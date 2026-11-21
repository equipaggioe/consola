"""The menu of the window: it moves and resizes it with the keys."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QRect, QSize, Qt, Slot
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from app.services.announce import announce
from app.theme import Metrics


class WindowMenu(QMenu):
    """Restore, move, size, minimize, maximize and close the window.

    The window has no system frame (`Qt.FramelessWindowHint`), and the
    system menu that Qt shows on Alt+Space does not move it: the brand
    of the title bar opens this one, as the icon of a window opens the
    menu of Windows. «Mover» and «Tamaño» take the arrows, which move
    the window or its bottom right corner `Metrics.KEY_STEP` px; Enter
    leaves it there and Escape puts it back (WCAG 2.1.1). Under Wayland
    the system does not let a window place itself: moving does nothing.
    """

    def __init__(self, window: QWidget) -> None:
        """Build the menu of `window`."""
        super().__init__(window)
        self._window = window
        self._mode = ""
        self._start = QRect()
        texts = (
            ("restore", QCoreApplication.translate("WindowMenu", "Restaurar"), window.showNormal),
            ("move", QCoreApplication.translate("WindowMenu", "Mover"), self._move),
            ("size", QCoreApplication.translate("WindowMenu", "Tamaño"), self._size),
            ("min", QCoreApplication.translate("WindowMenu", "Minimizar"), window.showMinimized),
            ("max", QCoreApplication.translate("WindowMenu", "Maximizar"), window.showMaximized),
        )
        self._actions: dict[str, QAction] = {}
        for key, text, slot in texts:
            action = self.addAction(text)
            action.triggered.connect(slot)
            self._actions[key] = action
        self.addSeparator()
        self.addAction(QCoreApplication.translate("WindowMenu", "Cerrar")).triggered.connect(
            window.close
        )
        self.aboutToShow.connect(self._sync)

    @Slot()
    def _sync(self) -> None:
        """Enable what fits the state of the window, as Windows does."""
        maximized = self._window.isMaximized()
        self._actions["restore"].setEnabled(maximized)
        for key in ("move", "size", "max"):
            self._actions[key].setEnabled(not maximized)

    def open(self) -> None:
        """Show the menu under the left end of the window's top edge."""
        self.popup(self._window.mapToGlobal(QPoint(0, 0)))

    @Slot()
    def _move(self) -> None:
        self._begin(
            "move",
            QCoreApplication.translate(
                "WindowMenu", "Mover: las flechas mueven la ventana, Enter termina, Escape cancela"
            ),
        )

    @Slot()
    def _size(self) -> None:
        self._begin(
            "size",
            QCoreApplication.translate(
                "WindowMenu",
                "Tamaño: las flechas mueven la esquina de abajo a la derecha, Enter termina, "
                "Escape cancela",
            ),
        )

    def _begin(self, mode: str, help_text: str) -> None:
        """Take the arrows until Enter or Escape."""
        self._mode = mode
        self._start = self._window.geometry()
        app = QApplication.instance()
        assert app is not None
        app.installEventFilter(self)
        announce(self._window, help_text)

    def _end(self) -> None:
        self._mode = ""
        app = QApplication.instance()
        assert app is not None
        app.removeEventFilter(self)

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._mode:
            return False
        if event.type() == QEvent.Type.MouseButtonPress:
            self._end()
            return False
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return False
        step = Metrics.KEY_STEP
        arrows = {
            Qt.Key.Key_Left: QPoint(-step, 0),
            Qt.Key.Key_Right: QPoint(step, 0),
            Qt.Key.Key_Up: QPoint(0, -step),
            Qt.Key.Key_Down: QPoint(0, step),
        }
        key = Qt.Key(event.key())
        if key in arrows:
            delta = arrows[key]
            if self._mode == "move":
                self._window.move(self._window.pos() + delta)
            else:
                grown = self._window.size() + QSize(delta.x(), delta.y())
                self._window.resize(grown.expandedTo(self._window.minimumSizeHint()))
            return True
        if key == Qt.Key.Key_Escape:
            self._window.setGeometry(self._start)
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._end()
            return True
        return False
