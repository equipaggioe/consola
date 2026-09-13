from __future__ import annotations
import json

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSplitter, QTableView, QTableWidget, QTableWidgetItem, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
)

from core import db_explorer as dbx
from core.files import human_size
from ui.db_worker import DbWorker
from ui.theme import Colors, Fonts

"""
La vista de la pestana «Explorar base» (docs/explorador-db.md 6).

Arbol de esquemas y tablas a la izquierda; a la derecha, Datos (paginado,
ordenado en el servidor) y Estructura (columnas, indices, constraints y quien
apunta a esta tabla). Solo muestra: la conexion es de solo lectura y aqui no
hay nada que escriba.

No consulta nada por su cuenta: todo pasa por `DbWorker`, que responde con el
id del pedido. Una respuesta cuyo id ya no es el que la vista espera se tira.
"""

NUMERIC_TYPES = {'int2', 'int4', 'int8', 'numeric', 'float4', 'float8', 'money', 'oid'}
JSON_TYPES = {'json', 'jsonb'}
_ROLE_REL = Qt.ItemDataRole.UserRole


# --- modelo de datos -----------------------------------------------------------

class RowsModel(QAbstractTableModel):
    """Filas de una tabla, pagina a pagina. `fetchMore` no consulta: pide al
    worker, y las filas entran cuando la respuesta llega (`append`)."""
    more_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.detail: dbx.TableDetail | None = None
        self.rows: list[tuple] = []
        self.has_more = False
        self.loading = False
        self.order_by: str | None = None
        self.descending = False

    def reset(self, detail: dbx.TableDetail | None) -> None:
        self.beginResetModel()
        self.detail = detail
        self.rows = []
        self.has_more = False
        self.loading = False
        self.endResetModel()

    def append(self, page: dbx.Page) -> None:
        self.loading = False
        if not page.rows:
            self.has_more = False
            return
        start = len(self.rows)
        self.beginInsertRows(QModelIndex(), start, start + len(page.rows) - 1)
        self.rows.extend(page.rows)
        self.endInsertRows()
        self.has_more = page.has_more

    # --- QAbstractTableModel ------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() or self.detail is None else len(self.detail.columns)

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        return not parent.isValid() and self.has_more and not self.loading

    def fetchMore(self, parent=QModelIndex()) -> None:
        if self.canFetchMore(parent):
            self.loading = True
            self.more_requested.emit()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole:
                return section + 1
            return None
        if self.detail is None or section >= len(self.detail.columns):
            return None
        col = self.detail.columns[section]
        if role == Qt.ItemDataRole.DisplayRole:
            marca = '🔑 ' if col.pk else ('↗ ' if col.fk else '')
            orden = ''
            if col.name == self.order_by:
                orden = '  ▼' if self.descending else '  ▲'
            return f'{marca}{col.name}{orden}'
        if role == Qt.ItemDataRole.ToolTipRole:
            partes = [f'<b>{col.name}</b> · {col.type}']
            if col.fk:
                partes.append(f'→ {col.fk.ref_schema}.{col.fk.ref_table}'
                              f'.{col.fk.ref_columns[0]}')
            if col.comment:
                partes.append(col.comment)
            partes.append(f"<span style='color:{Colors.TEXT_MUTED};'>"
                          'Clic para ordenar en el servidor</span>')
            return '<br>'.join(partes)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.rows[index.row()][index.column()]
        col = self.detail.columns[index.column()]

        if role == Qt.ItemDataRole.DisplayRole:
            if value is None:
                return 'NULL'
            if col.base_type == dbx.BYTEA:
                return f'‹bytea {human_size(int(value))}›'
            text = value if len(value) <= dbx.CELL_CHARS else value[:dbx.CELL_CHARS] + '…'
            return text.replace('\r\n', ' ⏎ ').replace('\n', ' ⏎ ')
        if role == Qt.ItemDataRole.ToolTipRole:
            if value is None or col.base_type == dbx.BYTEA:
                return None
            if col.base_type in JSON_TYPES and len(value) <= dbx.CELL_CHARS:
                try:
                    return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
                except ValueError:
                    pass
            if len(value) > 60 or '\n' in value:
                return value if len(value) <= dbx.CELL_CHARS else value[:dbx.CELL_CHARS] + '…'
            if col.fk:
                return f'Doble clic para ir a {col.fk.ref_table}'
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


