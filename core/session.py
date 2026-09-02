from __future__ import annotations
import threading
from dataclasses import dataclass, field

"""
Estado de sesion: lo que una tarea publica para que otra lo lea, en memoria.

`run_server.py` escribia `SERVER_PORT` en `scripts/.env` para que `run_terminal.py`
y `run_vite.py` lo leyeran despues. Funcionaba por casualidad de orden de
ejecucion y ensuciaba el repo con un dato que no es configuracion: es el puerto
que el backend consiguio *en esta corrida* (PLAN.md 7, caso 4).

Aca vive en memoria, con alcance por proyecto, y desaparece al cerrar la app.
Nada de esto se escribe a disco.
"""

# Ambito para lo que no es de ningun repo sino de la maquina: el serial del
# emulador que se acaba de arrancar sirve igual desde cualquier proyecto.
MACHINE = '@machine'

_lock = threading.Lock()
_state: dict[str, dict[str, object]] = {}


def publish(project: str, key: str, value: object) -> None:
    with _lock:
        _state.setdefault(project, {})[key] = value


def read(project: str, key: str, default: object = None) -> object:
    with _lock:
        return _state.get(project, {}).get(key, default)


def require(project: str, key: str) -> object:
    value = read(project, key)
    if value is None:
        raise KeyError(key)
    return value


def forget(project: str, key: str = '') -> None:
    with _lock:
        if not key:
            _state.pop(project, None)
        else:
            _state.get(project, {}).pop(key, None)


def snapshot(project: str) -> dict[str, object]:
    with _lock:
        return dict(_state.get(project, {}))


# --- endpoints -------------------------------------------------------------
# Lo que un launcher deja disponible: una URL con estado. Es la parte del
# estado de sesion que la interfaz mira todo el tiempo (la barra de endpoint de
# la pestana, el navegador embebido) y que ademas encadena launchers entre si:
# la SPA y la terminal esperan a que el backend conteste en vez de confiar en
# el orden en que se apretaron los botones (docs/launchers.md 2.5).

STARTING = 'starting'
READY = 'ready'
DOWN = 'down'

_ENDPOINTS = '@endpoints'


@dataclass
class Endpoint:
    """Una URL publicada por una tarea viva."""
    key: str
    url: str
    label: str = ''
    web: bool = True
    state: str = STARTING
    _ready: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def is_ready(self) -> bool:
        return self.state == READY


def publish_endpoint(project: str, endpoint: Endpoint) -> None:
    with _lock:
        _state.setdefault(project, {}).setdefault(_ENDPOINTS, {})[endpoint.key] = endpoint


def mark_endpoint(project: str, key: str, state: str) -> None:
    endpoint = read_endpoint(project, key)
    if endpoint is None:
        return
    endpoint.state = state
    if state == READY:
        endpoint._ready.set()
    else:
        endpoint._ready.clear()


def read_endpoint(project: str, key: str) -> 'Endpoint | None':
    with _lock:
        return _state.get(project, {}).get(_ENDPOINTS, {}).get(key)


def endpoints(project: str) -> list['Endpoint']:
    with _lock:
        return list(_state.get(project, {}).get(_ENDPOINTS, {}).values())


def forget_endpoint(project: str, key: str) -> None:
    with _lock:
        _state.get(project, {}).get(_ENDPOINTS, {}).pop(key, None)


def wait_for_endpoint(project: str, key: str, timeout: float = 0.0) -> 'Endpoint | None':
    """El endpoint, esperando a que este listo si todavia esta arrancando.

    Sin `timeout` no espera: contesta lo que haya. Es lo que permite que
    `serve_spa` funcione igual cuando el backend ya esta arriba (contesta al
    instante), cuando esta arrancando en otra pestana (espera) y cuando no hay
    backend en absoluto (devuelve `None` y la SPA sigue con su propia config).
    """
    endpoint = read_endpoint(project, key)
    if endpoint is None or timeout <= 0 or endpoint.is_ready:
        return endpoint
    endpoint._ready.wait(timeout)
    return endpoint
