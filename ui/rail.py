from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton, QHBoxLayout,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QSettings

from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import Project
from ui.widgets import GroupCard
from ui import favorites, readiness


class ProjectHeader(QWidget):
    """Cabecera del rail: recuerda que TODA accion se ejecuta sobre este repo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(62)
        self.accent = Colors.ACCENT

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.icon_label = QLabel("🚢")
        self.icon_label.setStyleSheet(f"font-size: {Fonts.SIZE_XL}px;")
        self.name_label = QLabel("—")
        self.name_label.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_LG}px; font-weight: 700; letter-spacing: 0.5px;"
        )
        top.addWidget(self.icon_label)
        top.addWidget(self.name_label)
        top.addStretch()

        self.path_label = QLabel("")
        self.path_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;")

        layout.addLayout(top)
        layout.addWidget(self.path_label)

    def set_project(self, project: Project) -> None:
        self.accent = project.color
        self.icon_label.setText(project.icon)
        self.name_label.setText(project.name)
        self.path_label.setText(project.path)
        self.setStyleSheet(f"""
            ProjectHeader {{
                background: {Colors.SURFACE};
                border-left: 3px solid {self.accent};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)

    def clear(self) -> None:
        """Sin ningun repositorio en pestanas (arranque en vacio o se cerro el
        ultimo): nada que acentuar todavia."""
        self.accent = Colors.TEXT_MUTED
        self.icon_label.setText("◇")
        self.name_label.setText("—")
        self.path_label.setText("Añade un repositorio con «+»")
        self.setStyleSheet(f"""
            ProjectHeader {{
                background: {Colors.SURFACE};
                border-left: 3px solid {Colors.BORDER};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)


class ActionRail(QWidget):
    """Rail izquierdo: acciones agrupadas en cajas, siempre relativas al
    repo activo. Cada grupo es un recuadro cerrado; al abrirlo (acordeon,
    una caja a la vez) despliega sus acciones, una por renglon."""
    action_requested = Signal(str)  # capability_id
    run_requested = Signal(str)     # capability_id: correr sin abrir la pestana
    width_hint_changed = Signal()   # el ancho natural del contenido cambio
    favorites_changed = Signal(set)  # el conjunto de favoritas, ya guardado

    # El rail deja de tener un ancho fijo: se ajusta al contenido (un nombre de
    # repo largo, una caja abierta con acciones de titulo largo) entre estos dos
    # limites, y el usuario lo puede fijar arrastrando el separador — igual que
    # el panel de parametros. `MIN` es lo que necesita el filtro y la cabecera;
    # `MAX` evita que una sola accion con nombre kilometrico se coma media
    # ventana.
    MIN_WIDTH = 232
    MAX_WIDTH = 460
    DEFAULT_WIDTH = 288
    _SETTINGS_KEY = 'ui/rail_width'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self._user_width = self._load_user_width()
        self._only_favorites = favorites.only_favorites()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.setStyleSheet(f"""
            ActionRail {{
                background-color: {Colors.SURFACE};
                border-right: 1px solid {Colors.BORDER};
            }}
        """)

        # 1. Cabecera de repo activo
        self.project_header = ProjectHeader()
        self.layout.addWidget(self.project_header)

        # 2. Filtro rapido de acciones
        filter_container = QWidget()
        filter_container.setStyleSheet("background: transparent;")
        filter_layout = QVBoxLayout(filter_container)
        filter_layout.setContentsMargins(12, 10, 12, 6)

        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filtrar acciones…")
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 7px 10px;
                font-size: {Fonts.SIZE_SM}px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Colors.ACCENT};
            }}
        """)
        self.filter_box.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(self.filter_box)

        # El interruptor «solo favoritos» ya no vive aca: es global a la app,
        # no del rail —tambien poda los menus—, asi que subio a la barra de
        # titulo (`ui/title_bar.py`). El rail solo obedece el modo. El escape
        # por caja sigue en el contador de cada GroupCard.
        self.layout.addWidget(filter_container)

        # 3. Cajas de grupo
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {Colors.SURFACE};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_LIGHT};
                border-radius: 4px;
            }}
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 6, 12, 12)
        self.scroll_layout.setSpacing(6)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area, 1)

        # 4. Acceso a base de datos
        db_container = QWidget()
        db_layout = QVBoxLayout(db_container)
        db_layout.setContentsMargins(12, 10, 12, 10)
        db_container.setStyleSheet(f"border-top: 1px solid {Colors.BORDER};")

        self.db_btn = QPushButton("🗄️  Base de datos")
        self.db_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.db_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT};
                text-align: left;
                padding: 9px 12px;
                border: none;
                border-radius: 6px;
                font-size: {Fonts.SIZE_BASE}px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
            }}
        """)
        self.db_btn.clicked.connect(lambda: self.action_requested.emit("bootstrap_db"))
        db_layout.addWidget(self.db_btn)

        self.layout.addWidget(db_container)

        self.project: Project | None = None
        self._cards: list[GroupCard] = []
        self.populate()
        self._refresh()

    # --- ancho: auto al contenido, o fijado por el usuario ------------
    def _load_user_width(self) -> int:
        try:
            w = int(QSettings().value(self._SETTINGS_KEY, 0) or 0)
        except (TypeError, ValueError):
            return 0
        return w if self.MIN_WIDTH <= w <= self.MAX_WIDTH else 0

    def has_user_width(self) -> bool:
        return self._user_width > 0

    def set_user_width(self, width: int) -> int:
        """Lo llama la ventana cuando se arrastra el separador: a partir de aca
        el ancho lo manda el usuario y el auto-ajuste no lo pisa. Devuelve el
        ancho ya clampado a [MIN, MAX]."""
        self._user_width = max(self.MIN_WIDTH, min(self.MAX_WIDTH, int(width)))
        QSettings().setValue(self._SETTINGS_KEY, self._user_width)
        return self._user_width

    def clear_user_width(self) -> None:
        """Vuelve al ancho automatico (doble clic en el separador)."""
        self._user_width = 0
        QSettings().remove(self._SETTINGS_KEY)
        self.width_hint_changed.emit()

    def content_width(self) -> int:
        """El ancho que el contenido pide para no recortar nada.

        Se mide sobre el contenido del scroll (las cajas de grupo, que crecen
        con la caja abierta) mas los margenes y el ancho de la barra de scroll;
        la cabecera y el filtro caben siempre dentro del minimo.
        """
        inner = self.scroll_content.sizeHint().width()
        margins = self.scroll_layout.contentsMargins()
        chrome = margins.left() + margins.right() + 10  # 10 = barra de scroll
        return max(self.MIN_WIDTH, min(self.MAX_WIDTH, inner + chrome))

    def preferred_width(self) -> int:
        return self._user_width or self.content_width()

    def _schedule_width_hint(self) -> None:
        """El sizeHint de una caja recien abierta solo es correcto despues de
        que el layout se acomode, asi que el aviso se difiere un ciclo."""
        QTimer.singleShot(0, self.width_hint_changed.emit)

    def sizeHint(self) -> QSize:
        return QSize(self.preferred_width(), super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(self.MIN_WIDTH, super().minimumSizeHint().height())

    # --- API ----------------------------------------------------------
    def set_project(self, project: Project) -> None:
        self.project = project
        self.project_header.set_project(project)
        self.filter_box.setStyleSheet(self.filter_box.styleSheet().replace(
            f"border: 1px solid {Colors.ACCENT};", f"border: 1px solid {project.color};"
        ))
        for card in self._cards:
            card.set_accent(project.color)
        self.scroll_area.setEnabled(True)
        self.db_btn.setEnabled(True)
        self._schedule_width_hint()

    def clear_project(self) -> None:
        """Sin ningun repositorio en pestanas: nada sobre lo que correr una
        accion todavia. Deshabilita las cajas en vez de solo vaciarlas, para
        que un clic perdido en un boton de accion no quede sin efecto en
        silencio (`ui/main_window.py::_show_empty_state`)."""
        self.project = None
        self.project_header.clear()
        self.scroll_area.setEnabled(False)
        self.db_btn.setEnabled(False)

    def refresh_readiness(self, ready: set[str] | None = None) -> None:
        """Que acciones pueden correr ya, sin abrir la pestana, con el
        `.consola/config.env` guardado del repo activo y los parametros
        guardados de cada boton. Se recalcula al cambiar de repo, al guardar
        el `.env` y al cambiar parametros (`ui/tab_panel.py`).

        La ventana pasa `ready` ya calculado cuando la misma cuenta alimenta
        tambien a la barra de menu, para no recorrer el registro dos veces.
        """
        if ready is None:
            ready = readiness.ready_ids(self.project)
        for card in self._cards:
            card.set_ready(ready)

    # --- construccion --------------------------------------------------
    def populate(self) -> None:
        marked = favorites.favorite_ids()
        groups = registry.get_groups()
        for group_name, capabilities in groups.items():
            card = GroupCard(group_name, registry.get_group_icon(group_name), capabilities)
            card.set_favorites(marked)
            card.set_only_favorites(self._only_favorites)
            card.action_triggered.connect(self._emit_action)
            card.favorite_toggled.connect(self._on_favorite_toggled)
            card.run_requested.connect(self.run_requested.emit)
            card.expanded.connect(self._collapse_others)
            self.scroll_layout.addWidget(card)
            self._cards.append(card)

    def _collapse_others(self, opened) -> None:
        """Acordeon: una caja abierta a la vez, para que el rail no crezca
        hasta obligar a hacer scroll para volver a los grupos de arriba.

        No aplica mientras se ven solo las favoritas: ahi las cajas ya estan
        podadas y caben todas abiertas."""
        if self._only_favorites or self.filter_box.text().strip():
            self._schedule_width_hint()
            return
        for card in self._cards:
            if card is not opened:
                card.set_expanded(False)
        self._schedule_width_hint()

    # --- filtro y modo --------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        self._refresh()

    def set_only_favorites(self, value: bool) -> None:
        """Lo manda el interruptor de la barra de titulo. Guardar el modo es
        cosa de quien lo manda: el rail es una de las dos superficies que lo
        obedecen, no su dueño."""
        self._only_favorites = value
        for card in self._cards:
            card.set_only_favorites(value)
        self._refresh()

    def refresh_favorites(self) -> None:
        """Se marco una favorita desde otra superficie (la estrella de la
        cabecera de parametros): las cajas releen el conjunto guardado."""
        marked = favorites.favorite_ids()
        for card in self._cards:
            card.set_favorites(marked)
        self._refresh()

    def _refresh(self) -> None:
        """Texto y modo favoritos deciden juntos que se ve.

        Con el interruptor puesto las cajas quedan abiertas: son cortas y la
        gracia del modo es llegar a la accion en un clic, no en dos.
        """
        needle = self.filter_box.text().strip().lower()
        only_fav = self._only_favorites
        for card in self._cards:
            hits = card.filter(needle)
            card.setVisible(hits > 0)
            if needle or only_fav:
                card.set_expanded(hits > 0, announce=False)
            else:
                card.set_expanded(False, announce=False)
        self._schedule_width_hint()

    def _emit_action(self, cap_id: str):
        self.action_requested.emit(cap_id)

    def _on_favorite_toggled(self, cap_id: str, value: bool) -> None:
        ids = favorites.set_favorite(cap_id, value)
        if self._only_favorites:
            self._refresh()
        self.favorites_changed.emit(ids)

    def set_active_action(self, cap_id: str) -> None:
        pass
