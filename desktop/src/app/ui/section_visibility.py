"""Which sections of the side column stay visible.

The sections are in `ui/tab_panel.py`: Action, Security, Parameters and
Settings. It is a global app preference, not per repository, in
QSettings like «only favorites» (`ui/favorites.py`).
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QSettings

_HIDDEN_KEY = "ui/hidden_sections"


def hidden_sections() -> set[str]:
    """Return the ids of the hidden sections."""
    raw = QSettings().value(_HIDDEN_KEY, [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(cast(list[str], raw) or [])


def set_section_hidden(section_id: str, value: bool) -> set[str]:
    """Hide or show one section."""
    hidden = hidden_sections()
    hidden.add(section_id) if value else hidden.discard(section_id)
    QSettings().setValue(_HIDDEN_KEY, sorted(hidden))
    return hidden