# --- vista -----------------------------------------------------------------------

class DbExplorerView(QWidget):
    """Arbol + (Datos | Estructura), sobre un `DbWorker` propio."""

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.setObjectName('dbExplorer')
        self._relations: list[dbx.Relation] = []
        self._detail: dbx.TableDetail | None = None
        # Miga de pan: cada paso es una tabla con el filtro con que se llego.
        self._trail: list[tuple[dbx.Relation, dbx.Filter]] = []
        self._pending: dict[str, int] = {}   # tipo de pedido -> id que se espera
        self._exact: int | None = None

        self.worker = DbWorker(url)
        self.worker.result.connect(self._on_result)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

        self._build()
        self.refresh()

    # --- construccion ------------------------------------------------------------
    def _build(self) -> None:
        self.setStyleSheet(f"""
            QWidget#dbExplorer {{ background: {Colors.BG}; }}
            QTreeWidget, QTableView, QTableWidget {{
                background: {Colors.BG}; color: {Colors.TEXT};
                border: none; font-size: {Fonts.SIZE_SM}px;
                selection-background-color: {Colors.SURFACE_HOVER};
                selection-color: {Colors.TEXT};
                gridline-color: {Colors.SURFACE};
                alternate-background-color: #11161e;
            }}
            QHeaderView::section {{
                background: {Colors.SURFACE}; color: {Colors.TEXT_DIM};
                border: none; border-right: 1px solid {Colors.BORDER};
                border-bottom: 1px solid {Colors.BORDER};
                padding: 4px 8px; font-size: {Fonts.SIZE_XS}px;
            }}
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: transparent; color: {Colors.TEXT_DIM};
                padding: 6px 14px; border: none; font-size: {Fonts.SIZE_SM}px;
            }}
            QTabBar::tab:selected {{ color: {Colors.TEXT}; border-bottom: 2px solid {Colors.ACCENT}; }}
            QLineEdit {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER}; border-radius: 6px;
                padding: 5px 8px; font-size: {Fonts.SIZE_SM}px;
            }}
            QScrollArea {{ border: none; background: transparent; }}
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(3)
        root.addWidget(splitter)

        # Izquierda: filtro + arbol.
        left = QWidget()
        left.setStyleSheet(f'background: {Colors.BG}; border-right: 1px solid {Colors.BORDER};')
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText('Filtrar tablas…')
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.textChanged.connect(self._apply_tree_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setIndentation(14)
        self.tree.setStyleSheet('border: none;')
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.itemClicked.connect(self._on_tree_clicked)
        self.tree.currentItemChanged.connect(lambda item, _prev: self._on_tree_clicked(item))
        ll.addWidget(self.filter_box)
        ll.addWidget(self.tree, 1)
        splitter.addWidget(left)

        # Derecha: cabecera + miga + pestanas.
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        head = QWidget()
        head.setStyleSheet(f'background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};')
        hl = QVBoxLayout(head)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.title = QLabel('Elige una tabla')
        self.title.setStyleSheet(
            f'background: transparent; color: {Colors.TEXT}; font-size: {Fonts.SIZE_BASE}px; font-weight: 600;')
        self.subtitle = QLabel('')
        self.subtitle.setStyleSheet(
            f'background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;')
        self.count_btn = self._chip('Contar', 'Contar las filas exactas (COUNT(*))', self._count)
        self.count_btn.setEnabled(False)
        top.addWidget(self.title)
        top.addWidget(self.subtitle)
        top.addStretch()
        top.addWidget(self.count_btn)
        hl.addLayout(top)

        self.trail_row = QHBoxLayout()
        self.trail_row.setSpacing(4)
        self.trail_wrap = QWidget()
        self.trail_wrap.setStyleSheet('background: transparent;')
        self.trail_wrap.setLayout(self.trail_row)
        self.trail_row.setContentsMargins(0, 0, 0, 0)
        self.trail_wrap.setVisible(False)
        hl.addWidget(self.trail_wrap)

        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        hl.addWidget(self.status)
        rl.addWidget(head)

        self.tabs = QTabWidget()
        self.model = RowsModel(self)
        self.model.more_requested.connect(self._request_more)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().setStyleSheet(
            f'QHeaderView::section {{ color: {Colors.TEXT_MUTED}; padding: 0 6px; }}')
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self._on_sort)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.doubleClicked.connect(self._on_cell_double_clicked)
        self.tabs.addTab(self.table, 'Datos')

        self.structure = QWidget()
        self.structure_layout = QVBoxLayout(self.structure)
        self.structure_layout.setContentsMargins(12, 10, 12, 12)
        self.structure_layout.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.structure)
        self.tabs.addTab(scroll, 'Estructura')
        rl.addWidget(self.tabs, 1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 900])

    def _chip(self, text: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(22)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT_DIM};
                border: none; border-radius: 5px; padding: 0 10px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; background: transparent; }}
        """)
        btn.clicked.connect(slot)
        return btn

    # --- ciclo de vida ---------------------------------------------------------------
    def refresh(self) -> None:
        """Relee el catalogo y la estructura de la tabla abierta.

        Lo llama la pestana al mostrarse (docs/explorador-db.md 6): si migraste
        en otra pestana, al volver lo ves. Las filas no se releen solas — vuelven
        a la primera pagina cuando eliges la tabla otra vez.
        """
        self._send('relations')
        if self._trail:
            self._send('describe', relation=self._trail[-1][0], _keep_rows=True)

    def shutdown(self) -> None:
        self.worker.stop()

    def _send(self, kind: str, **kwargs) -> None:
        keep = kwargs.pop('_keep_rows', False)
        req_id = self.worker.request(kind, **kwargs)
        self._pending[kind] = req_id
        if kind == 'describe':
            self._pending['describe_keep'] = int(keep)

    def _on_result(self, req_id: int, kind: str, payload) -> None:
        if self._pending.get(kind) != req_id:
            return   # llego tarde: ya se pidio otra cosa
        self._pending.pop(kind, None)
        if kind == 'relations':
            self._fill_tree(payload)
        elif kind == 'describe':
            self._show_detail(payload, keep_rows=bool(self._pending.pop('describe_keep', 0)))
        elif kind == 'rows':
            self.model.append(payload)
            if payload.offset == 0:
                self._fit_columns()
            self._show_status('')
        elif kind == 'count':
            self._exact = payload
            self._update_header()

    def _on_failed(self, req_id: int, kind: str, message: str) -> None:
        if self._pending.get(kind) != req_id:
            return
        self._pending.pop(kind, None)
        if kind == 'rows':
            self.model.loading = False
        self._show_status(message, error=True)

    def _show_status(self, text: str, error: bool = False) -> None:
        self.status.setVisible(bool(text))
        color = Colors.ERROR if error else Colors.TEXT_MUTED
        self.status.setStyleSheet(
            f'background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;')
        self.status.setText(text)

    # --- arbol ---------------------------------------------------------------------
    def _fill_tree(self, relations: list[dbx.Relation]) -> None:
        self._relations = relations
        current = self._trail[-1][0].qualified if self._trail else None
        expanded = {self.tree.topLevelItem(i).text(0)
                    for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        first_fill = self.tree.topLevelItemCount() == 0

        self.tree.blockSignals(True)
        self.tree.clear()
        schemas: dict[str, QTreeWidgetItem] = {}
        items: dict[str, QTreeWidgetItem] = {}
        children: dict[str, int] = {}
        for rel in relations:
            if rel.parent:
                children[f'{rel.schema}.{rel.parent}'] = children.get(f'{rel.schema}.{rel.parent}', 0) + 1

        for rel in relations:
            if rel.schema not in schemas:
                item = QTreeWidgetItem([rel.schema, ''])
                item.setForeground(0, QColor(Colors.TEXT_DIM))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                self.tree.addTopLevelItem(item)
                schemas[rel.schema] = item
            parent = schemas[rel.schema]
            if rel.parent and f'{rel.schema}.{rel.parent}' in items:
                parent = items[f'{rel.schema}.{rel.parent}']
            item = QTreeWidgetItem([self._tree_label(rel, children.get(rel.qualified, 0)),
                                    '' if rel.kind == 'v' else dbx.human_count(rel.estimate)])
            item.setData(0, _ROLE_REL, rel)
            item.setForeground(1, QColor(Colors.TEXT_MUTED))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
            tip = [f'<b>{rel.qualified}</b> · {rel.kind_label}']
            if rel.kind not in ('v',):
                tip.append(f'~{dbx.human_count(rel.estimate)} filas · {human_size(rel.size_bytes)}')
            if rel.comment:
                tip.append(rel.comment)
            if not rel.readable:
                tip.append(f"<span style='color:{Colors.WARNING};'>El rol de la app no tiene SELECT</span>")
                item.setForeground(0, QColor(Colors.TEXT_MUTED))
            elif rel.kind in ('v', 'm', 'f') or rel.name == 'spatial_ref_sys':
                item.setForeground(0, QColor(Colors.TEXT_DIM))
            item.setToolTip(0, '<br>'.join(tip))
            parent.addChild(item)
            items[rel.qualified] = item

        for name, item in schemas.items():
            # La primera vez se abre `public` (o el unico esquema); despues se
            # respeta lo que dejaste abierto.
            item.setExpanded(name in expanded if not first_fill
                             else name == 'public' or len(schemas) == 1)
        if current and current in items:
            self.tree.setCurrentItem(items[current])
        self.tree.blockSignals(False)
        self._apply_tree_filter(self.filter_box.text())

    @staticmethod
    def _tree_label(rel: dbx.Relation, partitions: int) -> str:
        glyph = {'v': '◇ ', 'm': '◈ ', 'f': '⇢ '}.get(rel.kind, '')
        extra = f'  ({partitions})' if partitions else ''
        return f'{glyph}{rel.name}{extra}'

    def _apply_tree_filter(self, text: str) -> None:
        needle = text.strip().lower()

        def visit(item: QTreeWidgetItem) -> bool:
            rel = item.data(0, _ROLE_REL)
            own = not needle or (rel is not None and needle in rel.name.lower())
            child_hit = False
            for i in range(item.childCount()):
                child_hit = visit(item.child(i)) or child_hit
            visible = own or child_hit
            item.setHidden(not visible)
            if needle and child_hit:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            hit = False
            for j in range(top.childCount()):
                hit = visit(top.child(j)) or hit
            top.setHidden(bool(needle) and not hit)
            if needle and hit:
                top.setExpanded(True)

    def _on_tree_clicked(self, item: QTreeWidgetItem | None, *_args) -> None:
        rel = item.data(0, _ROLE_REL) if item is not None else None
        if rel is None:
            return
        if self._trail and self._trail[-1][0].qualified == rel.qualified and not self._trail[-1][1]:
            return
        self._open(rel, dbx.Filter(), reset_trail=True)

    # --- abrir una tabla -------------------------------------------------------------
    def _open(self, rel: dbx.Relation, where: dbx.Filter, *, reset_trail: bool) -> None:
        if reset_trail:
            self._trail = []
        self._trail.append((rel, where))
        self._detail = None
        self._exact = None
        self.model.order_by = None
        self.model.descending = False
        self.model.reset(None)
        self._clear_structure()
        self._update_header()
        self._rebuild_trail()
        self._show_status('Cargando…')
        self._send('describe', relation=rel)

    def _show_detail(self, detail: dbx.TableDetail, *, keep_rows: bool) -> None:
        self._detail = detail
        # La relacion del arbol puede estar desactualizada (estimado, tamano):
        # la del catalogo recien leido manda.
        for rel in self._relations:
            if rel.qualified == detail.relation.qualified:
                detail.relation = rel
        self._fill_structure(detail)
        self._update_header()
        if keep_rows and self.model.detail is not None:
            # Refresco al volver a la pestana: la estructura se relee, las filas
            # que ya mirabas se quedan.
            columns_now = [c.name for c in detail.columns]
            if columns_now == [c.name for c in self.model.detail.columns]:
                self.model.detail = detail
                return
        self.model.reset(detail)
        self.count_btn.setEnabled(True)
        self._request_rows(offset=0)

    def _request_rows(self, offset: int) -> None:
        if self._detail is None:
            return
        self.model.loading = True
        self._send('rows', detail=self._detail, offset=offset, order_by=self.model.order_by,
                   descending=self.model.descending, where=self._trail[-1][1])

    def _request_more(self) -> None:
        self._request_rows(offset=len(self.model.rows))

    def _fit_columns(self) -> None:
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        for i in range(header.count()):
            if header.sectionSize(i) > 320:
                header.resizeSection(i, 320)

    def _on_sort(self, section: int) -> None:
        """Ordenar es del servidor: ordenar solo lo cargado mentiria."""
        if self._detail is None:
            return
        name = self._detail.columns[section].name
        if self.model.order_by == name:
            self.model.descending = not self.model.descending
        else:
            self.model.order_by, self.model.descending = name, False
        self.model.reset(self._detail)
        self._request_rows(offset=0)

    def _count(self) -> None:
        if self._trail:
            rel, where = self._trail[-1]
            self.count_btn.setEnabled(False)
            self._send('count', relation=rel, where=where)

    def _update_header(self) -> None:
        if not self._trail:
            self.title.setText('Elige una tabla')
            self.subtitle.setText('')
            self.count_btn.setEnabled(False)
            return
        rel, where = self._trail[-1]
        self.title.setText(rel.qualified)
        partes = [rel.kind_label]
        if self._exact is not None:
            filas = 'fila' if self._exact == 1 else 'filas'
            partes.append(f'{self._exact:,} {filas}'.replace(',', '.') + (' con el filtro' if where else ''))
        elif rel.kind != 'v':
            partes.append(f'~{dbx.human_count(rel.estimate)} filas')
        if rel.kind != 'v':
            partes.append(human_size(rel.size_bytes))
        self.subtitle.setText('  ·  '.join(partes))
        self.count_btn.setEnabled(self._detail is not None and self._exact is None)

    # --- seguir una FK ---------------------------------------------------------------
    def _on_cell_double_clicked(self, index: QModelIndex) -> None:
        if self._detail is None or not index.isValid():
            return
        col = self._detail.columns[index.column()]
        value = self.model.rows[index.row()][index.column()]
        if col.fk is None or value is None:
            return
        self._follow(col.fk.ref_schema, col.fk.ref_table,
                     dbx.Filter({col.fk.ref_columns[0]: value}))

    def _follow(self, schema: str, table: str, where: dbx.Filter) -> None:
        target = next((r for r in self._relations
                       if r.schema == schema and r.name == table), None)
        if target is None:
            self._show_status(f'{schema}.{table} no está en el catálogo leído.', error=True)
            return
        self._open(target, where, reset_trail=False)

    def _rebuild_trail(self) -> None:
        while self.trail_row.count():
            item = self.trail_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.trail_wrap.setVisible(len(self._trail) > 1)
        if len(self._trail) <= 1:
            return
        for i, (rel, where) in enumerate(self._trail):
            if i:
                sep = QLabel('›')
                sep.setStyleSheet(f'background: transparent; color: {Colors.TEXT_MUTED};')
                self.trail_row.addWidget(sep)
            texto = rel.name + ''.join(f' {k}={v}' for k, v in where.equals.items())
            ultimo = i == len(self._trail) - 1
            crumb = QPushButton(texto if len(texto) <= 60 else texto[:57] + '…')
            crumb.setEnabled(not ultimo)
            crumb.setCursor(Qt.CursorShape.PointingHandCursor)
            crumb.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none; padding: 0 2px;
                               color: {Colors.ACCENT}; font-size: {Fonts.SIZE_XS}px; }}
                QPushButton:disabled {{ color: {Colors.TEXT}; }}
            """)
            crumb.clicked.connect(lambda _c=False, n=i: self._back_to(n))
            self.trail_row.addWidget(crumb)
        self.trail_row.addStretch()

    def _back_to(self, index: int) -> None:
        rel, where = self._trail[index]
        self._trail = self._trail[:index]
        self._open(rel, where, reset_trail=False)

    # --- estructura ------------------------------------------------------------------
    def _clear_structure(self) -> None:
        while self.structure_layout.count():
            item = self.structure_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _fill_structure(self, detail: dbx.TableDetail) -> None:
        self._clear_structure()
        col_rows = []
        for col in detail.columns:
            llave = '🔑 PK' if col.pk else ''
            if col.fk:
                llave = (llave + '  ' if llave else '') + \
                    f'↗ {col.fk.ref_table}.{col.fk.ref_columns[0]}'
            extra = {'a': 'identity always', 'd': 'identity'}.get(col.identity, '')
            if col.generated:
                extra = 'generada'
            col_rows.append([col.name, col.type, '' if col.nullable else 'NOT NULL',
                             col.default or extra, llave, col.comment or ''])
        self._section('Columnas', ['Nombre', 'Tipo', 'Nulo', 'Default', 'Llave', 'Comentario'], col_rows)

        if detail.indexes:
            self._section('Índices', ['Nombre', 'Definición'],
                          [[ix.name, ix.definition] for ix in detail.indexes])
        kinds = {'p': 'PRIMARY KEY', 'f': 'FOREIGN KEY', 'u': 'UNIQUE', 'c': 'CHECK', 'x': 'EXCLUDE'}
        if detail.constraints:
            self._section('Constraints', ['Nombre', 'Tipo', 'Definición'],
                          [[c.name, kinds.get(c.kind, c.kind), c.definition] for c in detail.constraints])
        if detail.incoming:
            rows = [[f'{fk.ref_schema}.{fk.ref_table}', ', '.join(fk.ref_columns),
                     ', '.join(fk.columns), fk.name] for fk in detail.incoming]
            table = self._section('Referenciada por', ['Tabla', 'Columnas', '→ de esta tabla', 'Constraint'], rows)
            table.setToolTip('Doble clic para abrir esa tabla')
            table.cellDoubleClicked.connect(
                lambda r, _c, fks=detail.incoming: self._follow(fks[r].ref_schema, fks[r].ref_table, dbx.Filter()))
        self.structure_layout.addStretch()

    def _section(self, title: str, headers: list[str], rows: list[list[str]]) -> QTableWidget:
        label = QLabel(title.upper())
        label.setStyleSheet(
            f'background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px; '
            f'font-weight: 700; padding-top: 10px;')
        self.structure_layout.addWidget(label)

        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setWordWrap(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if len(value) > 40:
                    item.setToolTip(value)
                if c == 0:
                    font = item.font()
                    font.setFamily('Consolas')
                    item.setFont(font)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(header.count() - 1):
            if header.sectionSize(i) > 360:
                header.resizeSection(i, 360)
        row_h = 26
        table.verticalHeader().setDefaultSectionSize(row_h)
        table.setFixedHeight(header.sizeHint().height() + row_h * len(rows) + 18)
        self.structure_layout.addWidget(table)
        return table
