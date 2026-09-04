from __future__ import annotations
import hashlib
import json
import os
import tempfile

from PySide6.QtCore import QSettings, QTimer

from core.envfile import CONSOLA_DIR, ensure_gitignored

"""
Parametros elegidos en el panel de una accion: por repositorio Y por boton.

**Viven en el repo**, en `.consola/params.json`, al lado de `config.env`. Antes
estaban en QSettings —una tabla global de la maquina indexada por un sha1 de la
ruta—, y eso tenia tres problemas que el archivo resuelve solos:

- Mover o renombrar la carpeta del repo perdia todo lo elegido, porque la clave
  era la ruta vieja. Ahora los parametros viajan con la carpeta.
- Borrar el repo dejaba su basura en el registro para siempre.
- No habia forma de mirar ni de editar a mano lo guardado.

`.consola/` esta en el `.gitignore` (`core/envfile.py`), asi que el archivo no
se commitea: sigue siendo preferencia de esta maquina, solo que guardada donde
corresponde.

La excepcion son las capacidades con `scope='machine'` (instalar un SDK): esas
le pasan a la maquina, no al repo. Un repo no puede opinar sobre donde va el
SDK de Android, asi que **se quedan en QSettings** — la regla es "decision del
repo -> archivo del repo; decision de la maquina -> QSettings".

--- Sobre el rendimiento ---------------------------------------------------
Dos accesos lo dominan todo y los dos son calientes:

- `ui/rail.py::_missing_keys` llama a `stored_steps` una vez por capacidad cada
  vez que se cambia de repo (decenas de lecturas seguidas).
- `ui/params_panel.py::_refresh_summary` llama a `save` en cada tecla de un
  campo de texto.

Por eso el archivo se lee entero UNA vez por repo a un cache en memoria, y las
escrituras se juntan en un temporizador corto en vez de bajar al disco por
pulsacion. `flush()` fuerza la bajada; la llama el cierre de la ventana.
"""

_FILE_NAME = 'params.json'
_LEGACY_PREFIX = 'params'
_FLUSH_MS = 500

# repo normalizado -> {capability_id: estado}. La ruta normalizada sirve de
# clave y de destino de escritura a la vez: `normcase` solo baja mayusculas en
# Windows, y esa ruta abre el mismo archivo.
_cache: dict[str, dict] = {}
_dirty: set[str] = set()
_timer: QTimer | None = None


def _norm(repo_path: str) -> str:
    return os.path.normcase(os.path.normpath(repo_path or ''))


def _repo_key(repo_path: str) -> str:
    """Huella sha1 de la ruta: solo para leer lo que quedo en QSettings de
    antes de que los parametros vivieran en el repo."""
    return hashlib.sha1(_norm(repo_path).encode('utf-8')).hexdigest()[:12]


def _file(repo_norm: str) -> str:
    return os.path.join(repo_norm, CONSOLA_DIR, _FILE_NAME)


def _is_machine(capability_id: str) -> bool:
    from core.registry import registry

    cap = registry.get_capability(capability_id)
    return cap is not None and cap.is_machine_wide


def _machine_key(capability_id: str) -> str:
    return f'{_LEGACY_PREFIX}/machine/{capability_id}'


# --- lectura ---------------------------------------------------------------

def _read(repo_path: str) -> dict:
    """Todo lo guardado para un repo, cacheado. Nunca lanza: un archivo roto
    a mano se trata como si no hubiera nada, y el primer guardado lo rehace."""
    key = _norm(repo_path)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    data: dict = {}
    try:
        with open(_file(key), 'r', encoding='utf-8') as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = {k: v for k, v in loaded.items() if isinstance(v, dict)}
    except (OSError, ValueError, UnicodeDecodeError):
        data = {}

    if not data:
        data = _adopt_legacy(repo_path)

    _cache[key] = data
    return data


