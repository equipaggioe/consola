"""The star that marks the open action as a favorite."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtWidgets import QPushButton, QWidget

from app import theme
from app.theme import Colors, Fonts, tint


class FavoriteStar(QPushButton):
    """Mark as favorite the action being looked at.

    In the menu bar search, a favorite is marked on the row's stripe.
    This star does the same from the footer, next to Run, without
    searching for the action again (`widgets/params_panel.py`).
    """

    marked = Signal(bool)

    FULL = "★"
    EMPTY = "☆"

    def __init__(self, accent: str = Colors.PRIMARY, parent: QWidget | None = None) -> None:
        """Build the star."""
        super().__init__(parent)
        self.accent = accent
        self._favorite = False
        self.setAccessibleName(QCoreApplication.translate("FavoriteStar", "Favorita"))
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Tab reaches it; a click does not take the focus.
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.clicked.connect(self._on_clicked)
        self._restyle()

    def is_favorite(self) -> bool:
        """Return whether it is marked."""
        return self._favorite

    def set_favorite(self, value: bool, announce: bool = False) -> None:
        """Mark or unmark it, telling the listeners if `announce`."""
        self._favorite = bool(value)
        self._restyle()
        if announce:
            self.marked.emit(self._favorite)

    def set_accent(self, accent: str) -> None:
        """Change the color of the star."""
        self.accent = accent
        self._restyle()

    @Slot()
    def _on_clicked(self) -> None:
        self.set_favorite(not self._favorite, announce=True)

    def _restyle(self) -> None:
        self.setText(self.FULL if self._favorite else self.EMPTY)
        # Empty, in the text and not the hint: its thin outline,
        # smoothed, did not reach 3:1 with DejaVu Sans (WCAG 1.4.11).
        color = self.accent if self._favorite else Colors.ON_SURFACE
        tip = (
            QCoreApplication.translate("FavoriteStar", "Quitar de favoritas")
            if self._favorite
            else QCoreApplication.translate("FavoriteStar", "Marcar como favorita")
        )
        self.setToolTip(tip)
        # A new tooltip does not reach assistive technology; a new
        # description does.
        self.setAccessibleDescription(tip)
        self.setFont(theme.font(Fonts.SIZE_LG))
        theme.glyph(self, color, tint(self.accent, 0.16))
