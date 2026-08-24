from __future__ import annotations
import threading

"""
Estado de sesion: lo que una tarea publica para que otra lo lea, en memoria.

`run_server.py` escribia `SERVER_PORT` en `scripts/.env` para que `run_terminal.py`
y `run_vite.py` lo leyeran despues. Funcionaba por casualidad de orden de
ejecucion y ensuciaba el repo con un dato que no es configuracion: es el puerto
que el backend consiguio *en esta corrida* (PLAN.md 7, caso 4).

Aca vive en memoria, con alcance por proyecto, y desaparece al cerrar la app.
Nada de esto se escribe a disco.
"""

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
