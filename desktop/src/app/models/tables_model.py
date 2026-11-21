"""The model of the database explorer's tree of tables."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any, overload, override

from PySide6.QtCore import (
    QAbstractItemModel,
    QCoreApplication,
    QLocale,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QBrush, QFont

from app.services import db_explorer as dbx
from app.services import db_models as dbm
from app.services.files import human_size
from app.services.language import QT_TRANSLATE_NOOP
from app.theme import Colors

type Entry = dbx.Relation | dbm.ModelTable

_GLYPHS = {"v": "◇ ", "m": "◈ ", "f": "⇢ "}
# Each state against the models in words, for assistive technology:
# the marks and colors say it only to the eye.
_STATES = {
    dbm.MISSING: QT_TRANSLATE_NOOP("tables_model", "falta en la base"),
    dbm.CHANGED: QT_TRANSLATE_NOOP("tables_model", "difiere de su modelo"),
    dbm.UNMODELED: QT_TRANSLATE_NOOP("tables_model", "sin modelo"),
}
_GROUPS = {
    "schema": QT_TRANSLATE_NOOP("tables_model", "esquema"),
    "folder": QT_TRANSLATE_NOOP("tables_model", "carpeta de modelos"),
    "unmodeled": QT_TRANSLATE_NOOP("tables_model", "tablas sin modelo"),
}
_HEADERS = (QT_TRANSLATE_NOOP("tables_model", "Tabla"), QT_TRANSLATE_NOOP("tables_model", "Filas"))


@dataclass(eq=False)
class _Node:
    """A row of the tree: a group, a relation or a missing model."""

    parent: _Node | None
    row: int
    children: list[_Node] = field(default_factory=list)
    entry: Entry | None = None
    group: str = ""  # key of a schema or folder
    label: str = ""  # a group's text
    partitions: int = 0
    status: dbm.TableStatus | None = None
    show_schema: bool = False

    def add(self, **kwargs: Any) -> _Node:
        """Append a child and return it."""
        child = _Node(self, len(self.children), **kwargs)
        self.children.append(child)
        return child


class TablesModel(QAbstractItemModel):
    """The tables, by schema or by their model's folder.

    The folder is the model's in `app/models/`. By models whenever
    they could be read; by schemas is the fallback while they load or
    if they cannot be imported (ADR-0015).
    """

    # Mark and color of each state against the models (ADR-0015).
    MARKS = {
        dbm.MISSING: ("✕ ", Colors.ERROR),
        dbm.CHANGED: ("≠ ", Colors.WARNING),
        dbm.UNMODELED: ("+ ", Colors.TERTIARY),
    }

    def __init__(self, locale: QLocale, parent: QObject | None = None) -> None:
        """Start empty, with the numbers of the view's `locale`."""
        super().__init__(parent)
        self.locale = locale
        self._root = _Node(None, 0)
        self._by_name: dict[str, _Node] = {}

    def set_tables(self, relations: list[dbx.Relation], comparison: dbm.Comparison | None) -> None:
        """Rebuild the tree from the catalog and the comparison."""
        self.beginResetModel()
        self._root = _Node(None, 0)
        self._by_name = {}
        _Builder(self._root, self._by_name, relations, comparison).build()
        self.endResetModel()

    def entry(self, index: QModelIndex | QPersistentModelIndex) -> Entry | None:
        """Return the relation or the missing model of a row."""
        return self._node(index).entry if index.isValid() else None

    def group(self, index: QModelIndex | QPersistentModelIndex) -> str:
        """Return the key of a group's row, or '' for any other row."""
        return self._node(index).group if index.isValid() else ""

    def index_of(self, qualified: str) -> QModelIndex:
        """Return the row of `schema.table`, invalid if absent."""
        node = self._by_name.get(qualified)
        return QModelIndex() if node is None else self.createIndex(node.row, 0, node)

    def _node(self, index: QModelIndex | QPersistentModelIndex) -> _Node:
        # The node an index points to; the root for an invalid one.
        return index.internalPointer() if index.isValid() else self._root

    # --- QAbstractItemModel ---
    @override
    def index(
        self, row: int, column: int, parent: QModelIndex | QPersistentModelIndex = QModelIndex()
    ) -> QModelIndex:
        node = self._node(parent)
        if not 0 <= row < len(node.children) or not 0 <= column < len(_HEADERS):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    @overload
    def parent(self) -> QObject | None: ...

    @overload
    def parent(self, child: QModelIndex | QPersistentModelIndex, /) -> QModelIndex: ...

    @override
    def parent(
        self, child: QModelIndex | QPersistentModelIndex | None = None, /
    ) -> QObject | QModelIndex | None:
        if child is None:
            return super().parent()  # the QObject's
        if not child.isValid():
            return QModelIndex()
        up = self._node(child).parent
        if up is None or up is self._root:
            return QModelIndex()
        return self.createIndex(up.row, 0, up)

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid() and parent.column() != 0:
            return 0
        return len(self._node(parent).children)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(_HEADERS)

    @override
    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return QCoreApplication.translate("tables_model", _HEADERS[section])
        return None

    @override
    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid():
            return None
        node = self._node(index)
        if node.entry is None:
            return _group_data(node, index.column(), role)
        if isinstance(node.entry, dbm.ModelTable):
            return _missing_data(node.entry, index.column(), role)
        return self._relation_data(node, node.entry, index.column(), role)

    def _relation_data(self, node: _Node, rel: dbx.Relation, column: int, role: int) -> Any:
        # What a relation's row shows: name and estimate, colored by
        # its state against the models.
        status = node.status
        mark, mark_color = self.MARKS.get(status.status, ("", "")) if status else ("", "")
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 1:
                return "" if rel.kind == "v" else dbx.human_count(rel.estimate, self.locale)
            schema = node.show_schema and rel.schema != dbm.DEFAULT_SCHEMA
            extra = f"  ({node.partitions})" if node.partitions else ""
            return (
                f"{mark}{_GLYPHS.get(rel.kind, '')}{rel.qualified if schema else rel.name}{extra}"
            )
        if role == Qt.ItemDataRole.ForegroundRole:
            if column == 1:
                return QBrush(Colors.ON_SURFACE_VARIANT)
            if not rel.readable:
                return QBrush(Colors.ON_SURFACE_VARIANT)
            if mark:
                return QBrush(mark_color)
            if rel.kind in ("v", "m", "f") or rel.extension:
                return QBrush(Colors.ON_SURFACE_VARIANT)
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
            return int(Qt.AlignmentFlag.AlignRight)
        if role == Qt.ItemDataRole.ToolTipRole and column == 0:
            return self._relation_tip(rel, status)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            if column == 1:
                return (
                    ""
                    if rel.kind == "v"
                    else QCoreApplication.translate("TablesModel", "unas {0} filas").format(
                        self._count(rel)
                    )
                )
            schema = node.show_schema and rel.schema != dbm.DEFAULT_SCHEMA
            return rel.qualified if schema else rel.name
        if role == Qt.ItemDataRole.AccessibleDescriptionRole:
            return self._relation_about(node, rel)
        return None

    def _count(self, rel: dbx.Relation) -> str:
        # The estimate of rows, as short text.
        return dbx.human_count(rel.estimate, self.locale)

    def _relation_about(self, node: _Node, rel: dbx.Relation) -> str:
        # The relation in words: kind, partitions, state and access.
        about = [rel.kind_label]
        if node.partitions:
            about.append(
                QCoreApplication.translate("TablesModel", "{0} particiones").format(
                    node.partitions
                )
            )
        if node.status is not None and node.status.status in _STATES:
            about.append(QCoreApplication.translate("tables_model", _STATES[node.status.status]))
        if not rel.readable:
            about.append(
                QCoreApplication.translate("TablesModel", "el rol de la app no tiene SELECT")
            )
        return ", ".join(about)

    def _relation_tip(self, rel: dbx.Relation, status: dbm.TableStatus | None) -> str:
        # The relation's tooltip: kind, estimate, size, comment, model
        # and how it differs from it.
        tip = [f"<b>{rel.qualified}</b> · {rel.kind_label}"]
        if rel.kind not in ("v",):
            size = human_size(rel.size_bytes, self.locale)
            tip.append(
                QCoreApplication.translate("TablesModel", "~{0} filas · {1}").format(
                    self._count(rel), size
                )
            )
        if rel.comment:
            tip.append(html.escape(rel.comment, quote=False))
        if status is not None and status.model is not None:
            tip.append(
                QCoreApplication.translate("TablesModel", "Modelo: app/models/{0}").format(
                    status.model.source
                )
            )
        if not rel.readable:
            tip.append(
                QCoreApplication.translate(
                    "TablesModel",
                    "<span style='color:{0};'>El rol de la app no tiene SELECT</span>",
                ).format(Colors.WARNING)
            )
        if status is not None and status.status == dbm.CHANGED:
            lines = [html.escape(d.text, quote=False) for d in status.diffs[:12]]
            if len(status.diffs) > 12:
                lines.append(
                    QCoreApplication.translate("TablesModel", "… y {0} más").format(
                        len(status.diffs) - 12
                    )
                )
            tip.append(
                QCoreApplication.translate(
                    "TablesModel", "<span style='color:{0};'>Difiere de su modelo:</span><br>"
                ).format(Colors.WARNING)
                + "<br>".join(lines)
            )
        elif status is not None and status.status == dbm.UNMODELED:
            tip.append(
                QCoreApplication.translate(
                    "TablesModel",
                    "<span style='color:{0};'>Ningún modelo declara esta tabla</span>",
                ).format(Colors.TERTIARY)
            )
        return "<br>".join(tip)


