from __future__ import annotations
from dataclasses import dataclass, field

"""
Seguro por repositorio y por TIPO DE OBJETIVO.

El problema que resuelve no es "apretar un boton sin querer": es apretarlo en el
repo equivocado. Y no todos los destructivos son igual de graves — vaciar la
carpeta de artefactos de un repo de juguete se rehace con un build; borrar la
base del VPS de produccion, no.

Tres decisiones sostienen el diseno:

1. **El seguro es por tipo de objetivo, no por boton.** Lo que importa es el
   radio de dano: el VPS, la base, los otros repos. Un mismo boton puede tocar
   dos objetivos (`clean_vps` borra la base ademas del servidor) y un mismo
   boton puede tocar objetivos distintos segun sus parametros (`teardown_db`
   contra `local` no sale de esta maquina; contra `remoto` alcanza al VPS).

2. **El interruptor vive en su propia seccion, no en el panel de parametros.**
   Es deliberado: un seguro que se quita en el mismo gesto con el que se aprieta
   Ejecutar se vuelve parte del gesto, y a las dos semanas se quita sin leerlo.
   Aca se decide UNA vez, cuando se da de alta el repo. Un interruptor que se
   toca cada varios meses no llega a ser un reflejo.

   Se guarda en `.consola/params.json` (`ui/params_store.py`), no en
   `config.env`: el archivo .env son los DATOS que las tareas necesitan para
   hacer su trabajo —la IP, el usuario, el token—, y ningun paso lee jamas un
   `PROTECT_*`. Es una decision de la consola sobre este repo, de la misma
   familia que los pasos que quedan marcados en un panel, y va donde van esas.

3. **Lo que se repite es la confirmacion escrita, y verifica identidad.**
   Escribir `BORRAR` es correcto en cualquier repo: el automatismo siempre
   acierta y la comprobacion no comprueba nada. Escribir el NOMBRE DEL REPO
   solo es correcto en el repo que crees que tienes abierto — si te
   equivocaste, tus dedos escriben el nombre del otro y la accion no corre. El
   automatismo no erosiona esta comprobacion: es lo que la hace funcionar.

Un simulacro no dispara nada. `clean_artifacts` en modo `simulacro` y
`sync_common_files` en modo `simulacro` no destruyen: pedirles confirmacion
seria justo el ruido que gasta la senal del aviso de verdad.
"""


@dataclass(frozen=True)
class Target:
    """Un tipo de cosa que una accion destructiva puede romper."""
    id: str             # como se guarda en `.consola/params.json`
    label: str          # como se lee en el dialogo: "el VPS", "la base de datos"
    chip: str           # etiqueta corta para la barra de estado: "VPS", "BD"
    setting_label: str  # como se lee el interruptor en la seccion Seguridad
    protected_by_default: bool
    why: str            # por que ese default, para el tooltip del interruptor


TARGETS: tuple[Target, ...] = (
    Target('vps', 'el VPS', 'VPS', 'Proteger el VPS', True,
           'alcanza a una maquina remota y no hay deshacer'),
    Target('db', 'la base de datos', 'BD', 'Proteger la base de datos', True,
           'los datos borrados no vuelven sin un backup'),
    Target('otros_repos', 'otros repositorios', 'otros repos', 'Proteger otros repos', True,
           'escribe fuera de este repo, en carpetas que no estas mirando'),
    Target('publicacion', 'el canal de publicacion', 'publicacion', 'Proteger publicacion', True,
           'lo que se promueve queda a la vista de los usuarios'),
    Target('local', 'archivos de este repo', 'local', 'Proteger archivos locales', False,
           'apagado por defecto: un artefacto borrado se rehace con un build'),
)

_BY_ID = {t.id: t for t in TARGETS}


def get(target_id: str) -> Target | None:
    return _BY_ID.get(target_id)


# --- que rompe cada accion -------------------------------------------------
# Solo las `kind='destructive'`. `purge_emulators` no esta: es `scope='machine'`
# (borra AVDs e imagenes del SDK, que no son de ningun repo), asi que un
# interruptor por repositorio no tendria a que repositorio pertenecer. Se queda
# con su propia confirmacion escrita.

