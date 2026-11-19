"""Favorite actions: global to the app, not per repository.

An action exists in the rail for every repo alike; marking it a favorite
is a usage preference, not something that changes between repos. It goes
in QSettings.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QSettings

_IDS_KEY = "favorites/ids"
_ONLY_KEY = "favorites/only"


def favorite_ids() -> set[str]:
    """Return the ids of the favorite actions."""
    raw = QSettings().value(_IDS_KEY, [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(cast(list[str], raw) or [])


def is_favorite(capability_id: str) -> bool:
    """Return whether the action is a favorite."""
    return capability_id in favorite_ids()


def set_favorite(capability_id: str, value: bool) -> set[str]:
    """Mark or unmark a favorite."""
    ids = favorite_ids()
    ids.add(capability_id) if value else ids.discard(capability_id)
    QSettings().setValue(_IDS_KEY, sorted(ids))
    return ids


def toggle(capability_id: str) -> bool:
    """Flip a favorite and return the new state."""
    value = not is_favorite(capability_id)
    set_favorite(capability_id, value)
    return value


def only_favorites() -> bool:
    """Return whether the list shows only favorites."""
    raw = QSettings().value(_ONLY_KEY, False)
    return raw in (True, "true", "True", 1, "1")


def set_only_favorites(value: bool) -> None:
    """Save whether the list shows only favorites."""
    QSettings().setValue(_ONLY_KEY, bool(value))
