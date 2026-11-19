"""The grip between two sections of the right column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette


class SectionResizeGrip(QWidget):
    """A thin bar between two open sections of the accordion.

    Dragging it shares the height by hand: what the upper section gains,
    the rest lose (`TabPanel._resize_section`). A double click returns
    to the automatic sharing. It shows only when there is something to
    negotiate with: its section open and at least one open below.
    """

    pressed = Signal()  # a drag starts: resync with reality
    # px moved since the last event (+ = grow the upper section)
    dragged = Signal(int)
    reset = Signal()

    HEIGHT = 7

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        self.setObjectName("sectionGrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.SplitVCursor)
        self.pal = NEUTRAL
        self._restyle()
        self._last_y: float | None = None

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        grip = theme.SECTION_GRIP.on(self.pal)
        self.setStyleSheet(f"""
            QWidget#sectionGrip {{
                background: {grip.bg};
                border-bottom: 1px solid {grip.border};
            }}
            QWidget#sectionGrip:hover {{ background: {grip.hover}; }}
        """)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_y = event.globalPosition().y()
            self.pressed.emit()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_y is None:
            return
        y = event.globalPosition().y()
        delta = int(y - self._last_y)
        if delta:
            self._last_y = y
            self.dragged.emit(delta)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_y = None

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.reset.emit()
