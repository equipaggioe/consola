from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QApplication
)
from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QRect

from ui.theme import Colors, Fonts
from ui import favorites
from ui.widgets import ActionRow
from core.registry import registry


class ActionSearch(QWidget):
    """Buscador de la barra de menu: al escribir despliega debajo las acciones
    que coinciden, con las mismas filas del rail (`ActionRow`) — filete de
    favorita, marcas de nivel y ▶ para correr de una.

    Busca sobre TODAS las acciones aunque «solo favoritos» este puesto, igual
    que el filtro del rail (`GroupCard._sync_rows`): buscar es ir por algo
    puntual. Emite las mismas senales que el rail y el menu, asi que
    `MainWindow` no distingue de donde vino el clic.

    Teclado: flechas para moverse, Enter abre la pestana, Ctrl+Enter la corre
    si esta lista, Esc cierra.
    """
    action_requested = Signal(str)
    run_requested = Signal(str)
    favorites_changed = Signal(set)

    WIDTH = 240
    POPUP_WIDTH = 440
    POPUP_MAX_HEIGHT = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accent = Colors.ACCENT
        self._ready: set[str] = set()
        self._current = -1

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(0)

        self.box = QLineEdit()
        self.box.setPlaceholderText("Buscar acciones…")
        self.box.setClearButtonEnabled(True)
        self.box.setFixedWidth(self.WIDTH)
        self.box.textChanged.connect(self._on_text)
        self.box.installEventFilter(self)
        lay.addWidget(self.box)
        self._restyle_box()

        self._popup: QFrame | None = None
        self._rows: list[ActionRow] = []
        self._headers: list[tuple[QLabel, list[ActionRow]]] = []

    # --- estado que llega de la ventana ----------------------------------
    def set_accent(self, color: str) -> None:
        self._accent = color
        self._restyle_box()
        for row in self._rows:
            row.set_accent(color)

    def set_ready(self, ready: set[str]) -> None:
        self._ready = set(ready)
        for row in self._rows:
            row.set_ready(row.capability_id in self._ready)

    def set_favorites(self, ids: set[str]) -> None:
        for row in self._rows:
            row.set_favorite(row.capability_id in ids)

    def set_project_active(self, active: bool) -> None:
        """Sin repo en pestanas no hay sobre que correr: igual que el rail y
        los menus de grupo, el buscador se apaga."""
        self.box.setEnabled(active)
        if not active:
            self.box.clear()

    def _restyle_box(self) -> None:
        self.box.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: {Fonts.SIZE_SM}px;
            }}
            QLineEdit:focus {{ border: 1px solid {self._accent}; }}
            QLineEdit:disabled {{ color: {Colors.TEXT_MUTED}; }}
        """)

    # --- popup -------------------------------------------------------------
    def _build_popup(self) -> QFrame:
        """Hijo de la ventana y no una ventana `Qt.Popup`: un popup de verdad
        se lleva el foco del teclado, y hay que poder seguir escribiendo con
        la lista abierta. Se construye una vez, con todas las acciones, y la
        busqueda solo cambia que filas se ven."""
        popup = QFrame(self.window())
        popup.setObjectName("actionSearchPopup")
        popup.setCursor(Qt.CursorShape.ArrowCursor)
        popup.setStyleSheet(f"""
            QFrame#actionSearchPopup {{
                background: {Colors.SURFACE};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: 8px;
            }}
        """)
        outer = QVBoxLayout(popup)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {Colors.SURFACE}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {Colors.BORDER_LIGHT}; border-radius: 4px; }}
        """)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 6)
        self._content_layout.setSpacing(0)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        marked = favorites.favorite_ids()
        for group, capabilities in registry.get_groups().items():
            header = QLabel(f"{registry.get_group_icon(group)}  {group.upper()}".strip())
            header.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; padding: 8px 10px 3px 10px;")
            self._content_layout.addWidget(header)
            rows = []
            for cap in capabilities:
                row = ActionRow(cap.id, cap.name, cap.icon,
                                danger=cap.kind == 'destructive', accent=self._accent,
                                favorite=cap.id in marked, composite=cap.is_composite,
                                description=cap.description, machine=cap.is_machine_wide)
                row.set_ready(cap.id in self._ready)
                row.triggered.connect(self._open)
                row.run_requested.connect(self._run)
                row.favorite_toggled.connect(self._on_favorite_toggled)
                self._content_layout.addWidget(row)
                rows.append(row)
            self._headers.append((header, rows))
            self._rows.extend(rows)

        self._empty = QLabel("Sin resultados")
        self._empty.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_SM}px; padding: 12px;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.addWidget(self._empty)

        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)
        popup.hide()
        return popup

    def _visible_rows(self) -> list[ActionRow]:
        return [row for row in self._rows if not row.isHidden()]

    def _on_text(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            self._hide_popup()
            return
        if self._popup is None:
            self._popup = self._build_popup()

        hits = 0
        for header, rows in self._headers:
            group_hits = 0
            for row in rows:
                match = row.matches(needle)
                row.setVisible(match)
                group_hits += int(match)
            header.setVisible(group_hits > 0)
            hits += group_hits
        self._empty.setVisible(hits == 0)
        self._set_current(0 if hits else -1)
        self._show_popup()

    def _show_popup(self) -> None:
        popup = self._popup
        window = self.window()
        # Alineado por la derecha con el campo: el buscador vive cerca del
        # borde derecho de la fila, y la lista es mas ancha que el campo.
        anchor = self.box.mapTo(window, QPoint(self.box.width(), self.box.height() + 4))
        width = max(self.POPUP_WIDTH, self.box.width())
        x = max(4, anchor.x() - width)
        self._content_layout.activate()
        wanted = self._scroll.widget().sizeHint().height() + 2
        room = window.height() - anchor.y() - 12
        height = max(60, min(wanted, self.POPUP_MAX_HEIGHT, room))
        popup.setGeometry(x, anchor.y(), width, height)
        if not popup.isVisible():
            popup.show()
            QApplication.instance().installEventFilter(self)
        popup.raise_()

    def _hide_popup(self) -> None:
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()
            QApplication.instance().removeEventFilter(self)
        self._set_current(-1)

    # --- seleccion con teclado ------------------------------------------
    def _set_current(self, index: int) -> None:
        visible = self._visible_rows()
        for row in self._rows:
            row.set_highlighted(False)
        self._current = index if 0 <= index < len(visible) else -1
        if self._current >= 0:
            row = visible[self._current]
            row.set_highlighted(True)
            self._scroll.ensureWidgetVisible(row, 0, 24)

    def _current_row(self) -> ActionRow | None:
        visible = self._visible_rows()
        return visible[self._current] if 0 <= self._current < len(visible) else None

    # --- disparo -----------------------------------------------------------
    def _open(self, cap_id: str) -> None:
        self.box.clear()
        self.action_requested.emit(cap_id)

    def _run(self, cap_id: str) -> None:
        self.box.clear()
        self.run_requested.emit(cap_id)

    def _on_favorite_toggled(self, cap_id: str, value: bool) -> None:
        """Marcar desde la lista no la cierra: se guarda y se avisa al resto
        de las superficies, igual que desde el rail."""
        self.favorites_changed.emit(favorites.set_favorite(cap_id, value))

    # --- eventos -------------------------------------------------------------
    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.box and kind == QEvent.Type.FocusIn and self.box.text().strip():
            # Se cerro con un clic afuera pero quedo el texto: volver al campo
            # reabre la lista tal como estaba.
            self._on_text(self.box.text())
        elif obj is self.box and kind == QEvent.Type.KeyPress:
            popup_open = self._popup is not None and self._popup.isVisible()
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.box.clear()
                return True
            if popup_open and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                count = len(self._visible_rows())
                if count:
                    step = 1 if key == Qt.Key.Key_Down else -1
                    self._set_current((self._current + step) % count)
                return True
            if popup_open and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self._current_row()
                if row is not None:
                    ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
                    if ctrl and row.capability_id in self._ready:
                        self._run(row.capability_id)
                    else:
                        self._open(row.capability_id)
                return True
        elif kind == QEvent.Type.MouseButtonPress and self._popup is not None:
            # Clic fuera del campo y de la lista: se cierra, sin comerse el clic.
            pos = event.globalPosition().toPoint()
            popup_rect = QRect(self._popup.mapToGlobal(QPoint(0, 0)), self._popup.size())
            box_rect = QRect(self.box.mapToGlobal(QPoint(0, 0)), self.box.size())
            if not popup_rect.contains(pos) and not box_rect.contains(pos):
                self._hide_popup()
        elif kind == QEvent.Type.WindowDeactivate and obj is self.window():
            self._hide_popup()
        return super().eventFilter(obj, event)
