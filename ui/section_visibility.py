from __future__ import annotations
from PySide6.QtCore import QSettings

"""
Que secciones de la columna lateral (`ui/tab_panel.py`: Accion, Seguridad,
Parametros, Configuracion) quedan a la vista. Preferencia global de la app, no
por repositorio — igual que «solo favoritos» (`ui/favorites.py`), en QSettings.
"""

_HIDDEN_KEY = 'ui/hidden_sections'


def hidden_sections() -> set[str]:
    raw = QSettings().value(_HIDDEN_KEY, [])
    if isinstance(raw, str):
        raw = [raw] if raw else []
    return set(raw or [])


def set_section_hidden(section_id: str, value: bool) -> set[str]:
    hidden = hidden_sections()
    hidden.add(section_id) if value else hidden.discard(section_id)
    QSettings().setValue(_HIDDEN_KEY, sorted(hidden))
    return hidden
