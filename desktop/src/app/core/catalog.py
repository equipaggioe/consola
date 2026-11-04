from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from app.core import android, cache, canone, files, icons, shots, ssh, targets, toolchain, vps
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.registry import AxisDef, Capability, Facet, Step, registry

_VPS_KEYS = {"VPS_IP", "VPS_USER", "VPS_KEY_NAME", "VPS_DEPLOY_DIR"}

# Las tres cosas que de verdad se eligen de una system image. El id del SDK las
# trae permutadas en un solo paquete
# (`system-images;android-36;google_apis;x86_64`), y el catalogo publica varios
# cientos: una lista con todas es la misma pregunta hecha trescientas veces.
# Declaradas asi, el panel dibuja tres listas cortas que se recortan entre si
# —cambiar la version deja solo las variantes que existen para esa version— y
# el valor que se guarda sigue siendo el paquete entero.
_IMAGE_FACETS = (
    Facet("api", "Versión", 1),
    Facet("variant", "Variante", 2),
    Facet("abi", "Arquitectura", 3),
)

# El eje 'local'/'remoto' se repite igual en una docena de botones (DB,
# scripts de setup): una sola tabla de etiquetas para que el panel no muestre
# los valores crudos en minúscula.
_SCOPE_LABELS = {"local": "Local", "remote": "Remoto"}

# Todo boton con este eje conecta a la base (`db.credentials`): usuario, base y
# contrasena en los dos ambitos, y en remoto ademas lo que abre el SSH.
_DB_KEYS = {"DB_USER", "DB_NAME", "DB_PASSWORD"}
_SCOPE_AXIS = lambda: AxisDef(
    "scope",
    ["local", "remote"],
    "scope",
    labels=_SCOPE_LABELS,
    requires_env={"local": _DB_KEYS, "remote": _DB_KEYS | {"VPS_IP", "VPS_USER", "VPS_KEY_NAME"}},
)

# Que unidad systemd toca la accion. En el mismo VPS corren tres servicios —el
# del repo, coturn y Caddy— y los tres se reinician, se paran y se leen igual. Es un eje y no tres botones nuevos por lo
# mismo que `action` es un eje y no nueve botones: lo unico que cambia entre
# ellos es un nombre.
#
# Los valores no se enumeran: salen de preguntarle al VPS de ESTE repo cuales de
# las unidades de canone existen (`VPS_SERVICES`). Ofrecerlas todas siempre era
# ofrecer reiniciar un coturn que no esta instalado, y enterarse recien al apretar.
_SERVICE_AXIS = lambda: AxisDef(
    "service", [], "scope", label="Servicio", default=vps.MAIN_SERVICE, source=VPS_SERVICES
)

# `host` es del uvicorn que se levanta en ESTA maquina: escuchar en todas las
# interfaces (para probar desde el telefono) o solo en loopback. Los valores son
# los que entiende uvicorn; lo que se lee va en `labels`, porque `0.0.0.0` no es
# una frase.
_HOST_AXIS = lambda: AxisDef(
    "host",
    ["0.0.0.0", "127.0.0.1"],
    "scope",
    label="Escucha en",
    labels={"0.0.0.0": "Toda la red", "127.0.0.1": "Solo esta máquina"},
)


def for_project(cap: Capability, root: Path | str | None) -> Capability:
    """La capacidad tal como se ve con este repo abierto.

    Los ejes descubiertos (ADR-0006) no pueden declararse en `load_catalog()`:
    el catalogo se arma una vez al arrancar y el repo cambia con el selector.
    Aca se les llenan los valores mirando el repo, justo antes de dibujar el
    panel — un repo con tres SPA da tres valores, uno con una sola da uno, y un
    subproyecto nuevo aparece sin tocar el catalogo.

    Lo mismo vale para los pasos: los que exigen una caracteristica que el repo
    no tiene (`Step.requires_repo`) no se dibujan. No van en ambar como los que
    esperan una clave — ahi falta un dato que se puede cargar; aca falta el
    objeto sobre el que actuar, y la casilla no llevaria a ninguna parte.

    Los pasos se caen de la COPIA que mira el panel, no del catalogo: quien
    arma los kwargs es la capacidad registrada (`TabPanel._run` la busca por id)
    y un paso que el panel no dibujo no viene marcado en el payload, o sea que
    llega a la funcion en False. El paso no queda "sin decidir": queda apagado,
    que es lo correcto.

    Devuelve la misma capacidad cuando no hay nada que descubrir, asi que no
    cuesta nada llamarla para todas.
    """
    if not root:
        return cap
    has_steps = any(s.requires_repo for s in cap.steps)
    if not has_steps and not any(a.is_discovered for a in cap.axes):
        return cap
    # `Project.path` es un str; el descubrimiento trabaja con rutas.
    folder = Path(root)
    if not folder.is_dir():
        return cap
    resolved = [
        replace(a, values=targets.names_of(folder, a.discover)) if a.is_discovered else a
        for a in cap.axes
    ]
    chosen_steps = cap.steps_for(repo_features(folder)) if has_steps else cap.steps
    return replace(cap, axes=resolved, steps=chosen_steps)


def repo_features(root: Path | str | None) -> frozenset[str]:
    """Que caracteristicas tiene este repo (`core/targets.py::features`)."""
    if not root:
        return frozenset()
    folder = Path(root)
    return targets.features(folder) if folder.is_dir() else frozenset()


def applicable_ids(root: Path | str | None) -> set[str]:
    """Los botones que tienen sentido en este repo.

    Los que no —"Migrar" en un repo sin migraciones— se ocultan enteros en vez
    de quedar en ambar: no les falta configuracion, les falta sobre que actuar
    (ADR-0007). Un repo sin nada abierto no oculta nada:
    los menus ya estan deshabilitados por completo.
    """
    if not root:
        return {cap.id for cap in registry.get_all()}
    features = repo_features(root)
    return {cap.id for cap in registry.get_all() if cap.applies_to(features)}


# --- catalogos que se consultan -------------------------------------------
# Un eje `discover` se llena mirando el repo abierto (`core/targets.py`). Estos
# se llenan preguntandole a algo: al SDK, que dispositivos y que maquinas
# virtuales hay; al VPS del repo, cuales de los servicios que Consola administra
# existen ahi. Son la misma idea de ADR-0006 contra una fuente que no es la
# carpeta — y por eso viven aca, al lado de `for_project`, y no en el catalogo
# de botones.
#
# La diferencia entre las dos familias es a quien se le pregunta, y con ella
# cuanto tarda: el SDK es local, el VPS es una vuelta de SSH. Por eso las dos se
# resuelven fuera del hilo de la interfaz (`ui/params_panel.py::AxesLoader`) y
# las dos se cachean.

ANDROID_DEVICES = "android_devices"  # catalogo de dispositivos
ANDROID_IMAGES = "android_images"  # catalogo de maquinas publicadas
ANDROID_IMAGES_INSTALLED = "android_installed"  # maquinas ya instaladas
ANDROID_AVDS = "android_avds"  # AVD ya creados
ANDROID_RUNNING = "android_running"  # emuladores vivos ahora mismo
VPS_SERVICES = "vps_services"  # servicios systemd que existen en el VPS
BACKUP_FILES = "backup_files"  # respaldos ya guardados de este repo
RELEASES = "releases"  # releases firmados del repo en GitHub
SHOTS_APPS = "shots_apps"  # lo que la camara del repo dice que captura:
SHOTS_THEMES = "shots_themes"  # sus apps, sus temas y sus idiomas (ADR-0054)
SHOTS_LANGUAGES = "shots_languages"
_SHOTS_AXES = {SHOTS_APPS: "apps", SHOTS_THEMES: "themes", SHOTS_LANGUAGES: "languages"}
ICON_APPS = "icon_apps"  # apps del repo que toman su icono del logo

