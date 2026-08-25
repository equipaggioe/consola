from __future__ import annotations
from PySide6.QtCore import QSettings

"""
Acciones favoritas: globales a la app, no por repositorio.

La accion existe en el rail para todos los repos por igual (el rail es una
sola instancia, poblada del registro); marcarla favorita es una preferencia
de uso, no algo que cambie de un repo a otro. Se guarda en QSettings, igual
que el orden de pestanas (`ui/project_tabs.py`).
"""

_IDS_KEY = 'favorites/ids'
_ONLY_KEY = 'favorites/only'


def favorite_ids() -> set[str]:
    raw = QSettings().value(_IDS_KEY, [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(raw or [])


def is_favorite(capability_id: str) -> bool:
    return capability_id in favorite_ids()


def set_favorite(capability_id: str, value: bool) -> set[str]:
    ids = favorite_ids()
    ids.add(capability_id) if value else ids.discard(capability_id)
    QSettings().setValue(_IDS_KEY, sorted(ids))
    return ids


def toggle(capability_id: str) -> bool:
    """Devuelve el estado nuevo."""
    value = not is_favorite(capability_id)
    set_favorite(capability_id, value)
    return value


def only_favorites() -> bool:
    raw = QSettings().value(_ONLY_KEY, False)
    return raw in (True, 'true', 'True', 1, '1')


def set_only_favorites(value: bool) -> None:
    QSettings().setValue(_ONLY_KEY, bool(value))
