from __future__ import annotations
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt, Signal

from ..theme import Colors, Fonts, tint


class FavoriteStar(QPushButton):
    """Marcar como favorita la accion que se esta mirando.

    En el rail, favorita se marca en el filete de la fila — que solo existe
    mientras la caja del grupo esta abierta. Esta estrella hace lo mismo desde
    la cabecera de los parametros: la accion abierta se marca sin volver a
    buscarla en el rail.
    """
    marked = Signal(bool)

    FULL = '★'
    EMPTY = '☆'

    def __init__(self, accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.accent = accent
        self._favorite = False
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._on_clicked)
        self._restyle()

    def is_favorite(self) -> bool:
        return self._favorite

    def set_favorite(self, value: bool, announce: bool = False) -> None:
        self._favorite = bool(value)
        self._restyle()
        if announce:
            self.marked.emit(self._favorite)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def _on_clicked(self) -> None:
        self.set_favorite(not self._favorite, announce=True)

    def _restyle(self) -> None:
        self.setText(self.FULL if self._favorite else self.EMPTY)
        color = self.accent if self._favorite else Colors.TEXT_MUTED
        self.setToolTip("Quitar de favoritas" if self._favorite
                        else "Marcar como favorita")
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 5px;
                color: {color}; font-size: {Fonts.SIZE_LG}px;
            }}
            QPushButton:hover {{ background: {tint(self.accent, 0.16)}; }}
            QPushButton:disabled {{ color: {Colors.BORDER}; }}
        """)
