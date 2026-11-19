"""A bar whose tabs can be dragged to reorder them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QBoxLayout, QWidget

if TYPE_CHECKING:
    from app.widgets.reorderable_tab import ReorderableTab


class ReorderableBar(QWidget):
    """The bar that holds draggable tabs.

    It expects `self.tabs`, the ordered list, and `self._tab_layout()`,
    the layout that holds them. `reorder_to` rebuilds the layout's
    order, so no index arithmetic can drift from the model.
    """

    tabs: list[Any]

    def _tab_layout(self) -> QBoxLayout:
        raise NotImplementedError

    def index_for_x(self, x: int, dragged: ReorderableTab) -> int:
        """Return where `dragged` should land if released at `x`."""
        target = len(self.tabs) - 1
        for i, tab in enumerate(self.tabs):
            if x < tab.x() + tab.width() / 2:
                target = i
                break
        return max(0, min(target, len(self.tabs) - 1))

    def reorder_to(self, tab: ReorderableTab, index: int) -> None:
        """Move a tab to that index."""
        if tab not in self.tabs:
            return
        current = self.tabs.index(tab)
        if index == current:
            return
        self.tabs.insert(index, self.tabs.pop(current))
        self._relayout_tabs()
        self.tabs_reordered()

    def _relayout_tabs(self) -> None:
        layout = self._tab_layout()
        for tab in self.tabs:
            layout.removeWidget(tab)
        for offset, tab in enumerate(self.tabs):
            layout.insertWidget(offset, tab)
        layout.activate()

    def tabs_reordered(self) -> None:
        """React to the new order: a hook, empty here."""
        pass
