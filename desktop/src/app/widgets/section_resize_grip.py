"""The grip between two sections of the right column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QCoreApplication, QObject, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAccessible,
    QAccessibleInterface,
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
)
from PySide6.QtWidgets import QAccessibleWidget, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Metrics


class SectionResizeGrip(QWidget):
    """A thin bar between two open sections of the accordion.

    Dragging it shares the height by hand: what the upper section gains,
    the rest lose (`TabPanel._resize_section`). A double click returns
    to the automatic sharing. It shows only when there is something to
    negotiate with: its section open and at least one open below.

    With the keyboard, Tab reaches it, the up and down arrows move it
    `Metrics.KEY_STEP` px and Enter does what the double click does.
    """

    pressed = Signal()  # a drag starts: resync with reality
    # px moved since the last event (+ = grow the upper section)
    dragged = Signal(int)
    reset = Signal()

    # What one grabs measures the target of WCAG 2.5.8; what shows is a
    # line in its middle.
    HEIGHT = Metrics.TARGET

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        # Repainted when the cursor comes in or goes out.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.SplitVCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleDescription(
            QCoreApplication.translate(
                "SectionResizeGrip",
                "Las flechas arriba y abajo cambian el alto; Enter vuelve al reparto automático",
            )
        )
        self.pal = NEUTRAL
        self._restyle()
        self._last_y: float | None = None

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        theme.SECTION_GRIP.on(self.pal).dress(self, fill=False)
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the body's color, or the hover's, and a line across."""
        colors = self.palette()
        p = QPainter(self)
        fill = QPalette.ColorRole.Midlight if self.underMouse() else QPalette.ColorRole.Window
        p.fillRect(self.rect(), colors.color(fill))
        p.fillRect(0, self.height() // 2, self.width(), 1, colors.color(QPalette.ColorRole.Dark))
        if self.hasFocus():
            theme.ring(p, QRectF(self.rect()), colors.color(QPalette.ColorRole.Highlight), 0)
        p.end()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        steps = {Qt.Key.Key_Up: -Metrics.KEY_STEP, Qt.Key.Key_Down: Metrics.KEY_STEP}
        if event.key() in steps:
            self.pressed.emit()
            self.dragged.emit(steps[Qt.Key(event.key())])
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.reset.emit()
        else:
            super().keyPressEvent(event)

    @override
    def focusInEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusInEvent(event)

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusOutEvent(event)

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


class _Accessible(QAccessibleWidget):
    """The grip as what it is: a handle that resizes."""

    def __init__(self, grip: SectionResizeGrip) -> None:
        """Give the grip the grip role."""
        super().__init__(grip, QAccessible.Role.Grip)


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of a grip, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, SectionResizeGrip) else None


QAccessible.installFactory(_interface)