# Lo instalado y lo creado cambian mientras Consola esta abierta, asi que se
# cachean por un minuto y nada mas: alcanza para no repetir la consulta al abrir
# tres pestanas seguidas, y no alcanza para mentir despues de una instalacion.
# Los dos catalogos grandes usan el mes por defecto de `core/cache.py`.
_FRESH = 60.0


def queried_values(
    source: str,
    *,
    refresh: bool = False,
    config: Config | None = None,
    root: Path | str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Los valores de un eje consultado, con sus etiquetas legibles.

    A source that fails raises `TaskError`, and the panel shows why in place of the
    axis: an empty axis would hide it (ADR-0076).
    """
    if source == VPS_SERVICES:
        return _vps_services(config, root, refresh=refresh)
    if source == BACKUP_FILES:
        return _backup_files(config, root)
    if source == RELEASES:
        return _releases(root)
    if source in _SHOTS_AXES:
        return _shots_axis(source, config, root, refresh=refresh)
    if source == ICON_APPS:
        return _icon_apps(root)
    sdk = android.resolve_sdk()
    if source == ANDROID_DEVICES:
        catalog = android.device_catalog(sdk, refresh=refresh)
        return [d.id for d in catalog], {d.id: d.label for d in catalog}
    if source == ANDROID_IMAGES:
        catalog = android.image_catalog(sdk, refresh=refresh)
        return [i.package for i in catalog], _image_labels(catalog)
    if source == ANDROID_IMAGES_INSTALLED:
        packages = cache.cached(
            "android-installed", lambda: android.list_images(sdk), max_age=_FRESH, refresh=refresh
        )
        images = sorted((android.parse_image(p) for p in packages), key=lambda i: i.order)
        return [i.package for i in images], _image_labels(images)
    if source == ANDROID_AVDS:
        names = cache.cached(
            "android-avds", lambda: android.list_avds(sdk), max_age=_FRESH, refresh=refresh
        )
        return list(names), {}
    if source == ANDROID_RUNNING:
        # Nunca cacheado: es estado, no catalogo. Una respuesta vieja aca
        # ofreceria apagar un emulador que ya no existe.
        alive = android.running(sdk)
        return list(alive), {s: f"{n or '?'}  ({s})" for s, n in alive.items()}
    raise TaskError(f"Fuente desconocida: {source}")


def _image_labels(images: list[android.Image]) -> dict[str, str]:
    """Las etiquetas de un eje de system images: el paquete entero y sus partes.

    Las dos en la misma tabla porque `AxisDef.text_of` es una sola, y los ids no
    se pisan: un paquete siempre empieza con `system-images;`. El eje se dibuja
    por caracteristica (`_IMAGE_FACETS`), pero el paquete entero se sigue
    leyendo en el resumen de la corrida y en la lista de 'Liberar disco'.
    """
    return {**{i.package: i.label for i in images}, **android.facet_labels(images)}


def _vps_services(
    config: Config | None, root: Path | str | None, *, refresh: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Los servicios que existen en el VPS de ESTE repo.

    Sin configuracion no hay a quien preguntarle, y devolverlos todos seria
    ofrecer coturn en un repo que todavia no tiene ni IP: el eje queda vacio y
    el panel lo dice, igual que cuando no hay AVD creados.

    La cache es por host y no global: dos repos abiertos son casi siempre dos
    VPS, y compartir la respuesta le mostraria a uno los servicios del otro.
    """
    if config is None or root is None or not config.get("VPS_IP"):
        return [], {}
    remote = ssh.resolve_remote(config)
    _, app = canone.origin(Path(root))
    key = "".join(c if c.isalnum() else "-" for c in remote.target)
    values = cache.cached(
        f"vps-units-{key}",
        lambda: vps.installed_services(remote, app),
        max_age=_FRESH,
        refresh=refresh,
    )
    return list(values), vps.SERVICE_LABELS


def _backup_files(
    config: Config | None, root: Path | str | None
) -> tuple[list[str], dict[str, str]]:
    """Los respaldos ya guardados de este repo, del mas nuevo al mas viejo.

    **Sin cache**, por lo mismo que `ANDROID_RUNNING`: es estado, no catalogo.
    Una lista vieja ofreceria restaurar un dump que la rotacion acaba de borrar.

    Del mas nuevo al mas viejo para que el que queda preseleccionado sea el
    ultimo respaldo, que es el que se quiere casi siempre.

    Es el unico eje consultado que necesita la raiz del repo ademas de la
    configuracion: la carpeta puede ser relativa a ella. Los demas preguntan al
    SDK o al VPS, que no dependen de donde este el repo.
    """
    if config is None or not root:
        return [], {}
    from app.core.tasks.database import list_backups  # circular: tasks importa el registro

    values = list_backups(config, Path(root))
    return [p.name for p in values], {p.name: _backup_label(p) for p in values}


def _releases(root: Path | str | None) -> tuple[list[str], dict[str, str]]:
    """Los releases del repo que traen su firma, del mas nuevo al mas viejo.

    Sin cache, por lo mismo que `BACKUP_FILES`: un release se firma mientras
    Consola esta abierta. Si GitHub no contesta, el `TaskError` sube con lo que
    dijo `gh`: un eje vacio diria que no hay releases.
    """
    if not root:
        return [], {}
    from app.core.tasks.vps_release import releases  # circular: tasks importa el registro

    _, app = canone.origin(Path(root))
    signed = canone.signed(app, releases(Path(root)))
    return (
        [r["tag_name"] for r in signed],
        {r["tag_name"]: f"{r['tag_name']}  ({r['published_at'][:10]})" for r in signed},
    )


def _icon_apps(root: Path | str | None) -> tuple[list[str], dict[str, str]]:
    """Las apps que dicen donde va su icono (ADR-0055).

    Mira el repo y no una herramienta, pero no alcanza con el tipo de la app:
    una SPA que importa el logo por su cuenta (la landing de vettore) no lleva
    `favicon.svg`, y ofrecerla marcada era fallar en cada corrida hasta que
    alguien la desmarcara. Sin cache: es leer dos archivos por app.
    """
    if not root or not Path(root).is_dir():
        return [], {}
    return [t.name for t in icons.icon_apps(Path(root))], {}


def _shots_axis(
    source: str, config: Config | None, root: Path | str | None, *, refresh: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Un eje de la camara, con lo que ella dice que captura (ADR-0054).

    Preguntarle es arrancar node, y los tres ejes preguntan lo mismo: se cachea
    por repo un minuto, como los AVD. Cambiar la camara se ve al minuto o con
    Recargar.
    """
    if config is None or not root:
        return [], {}
    from app.core.tasks.images import camera_supported  # circular: tasks importa el registro

    key = "".join(c if c.isalnum() else "-" for c in str(Path(root).resolve()))
    declared = cache.cached(
        f"shots-supported-{key}",
        lambda: camera_supported(Path(root), config),
        max_age=_FRESH,
        refresh=refresh,
    )
    axis = _SHOTS_AXES[source]
    labels = SHOT_THEME_LABELS if axis == "themes" else {}
    return shots.supported_values(declared, axis), labels


def _backup_label(path: Path) -> str:
    """`2026-09-23 14:30  ·  12,4 MB`. El valor real es el nombre del archivo,
    que lleva el sello pegado y sin separar: ilegible en una lista.
    """
    parts = path.stem.rsplit("-", 2)
    try:
        when = datetime.strptime("-".join(parts[-2:]), "%Y%m%d-%H%M%S")
    except ValueError:
        return path.name
    return f"{when:%Y-%m-%d %H:%M}  ·  {files.human_size(files.size_of(path))}"


def forget_machine_cache() -> None:
    """Olvida lo que cambia al instalar, crear o borrar. La llama la UI cuando
    termina una tarea de maquina: el proximo panel ve el estado nuevo.
    """
    cache.forget("android-installed")
    cache.forget("android-avds")


# Valores por defecto de los SDK. Viven aca, con el resto de la forma de los
# botones, y `core/tasks/utils.py` los importa para usar el mismo cuando se le
# llama sin parametros: asi el panel y la funcion no pueden discrepar.
# En Linux se usan las rutas convencionales bajo el home; en Windows, las
# unidades que ya usaban los scripts.
ANDROID_DIR_DEFAULT = HOST.android_dir_default
FLUTTER_DIR_DEFAULT = HOST.flutter_dir_default
API_LEVEL_DEFAULT = "36"
BUILD_TOOLS_DEFAULT = "36.0.0"

ANDROID_PACKAGE_AXES = [
    AxisDef(
        "components",
        ["platform-tools", "emulator", "build-tools", "platform"],
        "checks",
        select="many",
        label="Componentes",
    ),
    AxisDef("api_level", [API_LEVEL_DEFAULT], "field", label="API level"),
    AxisDef("build_tools", [BUILD_TOOLS_DEFAULT], "field", label="Build-tools"),
]

# Los ejes de 'clean_artifacts'. Los valores son las claves que entiende
# `core/tasks/utils.py::find_artifacts` y las etiquetas van aparte, en `labels`:
# antes los valores ERAN el texto visible y `ui/task_adapters.py` mantenia dos
# tablas para traducirlos de vuelta, que es exactamente la duplicacion que el
# contrato de nombres saca (ADR-0003).
FAMILY_AXIS_VALUES = ["python", "gradle", "flutter", "crash"]
FAMILY_AXIS_LABELS = {
    "python": "Python",
    "gradle": "Gradle/Android",
    "flutter": "Flutter",
    "crash": "Volcados de crash",
}
HEAVY_AXIS_VALUES = ["node_modules", "venv", "build", "dart_tool"]
HEAVY_AXIS_LABELS = {
    "node_modules": "node_modules",
    "venv": ".venv",
    "build": "build/dist",
    "dart_tool": ".dart_tool",
}

# Solo el ejecutable sube la version del manifiesto (ADR-0059). Se muestran de
# mayor a menor, y el default real es `patch`.
SEMVER_MODES = ["major", "minor", "patch", "none"]
_SEMVER_AXIS = lambda: AxisDef("bump_mode", SEMVER_MODES, "scope", label="Bump", default="patch")

# Solo las que esta maquina puede compilar: ofrecer Windows en Linux seria
# ofrecer una casilla que siempre termina en error. Cada una trae su carpeta de
# salida de `config.env`, que solo aparece en pantalla si la plataforma esta
# marcada.
_PLATFORMS_AXIS = lambda: AxisDef(
    "platforms",
    toolchain.host_platforms(),
    "checks",
    select="many",
    label="Plataformas",
    defaults={"apk"},
    labels={k: p.label for k, p in toolchain.BUILD_PLATFORMS.items()},
    uses_env={k: {toolchain.out_key(k)} for k in toolchain.BUILD_PLATFORMS},
)

# 'Compilar binario' no es obligatorio: el script original tenia
# `BUILD_BINARY=false` para subir el ejecutable que ya estaba en `dist/` sin
# volver a empaquetarlo, para retomar un `scp` cortado. 'Checksum SHA-256' es
# propio del binario: un ejecutable que alguien descarga no se puede mirar por
# dentro, y el hash es lo unico que deja comprobar que lo bajado es lo que se
# publico.
BUILD_BINARY_STEPS = [
    Step("bump", "Subir número de versión"),
    Step("build", "Compilar binario"),
    Step("checksum", "Calcular checksum"),
    Step("upload", "Subir al VPS", default=False, requires_env=_VPS_KEYS),
]

# Los ocho pasos de `database.bootstrap_db` son sus ocho booleanos: termina
# en una base usable, con particiones y datos, no solo en el esquema creado.
#
# 'Extensiones' arranca desmarcado porque el paquete de sistema de PostGIS no
# siempre esta: marcarlo por default prometia una extension que la maquina no
# tenia.
# Antes ni siquiera era una casilla y `enable_extensions` corria siempre.
#
# Cuales extensiones son sale de `DB_EXTENSIONS`, no se deduce. Salian de los
# `CREATE EXTENSION` de las migraciones del repo y eso no podia funcionar:
# `alembic revision --autogenerate` nunca escribe uno, asi que la lista salia
# vacia; y una migracion que si lo declarara es la que necesita la extension ya
# creada para poder aplicarse. La casilla sigue eligiendo si el paso corre; el
# QUE no es un parametro de la corrida sino configuracion del repo, y por eso no
# tiene eje: no cambia entre dos veces que se aprieta el boton.
#
# Las etiquetas son verbos y dicen sobre qué actúan: una casilla que dice
# 'Migraciones' no distingue entre generarlas y ejecutarlas, y en una compuesta
# destructiva 'Base de datos' no dice si la crea o la borra. El sustantivo
# nombra el objeto; la casilla tiene que nombrar el acto.
BOOTSTRAP_DB_STEPS = [
    Step("role", "Crear rol de la aplicación"),
    Step("database", "Crear base de datos"),
    Step("privileges", "Otorgar permisos al rol"),
    Step("extensions", "Habilitar extensiones", default=False),
    Step("migrate", "Ejecutar migraciones", requires_repo=targets.MIGRATIONS),
    Step("partitions", "Crear particiones"),
    Step("seeders", "Cargar seeders"),
    Step("mock_seeders", "Cargar datos mock", default=False),
]


# Los cinco de `database.rebuild_db`, en el orden de la funcion. Reemplazan al
# `composed_of` que derivaba solo dos casillas (los seeders) para una compuesta
# de varios parametros: lo destructivo — vaciar el esquema — no se elegia, y es
# justo lo que uno quiere poder desmarcar.
#
# Reconstruir ya no reescribe el historial de migraciones: aplica el que hay.
# Borrarlo y escribir una inicial nueva es `reinit_migrations`, su propio boton.
REBUILD_DB_STEPS = [
    Step("drop", "Borrar tablas"),
    Step("migrate", "Ejecutar migraciones", requires_repo=targets.MIGRATIONS),
    Step("partitions", "Crear particiones"),
    Step("seeders", "Cargar seeders"),
    Step("mock_seeders", "Cargar datos mock"),
]


# Los tres de `database.reinit_migrations`. 'Vaciar esquema' es un paso suyo y
# no una precondicion que haya que recordar: el autogenerate compara contra la
# base viva, y sobre una base con tablas la "inicial" sale vacia.
REINIT_MIGRATIONS_STEPS = [
    Step("drop", "Borrar tablas"),
    Step("reset", "Borrar migraciones"),
    Step("generate", "Generar migración inicial"),
]


# Los dos pasos de `database.migrate_db`. Antes no eran casillas y `migrate_db`
# generaba y aplicaba siempre: no habia forma de generar la revision para
# mirarla antes de aplicar, ni de poner al dia una base atrasada sin autogenerar.
MIGRATE_DB_STEPS = [
    Step("generate", "Generar migración"),
    Step("apply", "Ejecutar migraciones"),
]


# Configurar VPS, en el orden en que la maquina lo necesita: `install.py` falla
# sin los paquetes o sin swap, y `credentials.py` lo instala `install.py`. Refrescar
# la huella arranca desmarcado: hace falta solo despues de reinstalar el VPS.
BOOTSTRAP_VPS_STEPS = [
    Step("known_host", "Refrescar known_hosts", default=False),
    Step("software", "Instalar paquetes y uv"),
    Step("swap", "Crear swap"),
    Step(
        "infra",
        "Instalar infraestructura",
        requires_env={"DOMAIN", "VALKEY_MEMORY", "OFFLINE_KEY"},
    ),
    Step("credentials", "Cargar credenciales", requires_env={"RESTIC_PASSWORD"}),
    Step("deploy", "Desplegar el último release"),
]

# Tag → `release.yml` → firma → `deploy.py`. Las claves van por paso: crear el
# tag no alcanza el VPS, y firmar solo pide la llave.
PUBLISH_RELEASE_STEPS = [
    Step("tag", "Crear tag"),
    Step("sign", "Firmar release", requires_env={"VPS_KEY_NAME"}),
    Step("deploy", "Desplegar", requires_env=_VPS_KEYS - {"VPS_DEPLOY_DIR"}),
]


# Los tres launchers del arranque diario, como pasos de una compuesta que NO es
# una secuencia: se lanzan a la vez, cada uno en su pestana, y ninguno termina
# (ADR-0011). El orden de esta lista es el de despacho, y el unico
# que importa es que el backend salga primero: los otros dos esperan su endpoint.
# Los pasos de abajo existian como parametros de su funcion y no como casillas:
# el catalogo dejaba que `composed_of` los derivara, y `composed_of` nombra
# CAPACIDADES (`generate_remote_keypair`), no parametros (`generate`). El panel
# dibujaba casillas cuyo id no le correspondia a nada y la funcion corria
# siempre con sus defaults (ADR-0003).

# Los dos lados de la clave con la que entra ESTA maquina. Desmarcar el local
# es el caso de revocar el acceso de una maquina que ya no se tiene enfrente.
REVOKE_SSH_STEPS = [
    Step("remote_side", "Borrar clave del VPS"),
    Step("local_side", "Borrar clave de esta máquina"),
]

# Los tres pasos de `utils.install_android_sdk`. Era la unica compuesta que
# recibia la lista de ids en vez de un booleano por paso: ahora recibe los tres
# booleanos como las otras doce (ADR-0003).
INSTALL_ANDROID_SDK_STEPS = [
    Step("tools", "Instalar herramientas de línea de comandos"),
    Step("packages", "Instalar paquetes del SDK"),
    Step("hypervisor", "Instalar aceleración del emulador"),
]

# `teardown_db` era `level='C'` sin pasos: sus dos booleanos no tenian casilla y
# borraba siempre las dos cosas. Borrar la base y dejar el rol es lo que se
# quiere antes de un bootstrap: el rol lo usan otras bases del mismo servidor.
TEARDOWN_DB_STEPS = [
    Step("database", "Borrar base de datos"),
    Step("role", "Borrar rol de la aplicación"),
]

SHOT_DESTINATION_LABELS = {
    "landing": "Landing",
    "play": "Google Play",
    "appstore": "App Store",
    "manual": "Manual",
    "og": "Open Graph",
    "social": "Redes sociales",
    "presskit": "Press kit",
}
_SHOT_DESTINATIONS_AXIS = lambda: AxisDef(
    "destinations",
    list(SHOT_DESTINATION_LABELS),
    "checks",
    select="many",
    label="Destinos",
    defaults={"landing"},
    labels=SHOT_DESTINATION_LABELS,
)

SHOT_THEME_LABELS = {"claro": "Claro", "oscuro": "Oscuro"}

# Lo que Consola le pasa a la camara del repo como argumentos (`--apps`,
# `--themes`, `--languages`, y `--device` con el serial del AVD elegido). Las
# apps, los temas y los idiomas los ofrece la propia camara (ADR-0054): se
# ofrece solo lo que sabe capturar. Las pantallas no se eligen: son suyas.
_SHOT_CAMERA_AXES = lambda: [
    AxisDef("apps", [], "checks", select="many", label="Apps", source=SHOTS_APPS),
    AxisDef("themes", [], "checks", select="many", label="Temas", source=SHOTS_THEMES),
    AxisDef("languages", [], "checks", select="many", label="Idiomas", source=SHOTS_LANGUAGES),
    # El emulador lo elige y lo arranca Consola, no el script (ADR-0049): se
    # elige un AVD creado, y si no esta vivo se levanta antes de correr la
    # camara. Si una app lo necesita lo sabe la camara (ADR-0052): sin
    # ninguno, es ella la que corta antes de sacar la primera foto.
    AxisDef(
        "avd",
        [],
        "pick",
        label="Emulador",
        source=ANDROID_AVDS,
        allow_empty=True,
        labels={"": "Ninguno"},
    ),
]

SCREENSHOTS_STEPS = [
    Step("shoot", "Sacar capturas", requires_env={"SHOTS_CMD"}),
    Step("render", "Revelar capturas"),
]

DEV_ENV_STEPS = [
    Step("backend", "Backend", optional=False),
    Step("serve_vite", "SPA"),
    Step("run_python", "App de escritorio", default=False),
]


def load_catalog() -> None:
    """Declara la forma de cada boton.

    `description` es la linea que la UI muestra en el tooltip del rail y bajo el
    nombre de la accion: que hace, en presente y en una oracion. `level` solo se
    escribe cuando no se deduce solo: una compuesta que no publica sus pasos
    (`teardown_db`, `migrate_db`) tiene que declararse `level='C'` a mano,
    porque sin `steps` ni `composed_of` la UI la tomaria por atomica.
    """
    # --- Ejecutar ------------------------------------------------------------
    # Lo que el launcher TE ENTREGA decide si su pestana tiene segunda vista:
    # una URL se mira en un navegador, un emulador se mira en su ventana
    # (ADR-0008).
    #
    # `view='web'` no es un boton mas ni una capacidad aparte: es la segunda
    # vista de la pestana del propio launcher, apuntada al endpoint que la tarea
    # publica con `ctx.serve()`. Un boton "abrir navegador" en el rail seria una
    # capacidad que no ejecuta nada, no registra nada y no tiene parametros.
    registry.register(
        Capability(
            id="backend",
            name="Levantar backend",
            group="Ejecutar",
            kind="live",
            icon="▶",
            view="web",
            description="Levanta el servidor FastAPI del repo, local o contra el VPS.",
            # El servidor se descubre como las SPA: la carpeta cuyo modulo de
            # arranque crea `FastAPI(`, se llame `server/` o `backend/`.
            # Los tres parametros que la funcion ya recibia y el catalogo no
            # ofrecia: corria clavada en 0.0.0.0:8000 con --reload. El puerto es
            # solo el preferido — `core/ports.py` busca el siguiente libre — y por
            # eso se puede dejar como esta sin miedo a chocar con otra pestana.
            axes=[
                AxisDef("target", [], "scope", label="Servidor", discover=(targets.FASTAPI,)),
                _SCOPE_AXIS(),
                _HOST_AXIS(),
                AxisDef("preferred_port", ["8000"], "field", label="Puerto", cast="int"),
                # Sin recarga es el modo en que se prueba lo que va a correr en el
                # VPS: `--reload` cambia como arranca la app y esconde los errores
                # que solo pasan una vez.
                AxisDef(
                    "reload",
                    ["reload", "no_reload"],
                    "scope",
                    label="Al cambiar el código",
                    truthy="reload",
                    labels={"reload": "Con recarga", "no_reload": "Sin recarga"},
                ),
            ],
            stub=True,
        )
    )
    # `fanout='target'`: marcar panel + backoffice son dos dev servers vivos a la
    # vez, no dos pasos en fila. Un eje `many` se recorre en bucle cuando la
    # capacidad termina (`build_vite`) y se reparte en pestanas cuando no
    # (ADR-0010).
    registry.register(
        Capability(
            id="serve_vite",
            name="Levantar SPA con Vite",
            group="Ejecutar",
            kind="live",
            icon="🌐",
            view="web",
            fanout="target",
            description="Arranca el dev server de Vite para las apps elegidas.",
            axes=[
                AxisDef(
                    "target",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=(targets.SPA_VITE,),
                ),
                # El puerto preferido, no el definitivo: con dos SPA marcadas la
                # segunda pestana toma el siguiente libre sola.
                AxisDef("preferred_port", ["5173"], "field", label="Puerto", cast="int"),
            ],
            stub=True,
        )
    )
    # No hay eje `framework`: elegir "Flutter o Flet" seria pedir que confirmen
    # algo que la carpeta ya contesta. Se elige la app; el framework viene con ella.
    # Tampoco tiene `view`: lo que entrega no es una URL, es una app en un
    # emulador, y esa ventana la dibuja Android.
    registry.register(
        Capability(
            id="run_mobile",
            name="Levantar app móvil",
            group="Ejecutar",
            kind="live",
            icon="📲",
            description="Corre la app móvil en el emulador o dispositivo conectado.",
            # `device` admite vacio y arranca vacio: la funcion ya elige sola —el
            # emulador que lanzo esta sesion, y si no el primero que conteste— y
            # solo hace falta decirlo cuando hay dos vivos. Un eje que obligara a
            # elegir dejaria el boton en ambar justo cuando no hay ninguno, que es
            # cuando el mensaje util es el de la funcion ("arranca uno primero").
            axes=[
                AxisDef("target", [], "scope", label="App móvil", discover=targets.MOBILE_APP),
                AxisDef(
                    "device",
                    [],
                    "pick",
                    label="Emulador",
                    source=ANDROID_RUNNING,
                    allow_empty=True,
                    labels={"": "El que esté corriendo"},
                ),
            ],
            stub=True,
        )
    )
    # Cualquier app Python del repo que no sea el servidor: PySide6, Flet de
    # escritorio, un bot. Como `serve_vite`, marcar varias abre una pestana por
    # cada una (ADR-0010).
    registry.register(
        Capability(
            id="run_python",
            name="Levantar app de escritorio",
            group="Ejecutar",
            kind="live",
            icon="🐍",
            fanout="target",
            description="Arranca las apps Python elegidas, con recarga al cambiar sus fuentes.",
            axes=[
                AxisDef(
                    "target",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=targets.DESKTOP_APP,
                )
            ],
            # Dos booleanos sueltos, no un paso encadenado: casilla real, no el
            # segmentado de `scope` (que es para "uno de estos dos", no "si o no").
            steps=[
                Step("watch", "Relanzar al detectar cambios"),
                Step("auto_login", "Auto-login de dev", default=False),
            ],
            stub=True,
        )
    )
    # La compuesta concurrente del grupo. No tiene `func` ni adaptador: su
    # cuerpo es el despachador de `ui/tab_panel.py`, porque "una pestana por
    # paso, todas vivas a la vez" no significa nada dentro de `core/`
    # (ADR-0011). Por eso se declara `stub=False` a mano.
    registry.register(
        Capability(
            id="dev_env",
            name="Levantar todo el entorno",
            cut=True,
            group="Ejecutar",
            kind="live",
            icon="🧪",
            level="C",
            concurrent=True,
            description="Levanta backend, SPA y apps Python a la vez, cada uno en su pestaña.",
            steps=DEV_ENV_STEPS,
            composed_of=["backend", "serve_vite", "run_python"],
            stub=False,
        )
    )

    # --- Compilar ------------------------------------------------------------
    # Sin ejes: el nombre de la carpeta se pregunta al correr (`ctx.ask`), no
    # se guarda. No es un parametro —un parametro es una decision que uno repite
    # igual, y el catalogo la recuerda por repo— ni un dato de configuracion:
    # cada SPA nueva se llama distinto, y guardado dejaba la segunda corrida
    # arrancando con el nombre de la primera, o sea con una carpeta que ya
    # existe. Tampoco es un eje descubierto: la carpeta todavia no esta.
    registry.register(
        Capability(
            id="create_spa",
            name="Crear SPA SvelteKit",
            group="Compilar",
            kind="once",
            icon="✨",
            description="Crea en el repo una SPA en blanco con SvelteKit, runes y UnoCSS.",
            stub=True,
        )
    )
    # `app` se descubre: un valor por app móvil del repo, sea Flutter o Flet. El
    # framework no se pregunta aparte porque viaja dentro del target elegido.
    # `bump_mode` es una lista cerrada, no un texto: va como opción excluyente
    # (igual que `dry_run` en clean_artifacts) y no como campo escrito.
    registry.register(
        Capability(
            id="build_flutter",
            name="Compilar app Flutter",
            group="Compilar",
            kind="once",
            icon="📦",
            description="Compila la app Flutter o Flet para las plataformas marcadas: APK, web, escritorio o iOS.",
            axes=[
                AxisDef("directory", [], "scope", label="App", discover=targets.MOBILE_APP),
                _PLATFORMS_AXIS(),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="build_vite",
            name="Compilar SPA",
            group="Compilar",
            kind="once",
            icon="🏗️",
            description="Deja compiladas las SPA del repo, listas para que el proxy las sirva.",
            axes=[
                AxisDef(
                    "directories",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=(targets.SPA_VITE,),
                )
            ],
            stub=True,
        )
    )
    # El tercer builder, y el unico que sube la version y publica en el VPS. Sus
    # ejes son campos y no una lista descubierta: el script original empaquetaba
    # *cualquier* ruta del repo (`server/main.py`, `tools/cli.py`), y un eje
    # `app` descubierto vacío dejaría en ámbar justo al repo que se empaqueta
    # desde su raíz — que es el caso de la propia Consola (ADR-0007).
    # Vacío no es "falta un dato": `resolve_entrypoint` deduce `src/main.py` de
    # la única app Python del repo, igual que hace el launcher App Python.
    registry.register(
        Capability(
            id="build_binary",
            name="Compilar ejecutable",
            group="Compilar",
            kind="once",
            icon="⚡",
            description="Empaqueta una app Python del repo como ejecutable descargable.",
            composed_of=["bump_version", "upload_to_vps"],
            axes=[
                AxisDef("entrypoint", [""], "field", label="Punto de entrada"),
                AxisDef("name", [""], "field", label="Nombre del ejecutable"),
                # Las dos decisiones de PyInstaller que cambian *que* se entrega:
                # un archivo suelto o una carpeta, y con o sin consola detras.
                AxisDef(
                    "onefile",
                    ["single_file", "folder"],
                    "scope",
                    label="Empaquetado",
                    truthy="single_file",
                    labels={"single_file": "Un archivo", "folder": "Carpeta"},
                ),
                AxisDef(
                    "windowed",
                    ["console", "window"],
                    "scope",
                    label="Al ejecutarse",
                    truthy="window",
                    labels={"console": "Consola", "window": "Ventana"},
                ),
                _SEMVER_AXIS(),
            ],
            steps=BUILD_BINARY_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="bump_version",
            name="Subir número de versión",
            group="Compilar",
            kind="once",
            icon="🏷️",
            description="Sube el número de versión del repo.",
            hidden=True,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="clean_artifacts",
            name="Borrar artefactos de build",
            group="Compilar",
            kind="destructive",
            icon="🧹",
            description="Borra cachés y basura de build del repo; en simulacro solo los lista.",
            axes=[
                AxisDef(
                    "families",
                    FAMILY_AXIS_VALUES,
                    "checks",
                    select="many",
                    label="Qué borrar",
                    labels=FAMILY_AXIS_LABELS,
                ),
                AxisDef(
                    "heavy",
                    HEAVY_AXIS_VALUES,
                    "checks",
                    select="many",
                    label="Pesados",
                    labels=HEAVY_AXIS_LABELS,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "apply",
                    ["dry_run", "delete"],
                    "scope",
                    label="Modo",
                    truthy="delete",
                    labels={"dry_run": "Simulacro", "delete": "Borrar"},
                ),
            ],
            stub=True,
        )
    )

    # --- Imágenes ------------------------------------------------------------
    # Los iconos salen del logo del repo: Consola lo rasteriza y lo deja donde
    # cada app lo toma (el `flutter_launcher_icons` del pubspec, el favicon de
    # la SPA). A diferencia de las capturas no hace falta un script del repo:
    # el repo solo pone el SVG. Se ofrecen solo las apps que dicen donde va su
    # icono (ADR-0055).
    registry.register(
        Capability(
            id="generate_icons",
            name="Generar íconos",
            group="Imágenes",
            kind="once",
            icon="🎨",
            description="Genera los íconos de las apps a partir del logo del repo.",
            axes=[AxisDef("apps", [], "checks", select="many", label="Apps", source=ICON_APPS)],
            stub=True,
        )
    )

    # El repo pone la camara y Consola el revelado: navegar la app, sembrar sus
    # datos y sacar el PNG es codigo del repo (importa sus modulos, conoce sus
    # selectores); convertir cada PNG a las medidas de cada destino es igual en
    # todos. Consola le pasa al script que apps, temas e idiomas capturar
    # (`_SHOT_CAMERA_AXES`); que pantallas hay lo decide el script.
    registry.register(
        Capability(
            id="shoot_screens",
            name="Sacar capturas",
            cut=True,
            group="Imágenes",
            kind="once",
            icon="📷",
            description="Corre la cámara del repo, que deja las capturas crudas de sus apps.",
            axes=_SHOT_CAMERA_AXES(),
            stub=True,
        )
    )
    # Un destino es un preset de medidas y formato (landing, tiendas, redes).
    # Solo arranca marcada la landing: las tiendas se publican de vez en cuando
    # y sus medidas hay que verificarlas antes contra la ficha vigente.
    registry.register(
        Capability(
            id="render_shots",
            name="Revelar capturas",
            group="Imágenes",
            kind="once",
            icon="🎞️",
            description="Convierte las capturas crudas a las medidas y formatos de cada destino.",
            axes=[_SHOT_DESTINATIONS_AXIS()],
            stub=True,
        )
    )
    # Los dos pasos se desmarcan: sin fotografiar queda revelar lo que ya esta en
    # disco, que es lo que se hace cuando cambia la medida de una tienda y no la
    # app. Mismo criterio que la compilacion desmarcable de los builders.
    registry.register(
        Capability(
            id="screenshots",
            name="Capturar y publicar",
            cut=True,
            group="Imágenes",
            kind="once",
            icon="📸",
            level="C",
            description="Saca las capturas de las apps del repo y las deja listas en cada destino.",
            composed_of=["shoot_screens", "render_shots"],
            axes=[*_SHOT_CAMERA_AXES(), _SHOT_DESTINATIONS_AXIS()],
            steps=SCREENSHOTS_STEPS,
            stub=True,
        )
    )

    # --- Repositorio ---------------------------------------------------------
    # Clonar es la unica accion del catalogo que no le pasa al repo abierto sino
    # a uno que todavia no existe, y por eso es `scope='machine'`: sus campos se
    # guardan una sola vez y no por repositorio (`ui/params_store.py`). La
    # carpeta destino vacia significa "al lado de los repos que ya tengo
    # abiertos" — el destino real casi siempre es la carpeta que contiene al
    # repo de la pestana, y escribirla a mano seria escribir lo que ya se sabe.
    #
    # `opens_repo=True` es el final del boton y no un extra: clonar para tener
    # que anadir la carpeta con «+» a continuacion deja la accion a mitad de
    # camino. Lo declara el catalogo y lo ejecuta la ventana, que es la unica
    # que sabe lo que es una pestana.
    registry.register(
        Capability(
            id="clone_repo",
            name="Clonar repositorio de GitHub",
            group="Repositorio",
            kind="once",
            icon="📥",
            scope="machine",
            opens_repo=True,
            description="Clona un repositorio de GitHub y lo abre como pestaña.",
            axes=[
                AxisDef("url", [""], "field", label="URL del repositorio", required=True),
                AxisDef("dest", [""], "field", label="Carpeta destino"),
                AxisDef("branch", [""], "field", label="Rama"),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="sync_common_files",
            name="Copiar archivos comunes a otros repos",
            group="Repositorio",
            kind="destructive",
            icon="🔄",
            description="Copia los archivos compartidos a los otros repos; en simulacro solo compara.",
            axes=[
                AxisDef("targets", [""], "field", label="Repos destino", multiline=True),
                AxisDef("paths", [""], "field", label="Archivos a copiar", multiline=True),
                AxisDef(
                    "apply",
                    ["dry_run", "apply"],
                    "scope",
                    label="Modo",
                    truthy="apply",
                    labels={"dry_run": "Simulacro", "apply": "Aplicar"},
                ),
            ],
            stub=True,
        )
    )
    # Los dos forzados existen para el caso en que alguien ya decidio que un
    # lado gana igual. Corren solo en esta maquina: el VPS no tiene clon del
    # repo (ADR-0061).
    registry.register(
        Capability(
            id="git_force_push",
            name="Force push",
            cut=True,
            group="Repositorio",
            kind="destructive",
            icon="⏫",
            description="Empuja a origin con --force la rama de esta máquina, aunque haya divergido.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="git_force_reset",
            name="Force reset",
            group="Repositorio",
            kind="destructive",
            icon="⏬",
            description="Descarta los commits y los cambios de esta máquina para dejarla igual a origin.",
            axes=[
                AxisDef(
                    "discard_changes",
                    ["ask", "discard"],
                    "scope",
                    label="Si hay cambios sin commitear",
                    truthy="discard",
                    danger={"discard"},
                    labels={"ask": "Preguntar", "discard": "Descartar"},
                )
            ],
            stub=True,
        )
    )

    # --- Base de datos -------------------------------------------------------
    # Cuatro botones sin eje `scope`: actuan solo sobre la base local. En el VPS
    # la base la crea `install.py`, migra `deploy.py` y respalda la receptora
    # de canone (ADR-0060).
    registry.register(
        Capability(
            id="bootstrap_db",
            name="Configurar base de datos",
            group="Base de datos",
            kind="once",
            icon="🏗️",
            description="Deja la base local usable desde cero: creada, migrada y con sus datos mínimos.",
            steps=BOOTSTRAP_DB_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="enable_extensions",
            name="Habilitar extensiones",
            group="Base de datos",
            kind="once",
            icon="🧩",
            description="Crea en la base las extensiones de Postgres que declara el repo.",
            axes=[_SCOPE_AXIS()],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="migrate_db",
            name="Correr migraciones",
            group="Base de datos",
            kind="once",
            icon="📐",
            requires_repo=targets.MIGRATIONS,
            description="Genera la migración pendiente y la aplica en la base local.",
            steps=MIGRATE_DB_STEPS,
            stub=True,
        )
    )
    # Las cuatro reciben `scope` en su funcion y el catalogo nunca les dio el
    # eje: corrian clavadas contra `local`, que es el default de la firma.
    registry.register(
        Capability(
            id="run_seeders",
            name="Correr seeders",
            cut=True,
            group="Base de datos",
            kind="once",
            icon="🌱",
            description="Carga los datos mínimos que la app necesita para arrancar.",
            axes=[_SCOPE_AXIS()],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="run_mock_seeders",
            name="Correr mock seeders",
            group="Base de datos",
            kind="once",
            icon="🎭",
            description="Carga datos de prueba encima de los datos base.",
            axes=[_SCOPE_AXIS()],
            stub=True,
        )
    )
    # Viva como un launcher: sostiene la conexion (y en remoto el tunel) hasta
    # cerrar la pestana, y lo que entrega es la vista de arbol y datos, no el
    # log (ADR-0015).
    registry.register(
        Capability(
            id="explore_db",
            name="Explorar datos",
            cut=True,
            group="Base de datos",
            kind="live",
            view="db",
            icon="🗂️",
            description="Navega esquemas, tablas y datos de la base, en solo lectura.",
            axes=[_SCOPE_AXIS()],
            stub=True,
        )
    )
    # El tunel no tiene parametros: el puerto remoto sale del VPS y el local lo
    # elige `core/ports.py` si el de enfrente esta ocupado.
    registry.register(
        Capability(
            id="ssh_tunnel",
            name="Abrir túnel a Postgres",
            group="Base de datos",
            kind="background",
            icon="🔗",
            description="Abre un túnel SSH al Postgres del VPS para conectarse en local.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="backup_db",
            name="Respaldar base de datos",
            group="Base de datos",
            kind="once",
            icon="💾",
            description="Vuelca la base local a un archivo y rota los respaldos viejos.",
            stub=True,
        )
    )
    # Destructiva: pisa la base entera con lo que traiga el dump. La lista de
    # respaldos no se enumera ni sale del repo: sale de mirar `BACKUP_DIR`, que
    # puede estar fuera del arbol de trabajo (ADR-0047).
    registry.register(
        Capability(
            id="restore_db",
            name="Restaurar base de datos",
            group="Base de datos",
            kind="destructive",
            icon="♻️",
            description="Carga un respaldo sobre la base local, reemplazando lo que haya.",
            axes=[AxisDef("dump", [], "pick", label="Respaldo", source=BACKUP_FILES)],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="rebuild_db",
            name="Reconstruir base",
            group="Base de datos",
            kind="destructive",
            icon="🔁",
            description="Vacía las tablas y vuelve a llenar la base: migraciones, particiones y seeders.",
            axes=[_SCOPE_AXIS()],
            steps=REBUILD_DB_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="reinit_migrations",
            name="Reiniciar historial de migraciones",
            group="Base de datos",
            kind="destructive",
            icon="🧨",
            requires_repo=targets.MIGRATIONS,
            description="Reinicia el historial de migraciones: deja una sola inicial con los modelos de hoy.",
            axes=[_SCOPE_AXIS()],
            steps=REINIT_MIGRATIONS_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="teardown_db",
            name="Borrar base y rol",
            group="Base de datos",
            kind="destructive",
            icon="💥",
            description="Borra la base de la aplicación y su rol.",
            axes=[_SCOPE_AXIS()],
            steps=TEARDOWN_DB_STEPS,
            stub=True,
        )
    )

    # --- Despliegue ----------------------------------------------------------
    # El despliegue propio salio entero (ADR-0059): quedan las versiones de
    # canone y los dos botones que operan los servicios que ya estan en el VPS.
    #
    # Un solo eje y no dos: `systemd_action` recibe UN parametro, y el catalogo
    # lo partia en 'buttons' (start/stop/restart/status) y 'menu' (el resto).
    # La particion no existia ni siquiera en el panel, que dibuja igual los dos
    # `expand`; lo unico que lograba era que el segundo eje no llegara a la
    # funcion. El default es 'status' —el de la firma— y no 'start': el valor
    # que arranca marcado es el que corre si alguien aprieta Ejecutar sin mirar.
    registry.register(
        Capability(
            id="systemd_action",
            name="Control del servicio",
            group="Despliegue",
            kind="once",
            icon="⚙️",
            description="Manda una acción al servicio systemd elegido en el VPS.",
            axes=[
                _SERVICE_AXIS(),
                AxisDef(
                    "action",
                    [
                        "status",
                        "start",
                        "stop",
                        "restart",
                        "enable",
                        "disable",
                        "reload",
                        "is-active",
                        "is-enabled",
                    ],
                    "buttons",
                    label="Acción",
                    default="status",
                    danger={"stop"},
                ),
            ],
            stub=True,
        )
    )
    # `follow` era un `expand='field'` con valores ['sí','no']: un booleano
    # dibujado como campo de texto libre, que ademas nunca llegaba a la funcion.
    registry.register(
        Capability(
            id="view_logs",
            name="Ver logs del servicio",
            group="Despliegue",
            kind="live",
            icon="📋",
            description="Muestra el journal del servicio elegido, de una o siguiéndolo en vivo.",
            axes=[
                _SERVICE_AXIS(),
                AxisDef(
                    "follow",
                    ["follow", "once"],
                    "scope",
                    label="Modo",
                    truthy="follow",
                    labels={"follow": "Seguir en vivo", "once": "De una"},
                ),
            ],
            stub=True,
        )
    )
    # Las versiones (ADR-0059): un tag que publica el `release.yml` del repo,
    # se firma en esta maquina y lo instala el `deploy.py` de canone.
    registry.register(
        Capability(
            id="publish_release",
            name="Publicar versión",
            group="Despliegue",
            kind="once",
            icon="🏷️",
            description="Crea el tag siguiente, espera a release.yml, firma el release y lo despliega.",
            axes=[
                AxisDef(
                    "part",
                    list(canone.PARTS),
                    "scope",
                    label="Sube",
                    default="patch",
                    labels={"major": "Major", "minor": "Minor", "patch": "Patch"},
                )
            ],
            steps=PUBLISH_RELEASE_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="deploy_version",
            name="Desplegar versión",
            group="Despliegue",
            kind="once",
            icon="🚢",
            description="Instala en el VPS un release ya firmado.",
            axes=[AxisDef("version", [], "pick", label="Versión", source=RELEASES)],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="upload_to_vps",
            name="Subir artefacto al VPS",
            group="Despliegue",
            kind="once",
            icon="📤",
            description="Copia el artefacto compilado al VPS.",
            hidden=True,
            stub=True,
        )
    )

    # --- VPS -----------------------------------------------------------------
    # Lo que se instala y como sale del repo (ADR-0059): no hay ejes que elegir.
    registry.register(
        Capability(
            id="bootstrap_vps",
            name="Configurar VPS",
            group="VPS",
            kind="once",
            icon="🚀",
            description="Deja el VPS listo con los programas de canone: paquetes, swap, install.py, credenciales y el último release.",
            steps=BOOTSTRAP_VPS_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_software",
            name="Instalar paquetes base",
            cut=True,
            group="VPS",
            kind="once",
            icon="📦",
            description="Instala en el VPS los paquetes que pide canone para este repo, y uv.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="load_credentials",
            name="Cargar credenciales",
            group="VPS",
            kind="once",
            icon="🔐",
            description="Pasa las credenciales de config.env a credentials.py de canone.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="refresh_known_host",
            name="Refrescar known_hosts",
            group="VPS",
            kind="once",
            icon="🔄",
            description="Borra del known_hosts de esta máquina la huella vieja del VPS.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="update_cloudflare",
            name="Actualizar Cloudflare",
            group="VPS",
            kind="once",
            icon="☁️",
            description="Apunta el registro DNS de Cloudflare a la IP pública actual.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="health_check",
            name="Health check",
            cut=True,
            group="VPS",
            kind="once",
            icon="❤️",
            description="Comprueba que el VPS responde y el servicio está arriba.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="view_events",
            name="Ver eventos",
            group="VPS",
            kind="once",
            icon="📊",
            description="Muestra los últimos eventos, el último respaldo y el disco del servidor.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="run_command",
            name="Ejecutar comando",
            group="VPS",
            kind="once",
            icon="💻",
            description="Corre un comando suelto en el VPS y trae su salida.",
            axes=[AxisDef("command", [""], "field", label="Comando")],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="ssh_login",
            name="Abrir sesión SSH",
            group="VPS",
            kind="interactive",
            icon="🔑",
            description="Abre una sesión SSH interactiva contra el VPS del repo.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="revoke_ssh",
            name="Quitar acceso SSH",
            group="VPS",
            kind="destructive",
            icon="🔓",
            description="Quita del VPS la clave pública con la que entra esta máquina.",
            steps=REVOKE_SSH_STEPS,
            stub=True,
        )
    )

    # --- Emuladores ----------------------------------------------------------
    # Los cuatro botones son de la maquina, no del repo: un AVD sirve para
    # cualquier proyecto, igual que el SDK. Instalar la maquina virtual, crear
    # el AVD y arrancarlo dejaron de ser tres casillas de una compuesta y son
    # tres botones, porque cada uno tiene su propio catalogo de opciones: un
    # paso con opciones propias ya no entra en una casilla (ADR-0027).
    registry.register(
        Capability(
            id="install_system_image",
            name="Instalar imagen de sistema",
            group="Emuladores",
            kind="once",
            icon="💿",
            scope="machine",
            description="Descarga del SDK la máquina virtual (system image) que va a correr el AVD.",
            axes=[
                AxisDef(
                    "image",
                    [],
                    "pick",
                    label="Máquina virtual",
                    source=ANDROID_IMAGES,
                    facets=_IMAGE_FACETS,
                )
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="create_avd",
            name="Crear AVD",
            group="Emuladores",
            kind="once",
            icon="🧱",
            scope="machine",
            description="Crea el dispositivo virtual eligiéndolo del catálogo del SDK.",
            axes=[
                AxisDef("device", [], "pick", label="Dispositivo", source=ANDROID_DEVICES),
                # Sin `facets`, a diferencia de 'Instalar máquina': acá la lista
                # son las que ya están bajadas, casi siempre una o dos. Partir dos
                # entradas en tres listas no ahorra ninguna lectura y hace creer
                # que hay un catálogo detrás — la forma del control estaría
                # diciendo algo falso sobre cuántas opciones hay.
                AxisDef(
                    "image",
                    [],
                    "pick",
                    label="Máquina virtual (instaladas)",
                    source=ANDROID_IMAGES_INSTALLED,
                ),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="launch_emulator",
            name="Abrir emulador",
            group="Emuladores",
            kind="live",
            icon="📲",
            scope="machine",
            description="Arranca uno de los AVD ya creados y sigue su salida.",
            axes=[
                AxisDef("avd", [], "pick", label="AVD", source=ANDROID_AVDS),
                AxisDef(
                    "wipe",
                    ["normal", "wipe_data"],
                    "scope",
                    label="Arranque",
                    truthy="wipe_data",
                    danger={"wipe_data"},
                    labels={"normal": "Normal", "wipe_data": "Borrar datos"},
                ),
                # Los tres flags que de verdad se escriben. Eran texto libre
                # —habia que acordarse de como se llaman y escribirlos bien— y
                # son una eleccion de si o no, que es exactamente una casilla.
                # El nombre del flag ES el valor: asi no hace falta una tabla
                # que traduzca, y `core/tasks/emulators.py` los suma tal cual.
                AxisDef(
                    "boot_flags",
                    ["-no-snapshot-load", "-no-snapshot-save", "-no-window"],
                    "checks",
                    select="many",
                    checked_by_default=False,
                    allow_empty=True,
                    label="Opciones de arranque",
                    labels={
                        "-no-snapshot-load": "Arranque en frío (ignora el snapshot)",
                        "-no-snapshot-save": "No guardar el snapshot al cerrar",
                        "-no-window": "Sin ventana (headless, solo adb)",
                    },
                ),
                # El renderizado es excluyente, no una casilla: pedir host y
                # software a la vez no significa nada.
                AxisDef(
                    "gpu",
                    ["host", "software"],
                    "scope",
                    label="GPU",
                    labels={"host": "Host (GPU real)", "software": "Software (swiftshader)"},
                ),
                # Lo que queda de la linea de comandos, para el flag que no esta
                # arriba (`-memory 4096`, `-http-proxy ...`). Se suma a las
                # casillas y a los flags de siempre de `core/android.py`
                # (`-no-boot-anim`, `-netdelay none`...) en vez de reemplazarlos.
                # Una sola linea porque es una linea de comandos: se parte en
                # tokens como la partiria una shell, y `-memory 4096` son dos.
                AxisDef("flags", [""], "field", label="Flags extra del emulador"),
            ],
            live_state=ANDROID_RUNNING,
            stub=True,
        )
    )
    # Hidden atomic capabilities
    # Apagar no es un boton del rail: cerrar la pestana del emulador ya lo
    # apaga, y para los huerfanos —un emulador de una sesion anterior o
    # arrancado desde Android Studio— esta el ✕ de la cabecera de estado del
    # panel, que es donde se ven. Sigue siendo una capacidad porque la corre el
    # runner como cualquier otra, con su log en la consola.
    registry.register(
        Capability(
            id="stop_emulator",
            name="Apagar emulador",
            group="Emuladores",
            kind="once",
            icon="⏹",
            scope="machine",
            description="Apaga por adb el emulador indicado.",
            # No se dibuja ningun panel para esta capacidad, pero el eje se declara
            # igual: es la unica forma de que el serial que le pasa el ✕ llegue a la
            # funcion. La declaracion es el contrato, la haya dibujado alguien o no.
            axes=[AxisDef("serial", [], "pick", label="Emulador", source=ANDROID_RUNNING)],
            hidden=True,
            stub=True,
        )
    )
    # Un solo boton de limpieza para las dos cosas que ocupan disco: el AVD
    # pesa cientos de MB y la maquina virtual, varios GB. Borrar uno suelto es
    # marcar una casilla, no otro boton (ADR-0004).
    registry.register(
        Capability(
            id="purge_emulators",
            name="Borrar AVDs e imágenes",
            group="Emuladores",
            kind="destructive",
            icon="🗑️",
            scope="machine",
            description="Borra AVD y máquinas virtuales; en simulacro solo los lista con su tamaño.",
            axes=[
                AxisDef(
                    "avds",
                    [],
                    "checks",
                    select="many",
                    label="AVD",
                    source=ANDROID_AVDS,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "images",
                    [],
                    "checks",
                    select="many",
                    label="Máquinas virtuales",
                    source=ANDROID_IMAGES_INSTALLED,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "apply",
                    ["dry_run", "delete"],
                    "scope",
                    label="Modo",
                    truthy="delete",
                    labels={"dry_run": "Simulacro", "delete": "Borrar"},
                ),
            ],
            stub=True,
        )
    )

    # --- SDKs ----------------------------------------------------------------
    registry.register(
        Capability(
            id="install_android_sdk",
            name="Instalar SDK de Android",
            group="SDKs",
            kind="once",
            icon="🤖",
            scope="machine",
            description="Deja esta máquina lista para compilar y emular Android.",
            composed_of=[
                "install_android_tools",
                "install_android_packages",
                "install_android_hypervisor",
            ],
            axes=[
                AxisDef("install_dir", [ANDROID_DIR_DEFAULT], "field", label="Directorio"),
                *ANDROID_PACKAGE_AXES,
            ],
            steps=INSTALL_ANDROID_SDK_STEPS,
            stub=True,
        )
    )
    # Los SDK son de la maquina, no del repo abierto: `scope='machine'`. La
    # instalacion se parte en tres atomicas porque agregar paquetes es lo que
    # se repite (una API nueva, otro build-tools) y no tiene por que arrastrar
    # la descarga del SDK ni tocar el PATH.
    registry.register(
        Capability(
            id="install_android_tools",
            name="Instalar command-line tools",
            cut=True,
            group="SDKs",
            kind="once",
            icon="🧰",
            scope="machine",
            description="Descarga las command-line tools del SDK y las deja en el entorno del usuario.",
            axes=[AxisDef("install_dir", [ANDROID_DIR_DEFAULT], "field", label="Directorio")],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_android_packages",
            name="Instalar paquetes del SDK",
            group="SDKs",
            kind="once",
            icon="📦",
            scope="machine",
            description="Acepta las licencias e instala en el SDK los paquetes que falten.",
            axes=list(ANDROID_PACKAGE_AXES),
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_android_hypervisor",
            name="Instalar aceleración del emulador",
            group="SDKs",
            kind="once",
            icon="⚡",
            scope="machine",
            description="Verifica la virtualización que el emulador necesita, y en Windows instala el driver.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_flutter_sdk",
            name="Instalar SDK de Flutter",
            cut=True,
            group="SDKs",
            kind="once",
            icon="🦋",
            scope="machine",
            description="Descarga el canal stable de Flutter y lo deja en el entorno del usuario.",
            axes=[AxisDef("install_dir", [FLUTTER_DIR_DEFAULT], "field", label="Directorio")],
            stub=True,
        )
    )
