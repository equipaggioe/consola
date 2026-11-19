"""Tabs that can be dragged to reorder them."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import (
    QAccessible,
    QAccessibleActionInterface,
    QAccessibleInterface,
    QAccessibleStateChangeEvent,
    QMouseEvent,
)
from PySide6.QtWidgets import QAccessibleWidget, QWidget

from app.widgets.reorderable_bar import ReorderableBar


class ReorderableTab(QWidget):
    """A tab that can be dragged to reorder it.

    Selection still happens on press, for an immediate response as in a
    browser; if the cursor moves beyond the threshold without releasing,
    the tab enters drag mode and the bar repositions it each time the
    cursor crosses the center of a neighbor.

    Whoever uses it has to call `_init_reorder()` in its __init__,
    delegate the three mouse events to `_reorder_press`, `_reorder_move`
    and `_reorder_release`, and have as a parent a `ReorderableBar`. Its
    accessible name is its title, and `set_active` changes `is_active`
    and calls `_announce_active`.
    """

    clicked = Signal()

    DRAG_THRESHOLD = 6
    is_active = False

    def _announce_active(self) -> None:
        """Tell assistive technology the tab was selected or left."""
        changed = QAccessible.State()
        # The stubs of PySide6 6.12 declare each state `...` with a
        # type comment, which Pyrefly does not read.
        changed.selected = True  # pyrefly: ignore[bad-assignment]
        QAccessible.updateAccessibility(QAccessibleStateChangeEvent(self, changed))

    def _init_reorder(self) -> None:
        self._drag_origin: QPointF | None = None
        self._is_dragging = False

    @property
    def is_dragging(self) -> bool:
        """Return whether the tab is being dragged."""
        return getattr(self, "_is_dragging", False)

    def _reorder_bar(self) -> ReorderableBar | None:
        """Walk up the parents to the one that knows how to reorder.

        The tabs' direct container is not always the one that holds the
        list: the sub-tabs live in a layout nested inside the panel.
        """
        node = self.parent()
        while node is not None:
            if isinstance(node, ReorderableBar):
                return node
            node = node.parent()
        return None

    def _reorder_press(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position()

    def _reorder_move(self, event: QMouseEvent) -> None:
        if self._drag_origin is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        bar = self._reorder_bar()
        if bar is None or len(bar.tabs) < 2:
            return

        if not self._is_dragging:
            if abs(event.position().x() - self._drag_origin.x()) < self.DRAG_THRESHOLD:
                return
            self._is_dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()
            self.update()

        # Cursor center in bar coordinates: the grabbed point's
        # position, not the edge's, so the tab does not jump when taken.
        pos_in_bar = self.mapToParent(event.position().toPoint())
        bar.reorder_to(self, bar.index_for_x(pos_in_bar.x(), self))

    def _reorder_release(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        if self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()


class _Accessible(QAccessibleWidget):
    """A tab as a page tab: selected if active, pressed like a click."""

    def __init__(self, tab: ReorderableTab) -> None:
        """Give the tab the page tab role."""
        super().__init__(tab, QAccessible.Role.PageTab)
        self.tab = tab

    @override
    def state(self) -> QAccessible.State:
        state = super().state()
        # The stubs of PySide6 6.12 declare each state `...` with a
        # type comment, which Pyrefly does not read.
        state.selectable = True  # pyrefly: ignore[bad-assignment]
        state.selected = self.tab.is_active  # pyrefly: ignore[bad-assignment]
        return state

    @override
    def actionNames(self) -> list[str]:
        return [QAccessibleActionInterface.pressAction(), *super().actionNames()]

    @override
    def doAction(self, actionName: str) -> None:
        if actionName == QAccessibleActionInterface.pressAction():
            self.tab.clicked.emit()
        else:
            super().doAction(actionName)


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of a tab, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, ReorderableTab) else None


QAccessible.installFactory(_interface)
