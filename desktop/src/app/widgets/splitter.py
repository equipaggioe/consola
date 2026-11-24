"""A splitter whose line and grip are two widgets.

The handle of Qt is a line of 1 px that draws and does nothing else.
What one grabs is a grip of `Metrics.TARGET` px laid over the line,
transparent: it measures what WCAG 2.5.8 asks of a pointer without
opening a gap of 24 px between the panels.
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QChildEvent, QCoreApplication, QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtGui import (
    QAccessible,
    QAccessibleInterface,
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QResizeEvent,
)
from PySide6.QtWidgets import QAccessibleWidget, QSplitter, QSplitterHandle, QWidget

from app import theme
from app.theme import Metrics


class Splitter(QSplitter):
    """A `QSplitter` moved by grips that Tab reaches.

    Each handle is a line that answers nothing; its grip, `before` px
    over the first panel and the rest over the second, takes the mouse,
    the focus of Tab and the arrows of its direction, which move it
    `Metrics.KEY_STEP` px. `name` says to assistive technology what it
    resizes.
    """

    def __init__(
        self,
        orientation: Qt.Orientation,
        name: str,
        parent: QWidget | None = None,
        before: int = Metrics.TARGET // 2,
    ) -> None:
        """Build the splitter; its grips take `name`."""
        super().__init__(orientation, parent)
        self.name = name
        self.before = before
        self._grips: dict[QSplitterHandle, _Grip] = {}
        self.splitterMoved.connect(self.place_grips)

    @override
    def createHandle(self) -> QSplitterHandle:
        handle = _Line(self.orientation(), self)
        handle.installEventFilter(self)
        self._grips[handle] = _Grip(self, handle)
        return handle

    def move_line(self, handle: QSplitterHandle, pos: int) -> None:
        """Move a handle's line to `pos`, in the splitter's pixels."""
        self.moveSplitter(pos, self.indexOf(handle))

    def place_grips(self) -> None:
        """Lay each grip over its line, above the panels."""
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        for handle, grip in self._grips.items():
            line = handle.geometry().center()
            if horizontal:
                grip.setGeometry(line.x() - self.before, 0, Metrics.TARGET, self.height())
            else:
                grip.setGeometry(0, line.y() - self.before, self.width(), Metrics.TARGET)
            grip.setVisible(not handle.isHidden())
            grip.raise_()

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched in self._grips and event.type() in (
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            self.place_grips()
        return super().eventFilter(watched, event)

    @override
    def childEvent(self, event: QChildEvent) -> None:
        super().childEvent(event)
        # A panel added later is stacked above the grips.
        if event.type() == QEvent.Type.ChildPolished:
            self.place_grips()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.place_grips()


class _Line(QSplitterHandle):
    """The handle: it draws the line and answers neither mouse nor Tab.

    Disabled, so it is no target: its grip is.
    """

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        """Build the line."""
        super().__init__(orientation, parent)
        self.setEnabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class _Grip(QWidget):
    """What one grabs to move a line: transparent, save its focus."""

    def __init__(self, splitter: Splitter, handle: QSplitterHandle) -> None:
        """Build the grip of a handle, reachable with Tab."""
        super().__init__(splitter)
        self.splitter = splitter
        self.handle = handle
        self._grab: int | None = None
        horizontal = splitter.orientation() == Qt.Orientation.Horizontal
        self.setCursor(Qt.CursorShape.SplitHCursor if horizontal else Qt.CursorShape.SplitVCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(splitter.name)
        self.setAccessibleDescription(
            QCoreApplication.translate("Splitter", "Las flechas mueven el separador")
        )

    def _along(self, point: QPoint) -> int:
        """Return a point of the splitter on the axis the line moves."""
        horizontal = self.splitter.orientation() == Qt.Orientation.Horizontal
        return point.x() if horizontal else point.y()

    def _line(self) -> int:
        """Return where the line is.

        The middle of the handle: Qt widens a handle of 1 px to 5, two
        on each side, but moves it by the line.
        """
        return self._along(self.handle.geometry().center())

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        where = self._along(self.mapTo(self.splitter, event.position().toPoint()))
        self._grab = where - self._line()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._grab is None:
            super().mouseMoveEvent(event)
            return
        where = self._along(self.mapTo(self.splitter, event.position().toPoint()))
        self.splitter.move_line(self.handle, where - self._grab)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._grab = None
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        horizontal = self.splitter.orientation() == Qt.Orientation.Horizontal
        back, forth = (
            (Qt.Key.Key_Left, Qt.Key.Key_Right) if horizontal else (Qt.Key.Key_Up, Qt.Key.Key_Down)
        )
        step = {back: -Metrics.KEY_STEP, forth: Metrics.KEY_STEP}.get(Qt.Key(event.key()))
        if step is None:
            super().keyPressEvent(event)
            return
        self.splitter.move_line(self.handle, self._line() + step)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        # Nothing but the focus: the line is the handle's.
        if not self.hasFocus():
            return
        p = QPainter(self)
        theme.ring(p, QRectF(self.rect()), self.palette().color(QPalette.ColorRole.Highlight))
        p.end()

    @override
    def focusInEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusInEvent(event)

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusOutEvent(event)


class _Accessible(QAccessibleWidget):
    """A grip as what it is to assistive technology: a grip."""

    def __init__(self, grip: _Grip) -> None:
        """Give the grip the grip role."""
        super().__init__(grip, QAccessible.Role.Grip)


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of a grip, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, _Grip) else None


QAccessible.installFactory(_interface)