class _Builder:
    """Lays out the tree's nodes from the catalog and the comparison."""

    def __init__(
        self,
        root: _Node,
        by_name: dict[str, _Node],
        relations: list[dbx.Relation],
        comparison: dbm.Comparison | None,
    ) -> None:
        """Keep what the tree is built from."""
        self.root = root
        self.by_name = by_name
        self.relations = relations
        self.comparison = comparison
        self.by_models = comparison is not None
        self.groups: dict[str, _Node] = {}

    def build(self) -> None:
        """Add the groups, the tables and their partitions."""
        children: dict[str, int] = {}
        for rel in self.relations:
            if rel.parent:
                key = f"{rel.schema}.{rel.parent}"
                children[key] = children.get(key, 0) + 1

        # What goes in the tree: relations that are not partitions and
        # models whose table is missing from the database. By models,
        # folders go before the root's loose files, as on disk, and what
        # has no model goes last.
        entries: list[tuple[tuple[Any, ...], Entry]] = []
        for rel in self.relations:
            if not rel.parent:
                status = self._status_of(rel.qualified)
                model = status.model if status else None
                entries.append((self._order(rel.schema, rel.name, model), rel))
        if self.comparison is not None:
            for model in self.comparison.missing():
                entries.append((self._order(model.schema, model.name, model), model))
        entries.sort(key=lambda pair: pair[0])

        for _order, entry in entries:
            if isinstance(entry, dbm.ModelTable):
                parent = self._container(entry.schema, entry) or self.root
                node = parent.add(entry=entry)
            else:
                status = self._status_of(entry.qualified)
                parent = self._container(entry.schema, status.model if status else None)
                node = (parent or self.root).add(
                    entry=entry,
                    partitions=children.get(entry.qualified, 0),
                    status=status,
                    show_schema=self.by_models,
                )
            self.by_name[entry.qualified] = node

        for rel in self.relations:
            owner = self.by_name.get(f"{rel.schema}.{rel.parent}") if rel.parent else None
            if owner is not None:
                self.by_name[rel.qualified] = owner.add(entry=rel)

    def _status_of(self, qualified: str) -> dbm.TableStatus | None:
        # The table's state against the models, if they could be read.
        return self.comparison.tables.get(qualified) if self.comparison else None

    def _order(self, schema: str, name: str, model: dbm.ModelTable | None) -> tuple[Any, ...]:
        # The sort key of an entry, by schema or by model folder.
        if not self.by_models:
            return (schema, name)
        if model is None:
            return (2, "", schema, name)
        return (0 if model.folder else 1, model.folder, schema, name)

    def _group(self, key: str, label: str, parent: _Node) -> _Node:
        # The group with that key, created under `parent` if new.
        if key not in self.groups:
            self.groups[key] = parent.add(group=key, label=label)
        return self.groups[key]

    def _container(self, schema: str, model: dbm.ModelTable | None) -> _Node | None:
        # The group an entry hangs from; None at the root of app/models.
        if not self.by_models:
            return self._group(f"schema:{schema}", schema, self.root)
        if model is None:
            return self._group(
                "unmodeled", QCoreApplication.translate("_Builder", "sin modelo"), self.root
            )
        node, path = None, ""
        for part in filter(None, model.folder.split("/")):
            path = f"{path}/{part}" if path else part
            node = self._group(f"folder:{path}", f"{part}/", node or self.root)
        return node


