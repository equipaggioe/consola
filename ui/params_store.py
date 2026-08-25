from __future__ import annotations
import hashlib
import json
import os

from PySide6.QtCore import QSettings

"""
Parametros elegidos en el panel de una accion: por repositorio Y por boton.

A diferencia de los favoritos (`ui/favorites.py`), que son una preferencia
global de uso, lo que se marca en el panel de parametros es una decision
sobre ESE repo: que variantes construir, que pasos correr, con que opcion.
El mismo boton en dos repos distintos casi nunca quiere lo mismo, asi que
la clave de guardado lleva las dos cosas.

Se guarda en QSettings (no en `.consola/config.env`): el archivo del repo
es configuracion que el repo necesita para funcionar; esto es como dejaste
la pantalla la ultima vez.
"""

_PREFIX = 'params'


def _repo_key(repo_path: str) -> str:
    """Huella estable de la ruta del repo.

    No se usa la ruta tal cual porque QSettings trata '/' como separador de
    grupos y en Windows la ruta trae ademas ':' y mayusculas inestables.
    """
    norm = os.path.normcase(os.path.normpath(repo_path or ''))
    return hashlib.sha1(norm.encode('utf-8')).hexdigest()[:12]


def _key(repo_path: str, capability_id: str) -> str:
    return f'{_PREFIX}/{_repo_key(repo_path)}/{capability_id}'


def load(repo_path: str, capability_id: str) -> dict | None:
    """Lo guardado para ese boton en ese repo, o None si nunca se toco."""
    raw = QSettings().value(_key(repo_path, capability_id), '')
    if not raw:
        return None
    try:
        state = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def save(repo_path: str, capability_id: str, state: dict) -> None:
    QSettings().setValue(_key(repo_path, capability_id),
                         json.dumps(state, ensure_ascii=False))


def clear(repo_path: str, capability_id: str) -> None:
    QSettings().remove(_key(repo_path, capability_id))


def stored_steps(repo_path: str, capability_id: str) -> list[str] | None:
    """Pasos activos guardados, para calcular fuera del panel que le falta a
    una accion para poder correr sin abrir la pestana (`ui/rail.py`)."""
    state = load(repo_path, capability_id)
    if not state:
        return None
    steps = state.get('steps')
    return list(steps) if isinstance(steps, list) else None
