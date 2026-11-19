"""The model of a table of the explorer's structure tabs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, override

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QFont

from app.theme import mono


class StructureModel(QAbstractTableModel):
    """Rows of text under their headers, read-only.

    Columns, indexes, constraints, who points to the table and how it
    differs from its model. The first column is a name, and goes in the
    fixed-width font.
    """

    def __init__(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        parent: QObject | None = None,
    ) -> None:
        """Keep the headers and the rows."""
        super().__init__(parent)
        self.headers = list(headers)
        self.rows = [list(row) for row in rows]

    # --- QAbstractTableModel ---
    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.headers)

    @override
    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return section + 1
        return self.headers[section]

    @override
    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            return value if len(value) > 40 else None
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return value or "vacío"
        if role == Qt.ItemDataRole.AccessibleDescriptionRole:
            return self.headers[index.column()]
        if role == Qt.ItemDataRole.FontRole and index.column() == 0:
            return mono(QFont())
        return None
