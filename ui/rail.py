from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QPushButton, QHBoxLayout,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal, QSettings

from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import Project
from ui.widgets import SectionHeader, ActionButton, Segmented, GroupCard


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


class ActionRail(QWidget):
    """Rail izquierdo: acciones agrupadas, siempre relativas al repo activo."""
    action_requested = Signal(str)  # capability_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(288)

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

        # Selector de presentacion: cajas por grupo (compacto, se abarca de
        # un vistazo) o el listado plano de siempre.
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 6, 0, 0)
        mode_row.addStretch()
        self.mode_toggle = Segmented(['Cajas', 'Lista'], current=self._saved_mode())
        self.mode_toggle.value_changed.connect(self._set_mode)
        mode_row.addWidget(self.mode_toggle)
        filter_layout.addLayout(mode_row)

        self.layout.addWidget(filter_container)

        # 3. Lista de acciones
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
        self.scroll_layout.setContentsMargins(12, 0, 12, 12)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Vista de cajas y vista de listado conviven; solo una esta visible.
        self.cards_view = QWidget()
        self.cards_view.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_view)
        self.cards_layout.setContentsMargins(0, 6, 0, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.list_view = QWidget()
        self.list_view.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_view)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_layout.addWidget(self.cards_view)
        self.scroll_layout.addWidget(self.list_view)

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

        self._sections: list[tuple[SectionHeader, QWidget, list[ActionButton]]] = []
        self._cards: list[GroupCard] = []
        self.populate()
        self._apply_mode(self._saved_mode())

    # --- API ----------------------------------------------------------
    def set_project(self, project: Project) -> None:
        self.project_header.set_project(project)
        self.filter_box.setStyleSheet(self.filter_box.styleSheet().replace(
            f"border: 1px solid {Colors.ACCENT};", f"border: 1px solid {project.color};"
        ))
        self.mode_toggle.set_accent(project.color)
        for card in self._cards:
            card.set_accent(project.color)

    # --- construccion --------------------------------------------------
    def populate(self) -> None:
        groups = registry.get_groups()
        for group_name, capabilities in groups.items():
            self._add_list_section(group_name, capabilities)
            self._add_card(group_name, capabilities)

    def _add_list_section(self, group_name: str, capabilities: list) -> None:
        """Presentacion clasica: cabecera de seccion + un renglon por accion."""
        icon = registry.get_group_icon(group_name)
        header = SectionHeader(group_name, icon, self)
        self.list_layout.addWidget(header)

        section_widget = QWidget()
        section_widget.setStyleSheet("background: transparent;")
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(0, 0, 0, 8)
        section_layout.setSpacing(2)

        buttons: list[ActionButton] = []

        # Un boton por capacidad: las variantes ya no duplican filas, viven
        # en el panel de parametros (docs/panel-de-parametros.md §1).
        for cap in capabilities:
            btn = ActionButton(cap.id, cap.name, cap.icon, cap.kind,
                               cap.kind == 'destructive', self)
            btn.action_triggered.connect(self._emit_action)
            section_layout.addWidget(btn)
            buttons.append(btn)

        self.list_layout.addWidget(section_widget)
        header.toggled.connect(section_widget.setVisible)
        self._sections.append((header, section_widget, buttons))

    def _add_card(self, group_name: str, capabilities: list) -> None:
        """Presentacion en cajas: el grupo es un recuadro cerrado; al abrirlo
        muestra sus acciones como pastillas, no como renglones."""
        card = GroupCard(group_name, registry.get_group_icon(group_name), capabilities)
        card.action_triggered.connect(self._emit_action)
        card.expanded.connect(self._collapse_others)
        self.cards_layout.addWidget(card)
        self._cards.append(card)

    # --- modo de presentacion -------------------------------------------
    def _saved_mode(self) -> str:
        return 'Lista' if QSettings().value('rail/mode', 'Cajas') == 'Lista' else 'Cajas'

    def _set_mode(self, mode: str) -> None:
        QSettings().setValue('rail/mode', mode)
        self._apply_mode(mode)

    def _apply_mode(self, mode: str) -> None:
        cards = mode == 'Cajas'
        self.cards_view.setVisible(cards)
        self.list_view.setVisible(not cards)
        self._apply_filter(self.filter_box.text())

    def _collapse_others(self, opened) -> None:
        """Acordeon: una caja abierta a la vez, para que el rail no crezca
        hasta obligar a hacer scroll para volver a los grupos de arriba."""
        for card in self._cards:
            if card is not opened:
                card.set_expanded(False)

    # --- filtro ---------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        self._filter_list(needle)
        self._filter_cards(needle)

    def _filter_list(self, needle: str) -> None:
        for header, section_widget, buttons in self._sections:
            if not needle:
                for btn in buttons:
                    btn.setVisible(True)
                header.setVisible(True)
                section_widget.setVisible(header.is_expanded())
                continue

            any_match = False
            for btn in buttons:
                match = needle in btn.text_label.text().lower()
                btn.setVisible(match)
                any_match = any_match or match
            header.setVisible(any_match)
            section_widget.setVisible(any_match)

    def _filter_cards(self, needle: str) -> None:
        """Con filtro escrito las cajas con coincidencias se abren solas: sin
        eso habria que abrirlas a mano para ver el resultado de la busqueda."""
        for card in self._cards:
            hits = card.filter(needle)
            card.setVisible(hits > 0)
            if needle:
                card.set_expanded(hits > 0, announce=False)
            else:
                card.set_expanded(False, announce=False)

    def _emit_action(self, cap_id: str):
        self.action_requested.emit(cap_id)

    def set_active_action(self, cap_id: str) -> None:
        pass
