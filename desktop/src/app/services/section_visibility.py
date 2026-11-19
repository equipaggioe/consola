"""Which sections of the side column stay visible.

The sections are in `widgets/tab_panel.py`: Action, Security,
Parameters, Settings and Machine. They hide from the Ver menu or a
section header's right click. It is a global app preference, not per
repository, in QSettings like «only favorites»
(`services/favorites.py`).
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QSettings

_HIDDEN_KEY = "ui/hidden_sections"

# Each section's id, what it saves under, and its title, in the column's
# order. The Ver menu (`widgets/action_menu_bar.py`) lists them too.
SECTIONS = {
    "accion": "Acción",
    "seguridad": "Seguridad",
    "parametros": "Parámetros",
    "configuracion": "Configuración del repo",
    "maquina": "Configuración de la máquina",
}


# Hidden until the Ver menu shows them, while nothing is saved.
HIDDEN_BY_DEFAULT = ["maquina"]


def hidden_sections() -> set[str]:
    """Return the ids of the hidden sections."""
    raw = QSettings().value(_HIDDEN_KEY, HIDDEN_BY_DEFAULT)
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(cast(list[str], raw) or [])


def set_section_hidden(section_id: str, value: bool) -> set[str]:
    """Hide or show one section."""
    hidden = hidden_sections()
    hidden.add(section_id) if value else hidden.discard(section_id)
    QSettings().setValue(_HIDDEN_KEY, sorted(hidden))
    return hidden
