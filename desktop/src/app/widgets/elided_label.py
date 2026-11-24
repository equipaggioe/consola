"""A label that shortens its text with «…» when it lacks room."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """A label that shortens its text with «…» when it lacks room.

    So many tabs fit in a narrow window, as a browser's do, and the
    endpoint fits beside the console's filters, instead of holding the
    window wider than the screen at 200 % (WCAG 1.4.4). Shortened, its
    tooltip has the whole text.
    """

    def __init__(self, keep: int = 4) -> None:
        """Build the empty label; it keeps at least `keep` letters."""
        super().__init__()
        self.full = ""
        self.keep = keep

    def set_full(self, text: str) -> None:
        """Show `text`, shortened if it does not fit."""
        self.full = text
        self.updateGeometry()
        self._fit()

    @override
    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self.full), super().sizeHint().height())

    @override
    def minimumSizeHint(self) -> QSize:
        width = self.fontMetrics().horizontalAdvance(self.full[: self.keep] + "…")
        return QSize(width, super().minimumSizeHint().height())

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit()

    @override
    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.updateGeometry()
            self._fit()

    def _fit(self) -> None:
        shown = self.fontMetrics().elidedText(self.full, Qt.TextElideMode.ElideRight, self.width())
        self.setText(shown)
        self.setToolTip(self.full if shown != self.full else "")