@dataclass(frozen=True)
class Rule:
    """Objetivos fijos de una accion, mas los que dependen de sus parametros."""
    always: tuple[str, ...] = ()
    # nombre del eje -> {valor: objetivos que ese valor agrega}
    when: dict = field(default_factory=dict)
    # nombre del eje -> valores con los que la accion NO destruye nada
    dry_run: dict = field(default_factory=dict)


RULES: dict[str, Rule] = {
    # Deja el VPS como estaba: servicio, base, repo, claves, paquetes y usuario.
    # Toca DOS objetivos, y por eso el seguro no puede ser por boton.
    'clean_vps': Rule(always=('vps', 'db')),
    'revoke_ssh': Rule(always=('vps',)),
    'revoke_github_ssh': Rule(always=('vps',)),

    # `local` no sale de esta maquina; `remoto` alcanza al servidor. El mismo
    # boton, dos radios de dano distintos.
    'teardown_db': Rule(always=('db',), when={'scope': {'remoto': ('vps',)}}),
    'rebuild_db': Rule(always=('db',), when={'scope': {'remoto': ('vps',)}}),

    # Toca dos objetivos: vacia el esquema de la base que diga `scope` y borra
    # los archivos de `alembic/versions/` del repo abierto.
    'reinit_migrations': Rule(always=('db', 'local'),
                              when={'scope': {'remoto': ('vps',)}}),

    'promote_app': Rule(always=('publicacion',)),

    'clean_artifacts': Rule(always=('local',), dry_run={'apply': ('simulacro',)}),
    'sync_common_files': Rule(always=('otros_repos',), dry_run={'apply': ('simulacro',)}),
}


def _chosen(payload: dict, axis: str) -> set[str]:
    """Lo marcado en un eje, venga como valor suelto o como lista."""
    raw = (payload.get('options') or {}).get(axis)
    if isinstance(raw, list):
        return set(raw)
    return {raw} if raw else set()


def targets_of(capability_id: str, payload: dict | None = None) -> list[Target]:
    """Que va a romper esta corrida, con estos parametros. Vacio = nada."""
    rule = RULES.get(capability_id)
    if rule is None:
        return []
    payload = payload or {}

    for axis, inocuos in rule.dry_run.items():
        if _chosen(payload, axis) & set(inocuos):
            return []   # un simulacro no destruye: no se pregunta nada

    ids = list(rule.always)
    for axis, mapa in rule.when.items():
        for value in _chosen(payload, axis):
            ids.extend(mapa.get(value, ()))

    vistos, salida = set(), []
    for tid in ids:
        target = _BY_ID.get(tid)
        if target is not None and tid not in vistos:
            vistos.add(tid)
            salida.append(target)
    return salida


def defaults() -> dict:
    """Como arranca un repo que todavia no dijo nada."""
    return {t.id: t.protected_by_default for t in TARGETS}


def state_from(stored: dict | None) -> dict:
    """El estado completo a partir de lo guardado, que puede ser parcial.

    Un objetivo que no figura en el json cae en su default —protegido, salvo
    `local`—: agregar un objetivo nuevo no puede dejar desprotegidos a los
    repos que ya existen.
    """
    estado = defaults()
    for tid, valor in (stored or {}).items():
        if tid in _BY_ID:
            estado[tid] = bool(valor)
    return estado


def protected(state: dict, capability_id: str, payload: dict | None = None) -> list[Target]:
    """Los objetivos que esta corrida toca Y que este repo tiene protegidos.

    `state` es lo que devuelve `state_from`: `{target_id: bool}`.
    """
    return [t for t in targets_of(capability_id, payload) if is_protected(state, t)]


def is_protected(state: dict, target: Target) -> bool:
    return bool(state.get(target.id, target.protected_by_default))


def repo_protections(state: dict) -> list[Target]:
    """Todos los objetivos que este repo tiene protegidos, sin mirar ninguna
    accion en particular. Es lo que resume el indicador de la barra de estado
    (`ui/tab_panel.py::WorkspaceStatusBar`)."""
    return [t for t in TARGETS if is_protected(state, t)]
