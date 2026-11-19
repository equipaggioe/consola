"""The model of the rows the database explorer shows."""

from __future__ import annotations

import json
from typing import Any, override

from PySide6.QtCore import (
    QAbstractTableModel,
    QLocale,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont

from app.services import db_explorer as dbx
from app.services.files import human_size
from app.theme import Colors

NUMERIC_TYPES = {"int2", "int4", "int8", "numeric", "float4", "float8", "money", "oid"}
JSON_TYPES = {"json", "jsonb"}


# --- data model ---


class RowsModel(QAbstractTableModel):
    """A table's rows, page by page.

    `fetchMore` does not query: it asks the worker, and rows enter when
    the answer arrives (`append`).
    """

    more_requested = Signal()

    def __init__(self, locale: QLocale, parent: QObject | None = None) -> None:
        """Start empty, with the numbers of the view's `locale`."""
        super().__init__(parent)
        self.locale = locale
        self.detail: dbx.TableDetail | None = None
        self.rows: list[tuple[Any, ...]] = []
        self.has_more = False
        self.loading = False
        self.order_by: str | None = None
        self.descending = False

    def reset(self, detail: dbx.TableDetail | None) -> None:
        """Start over with another table."""
        self.beginResetModel()
        self.detail = detail
        self.rows = []
        self.has_more = False
        self.loading = False
        self.endResetModel()

    def append(self, page: dbx.Page) -> None:
        """Add a page of rows."""
        self.loading = False
        if not page.rows:
            self.has_more = False
            return
        start = len(self.rows)
        self.beginInsertRows(QModelIndex(), start, start + len(page.rows) - 1)
        self.rows.extend(page.rows)
        self.endInsertRows()
        self.has_more = page.has_more

    # --- QAbstractTableModel ---
    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() or self.detail is None else len(self.detail.columns)

    @override
    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and self.has_more and not self.loading

    @override
    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> None:
        if self.canFetchMore(parent):
            self.loading = True
            self.more_requested.emit()

    @override
    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole:
                return section + 1
            return None
        if self.detail is None or section >= len(self.detail.columns):
            return None
        col = self.detail.columns[section]
        if role == Qt.ItemDataRole.DisplayRole:
            mark = "🔑 " if col.pk else ("↗ " if col.fk else "")
            order = ""
            if col.name == self.order_by:
                order = "  ▼" if self.descending else "  ▲"
            return f"{mark}{col.name}{order}"
        if role == Qt.ItemDataRole.ToolTipRole:
            parts = [f"<b>{col.name}</b> · {col.type}"]
            if col.fk:
                parts.append(f"→ {col.fk.ref_schema}.{col.fk.ref_table}.{col.fk.ref_columns[0]}")
            if col.comment:
                parts.append(col.comment)
            parts.append(
                f"<span style='color:{Colors.TEXT_MUTED};'>Clic para ordenar en el servidor</span>"
            )
            return "<br>".join(parts)
        return None

    @override
    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid() or self.detail is None:
            return None
        value = self.rows[index.row()][index.column()]
        col = self.detail.columns[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return "NULL"
            if col.base_type == dbx.BYTEA:
                return f"‹bytea {human_size(int(value), self.locale)}›"
            text = value if len(value) <= dbx.CELL_CHARS else value[: dbx.CELL_CHARS] + "…"
            return text.replace("\r\n", " ⏎ ").replace("\n", " ⏎ ")
        if role == Qt.ItemDataRole.ToolTipRole:
            if value is None or col.base_type == dbx.BYTEA:
                return None
            if col.base_type in JSON_TYPES and len(value) <= dbx.CELL_CHARS:
                try:
                    return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
                except ValueError:
                    pass
            if len(value) > 60 or "\n" in value:
                return value if len(value) <= dbx.CELL_CHARS else value[: dbx.CELL_CHARS] + "…"
            if col.fk:
                return f"Doble clic para ir a {col.fk.ref_table}"
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            if value is None or col.base_type == dbx.BYTEA:
                return QColor(Colors.TEXT_MUTED)
            if col.fk:
                return QColor(Colors.ACCENT)
            return None
        if role == Qt.ItemDataRole.FontRole:
            if value is None:
                font = QFont()
                font.setItalic(True)
                return font
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col.base_type in NUMERIC_TYPES and value is not None:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None