def _group_data(node: _Node, column: int, role: int) -> Any:
    """Return what a group's row shows: its name, bold and dim."""
    if column != 0:
        return "" if role == Qt.ItemDataRole.DisplayRole else None
    if role == Qt.ItemDataRole.DisplayRole:
        return node.label
    if role == Qt.ItemDataRole.ForegroundRole:
        return QBrush(Colors.ON_SURFACE_VARIANT)
    if role == Qt.ItemDataRole.FontRole:
        font = QFont()
        font.setBold(True)
        return font
    if role == Qt.ItemDataRole.AccessibleTextRole:
        return node.label
    if role == Qt.ItemDataRole.AccessibleDescriptionRole:
        return QCoreApplication.translate("tables_model", _GROUPS[node.group.split(":")[0]])
    return None


def _missing_data(model: dbm.ModelTable, column: int, role: int) -> Any:
    """Return what a missing model's row shows: name and «falta»."""
    mark, color = TablesModel.MARKS[dbm.MISSING]
    if role == Qt.ItemDataRole.DisplayRole:
        return (
            QCoreApplication.translate("tables_model", "falta")
            if column == 1
            else f"{mark}{model.name}"
        )
    if role == Qt.ItemDataRole.ForegroundRole:
        return QBrush(color)
    if role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
        return int(Qt.AlignmentFlag.AlignRight)
    if role == Qt.ItemDataRole.AccessibleTextRole:
        return QCoreApplication.translate("tables_model", "falta") if column == 1 else model.name
    if role == Qt.ItemDataRole.AccessibleDescriptionRole:
        return QCoreApplication.translate("tables_model", "{0}: está en app/models/{1}").format(
            QCoreApplication.translate("tables_model", _STATES[dbm.MISSING]), model.source
        )
    if role == Qt.ItemDataRole.ToolTipRole and column == 0:
        return QCoreApplication.translate(
            "tables_model",
            "<b>{0}</b><br>Modelo: app/models/{1}<br><span style='color:{2};'>Está "
            "en los modelos y no en la base: falta migrar</span>",
        ).format(model.qualified, model.source, color)
    return None
