"""A multi-line field whose height grows with what is written."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, Slot
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QPlainTextEdit, QWidget

# It starts at two lines, grows with what is written up to ten, and
# from there it scrolls.
MIN_ROWS = 2
MAX_ROWS = 10


class GrowField(QPlainTextEdit):
    """A QPlainTextEdit as tall as its text, plus one empty line.

    That extra line says «this is all»: a field ending exactly on the
    last entry cannot be told from one cutting off the rest, and an
    entry out of view becomes a deploy without its secret. With three
    lines written it shows four.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        """Build the field and fit it to its text."""
        super().__init__(text, parent)
        self.textChanged.connect(self._fit)
        self._fit()

    @override
    def setPlainText(self, text: str) -> None:
        super().setPlainText(text)
        self._fit()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        # Narrowing the field changes where each long line breaks, and
        # so how many lines the same text takes.
        super().resizeEvent(event)
        self._fit()

    @override
    def changeEvent(self, event: QEvent) -> None:
        # Another font changes the height of each line.
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._fit()

    @Slot()
    def _fit(self) -> None:
        # A QPlainTextEdit's `documentSize()` counts LINES, not pixels,
        # and counts those visible: a long path broken in two takes two.
        doc = self.document()
        doc.setTextWidth(max(1, self.viewport().width()))
        written = max(1, int(doc.size().height()))
        rows = min(max(written + 1, MIN_ROWS), MAX_ROWS)
        height = (
            rows * self.fontMetrics().lineSpacing()
            + 2 * int(doc.documentMargin())
            + 2 * self.frameWidth()
        )
        if self.height() != height:
            self.setFixedHeight(height)