def _adopt_legacy(repo_path: str) -> dict:
    """Rescata lo que este repo tenia en QSettings de la version anterior.

    Se hace una sola vez, cuando todavia no hay archivo: se copia al cache y el
    primer guardado lo baja al repo. Las claves viejas NO se borran — si se
    vuelve a la version anterior, lo elegido sigue ahi.
    """
    settings = QSettings()
    group = f'{_LEGACY_PREFIX}/{_repo_key(repo_path)}'
    settings.beginGroup(group)
    try:
        ids = settings.childKeys()
    finally:
        settings.endGroup()

    rescatado: dict = {}
    for capability_id in ids:
        raw = settings.value(f'{group}/{capability_id}', '')
        if not raw:
            continue
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(state, dict):
            rescatado[capability_id] = state
    return rescatado


def load(repo_path: str, capability_id: str) -> dict | None:
    """Lo guardado para ese boton en ese repo, o None si nunca se toco."""
    if _is_machine(capability_id):
        raw = QSettings().value(_machine_key(capability_id), '')
        if not raw:
            return None
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return state if isinstance(state, dict) else None

    state = _read(repo_path).get(capability_id)
    return state if isinstance(state, dict) else None


def stored_steps(repo_path: str, capability_id: str) -> list[str] | None:
    """Pasos activos guardados, para calcular fuera del panel que le falta a
    una accion para poder correr sin abrir la pestana (`ui/rail.py`)."""
    state = load(repo_path, capability_id)
    if not state:
        return None
    steps = state.get('steps')
    return list(steps) if isinstance(steps, list) else None


# --- escritura -------------------------------------------------------------

def save(repo_path: str, capability_id: str, state: dict) -> None:
    if _is_machine(capability_id):
        QSettings().setValue(_machine_key(capability_id),
                             json.dumps(state, ensure_ascii=False))
        return

    key = _norm(repo_path)
    data = _read(repo_path)
    if data.get(capability_id) == state:
        return   # una tecla que no cambio nada no ensucia el archivo
    data[capability_id] = state
    _dirty.add(key)
    _schedule()


def clear(repo_path: str, capability_id: str) -> None:
    if _is_machine(capability_id):
        QSettings().remove(_machine_key(capability_id))
        return
    key = _norm(repo_path)
    if _read(repo_path).pop(capability_id, None) is not None:
        _dirty.add(key)
        _schedule()


def _schedule() -> None:
    """Junta las escrituras de una rafaga de tecleo en una sola bajada."""
    global _timer
    if _timer is None:
        _timer = QTimer()
        _timer.setSingleShot(True)
        _timer.setInterval(_FLUSH_MS)
        _timer.timeout.connect(flush)
    _timer.start()


def flush() -> None:
    """Baja al disco lo pendiente. La llama el temporizador y el cierre de la
    ventana (`ui/main_window.py::closeEvent`), para que los ultimos cambios no
    se pierdan si se cierra dentro de la ventana del temporizador."""
    for key in list(_dirty):
        _dirty.discard(key)
        _write(key, _cache.get(key) or {})


def _write(repo_norm: str, data: dict) -> None:
    """Escritura atomica: se arma al lado y se renombra encima.

    Ahora es UN archivo por repo, no una clave por boton: un corte a mitad de
    escritura se llevaria todos los parametros del repo, no uno. `os.replace`
    es atomico en el mismo volumen y en Windows tambien.
    """
    path = _file(repo_norm)
    carpeta = os.path.dirname(path)
    try:
        os.makedirs(carpeta, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=carpeta, prefix='.params-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write('\n')
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        # Un repo en un disco desconectado o de solo lectura no debe tumbar la
        # interfaz: lo elegido sigue en el cache y vale para esta sesion.
        return
    ensure_gitignored(repo_norm)


def forget(repo_path: str) -> None:
    """Suelta el cache de un repo que se quito de las pestanas."""
    key = _norm(repo_path)
    if key in _dirty:
        _dirty.discard(key)
        _write(key, _cache.get(key) or {})
    _cache.pop(key, None)
