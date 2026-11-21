"""A splitter whose handles also move with the keyboard."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QWidget

from app.theme import Metrics


class Splitter(QSplitter):
    """A `QSplitter` whose handles take the focus of Tab.

    A handle of Qt only answers the mouse (WCAG 2.1.1). Here Tab
    reaches it, the arrows of its direction move it `Metrics.KEY_STEP`
    px, and with the focus it paints itself in Highlight. `name` says
    to assistive technology what it resizes.
    """

    def __init__(self, orientation: Qt.Orientation, name: str, parent: QWidget | None = None):
        """Build the splitter; its handles take `name`."""
        super().__init__(orientation, parent)
        self.name = name

    @override
    def createHandle(self) -> QSplitterHandle:
        handle = _Handle(self.orientation(), self)
        handle.setAccessibleName(self.name)
        return handle


class _Handle(QSplitterHandle):
    """A handle that moves with the arrows and shows its focus."""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        """Build the handle, reachable with Tab."""
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleDescription(
            QCoreApplication.translate("Splitter", "Las flechas mueven el separador")
        )

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        back, forth = (
            (Qt.Key.Key_Left, Qt.Key.Key_Right) if horizontal else (Qt.Key.Key_Up, Qt.Key.Key_Down)
        )
        step = {back: -Metrics.KEY_STEP, forth: Metrics.KEY_STEP}.get(Qt.Key(event.key()))
        if step is None:
            super().keyPressEvent(event)
            return
        here = self.pos().x() if horizontal else self.pos().y()
        self.moveSplitter(here + step)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        if not self.hasFocus():
            super().paintEvent(event)
            return
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Highlight))
        p.end()

    @override
    def focusInEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusInEvent(event)

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusOutEvent(event)
