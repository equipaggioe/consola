from __future__ import annotations
import re
from PySide6.QtCore import QSettings

"""
Acciones favoritas, por repositorio.

Un repo Flutter no usa las mismas acciones que uno con VPS: la marca es del
repo, no de la app. Se guarda en QSettings, igual que el orden de pestanas
(`ui/project_tabs.py`), asi que sobrevive al cierre sin ensuciar el repo.
"""

_PREFIX = 'favorites'


def _slug(project_path: str) -> str:
    """'E:/Git/navetta' -> 'e_git_navetta'. QSettings usa '/' para anidar
    grupos, asi que una ruta cruda partiria la clave en pedazos."""
    return re.sub(r'[^A-Za-z0-9]+', '_', project_path).strip('_').lower()


def favorites_for(project_path: str) -> set[str]:
    raw = QSettings().value(f'{_PREFIX}/{_slug(project_path)}', [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(raw or [])


def is_favorite(project_path: str, capability_id: str) -> bool:
    return capability_id in favorites_for(project_path)


def set_favorite(project_path: str, capability_id: str, value: bool) -> set[str]:
    ids = favorites_for(project_path)
    ids.add(capability_id) if value else ids.discard(capability_id)
    QSettings().setValue(f'{_PREFIX}/{_slug(project_path)}', sorted(ids))
    return ids


def toggle(project_path: str, capability_id: str) -> bool:
    """Devuelve el estado nuevo."""
    value = not is_favorite(project_path, capability_id)
    set_favorite(project_path, capability_id, value)
    return value


_ONLY_KEY = f'{_PREFIX}/only'


def only_favorites() -> bool:
    """El modo de la vista es de la app, no del repo: el interruptor queda
    como lo dejaste al cerrar."""
    raw = QSettings().value(_ONLY_KEY, False)
    return raw in (True, 'true', 'True', 1, '1')


def set_only_favorites(value: bool) -> None:
    QSettings().setValue(_ONLY_KEY, bool(value))
