from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPainterPath, QPen

from ui.theme import Colors, Fonts
from core.registry import Capability
from core.projects import Project
from ui.console_view import ConsoleView
from ui.params_panel import ParamsPanel
from ui.env_panel import EnvPanel
from ui.widgets.led import LedIndicator
from ui.widgets import ReorderableTab, ReorderableBar, StarToggle
from ui import favorites


class SubTabButton(ReorderableTab, QWidget):
    """Pestana de segundo nivel: una ejecucion dentro del repo activo.

    Subordinada visualmente al nivel superior: mas baja, tipografia menor
    y subrayado (no barra superior) en el color del repo.
    """
    clicked = Signal()
    close_requested = Signal()

    HEIGHT = 34

    def __init__(self, title: str, icon: str, accent: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.accent = accent
        self.is_active = False
        self._hovered = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("SubTabButton { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(7)

        self.icon_label = QLabel(icon or "⚡")
        self.icon_label.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_SM}px;")

        self.title_label = QLabel(title)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
                font-size: {Fonts.SIZE_LG}px;
            }}
            QPushButton:hover {{
                color: {Colors.ERROR};
            }}
        """)
        self.close_btn.clicked.connect(self.close_requested.emit)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.close_btn)

        self._init_reorder()
        self._sync_text()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.update()

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._sync_text()
        self.update()

    def _sync_text(self) -> None:
        f = QFont(self.title_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        f.setBold(self.is_active)
        self.title_label.setFont(f)
        color = Colors.TEXT if self.is_active else (Colors.TEXT_DIM if self._hovered else Colors.TEXT_MUTED)
        self.title_label.setStyleSheet(f"background: transparent; color: {color};")

    def enterEvent(self, event):
        self._hovered = True
        self._sync_text()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._reorder_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._reorder_release(event)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        accent = QColor(self.accent)

        if self.is_active:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(accent.red(), accent.green(), accent.blue(), 34))
            underline = QPainterPath()
            underline.addRoundedRect(QRectF(r.left() + 8, r.bottom() - 3, r.width() - 16, 2.5), 1.2, 1.2)
            p.fillPath(underline, accent)
        elif self._hovered or self.is_dragging:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))

        if self.is_dragging:
            pen = QPen(accent)
            pen.setWidthF(1.2)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(2.5, 4.5, -2.5, -3.5), 7, 7)
        p.end()


class WorkspaceStatusBar(QWidget):
    """Barra inferior del espacio de trabajo: repo activo, servicios y estado.

    Antes eran dos barras apiladas (un selector de vistas que no cambiaba
    ninguna vista, y una barra de estado global repitiendo el mismo reloj).
    Se fusionaron en una sola.
    """

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.project_label = QLabel("")
        layout.addWidget(self.project_label)

        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(10)
        layout.addLayout(self.services_layout)

        layout.addStretch()

        self.status_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")
        layout.addWidget(self.status_label)

        self._restyle()

    def set_project(self, name: str, icon: str = "") -> None:
        self.project_label.setText(f"{icon or '◇'} {name}")

    def add_service(self, name: str) -> None:
        container = QWidget()
        container.setObjectName(f"service_{name}")
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=9)
        led.set_state('green')
        clayout.addWidget(led)

        label = QLabel(name)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")
        clayout.addWidget(label)

        self.services_layout.addWidget(container)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _restyle(self) -> None:
        self.setStyleSheet(f"""
            WorkspaceStatusBar {{
                background: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        self.project_label.setStyleSheet(
            f"color: {self.accent}; font-size: {Fonts.SIZE_SM}px; font-weight: 600;"
        )


class TabPanel(ReorderableBar, QWidget):
    """Espacio de trabajo de UN repositorio.

    Contiene el segundo nivel de pestanas (las ejecuciones de ese repo),
    el area de consola y la barra de vistas. Cada repo tiene su propia
    instancia, asi que las sub-pestanas nunca se mezclan entre repos.
    """
    favorites_changed = Signal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.accent = project.color
        self._header_capability = ''

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # --- barra de sub-pestanas -----------------------------------
        self.sub_bar = QWidget()
        self.sub_bar.setObjectName("subBar")
        self.sub_bar.setFixedHeight(SubTabButton.HEIGHT + 4)
        self.sub_bar.setStyleSheet(f"""
            QWidget#subBar {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
        sub_bar_layout = QHBoxLayout(self.sub_bar)
        sub_bar_layout.setContentsMargins(10, 0, 10, 0)
        sub_bar_layout.setSpacing(2)

        self.tabs_layout = QHBoxLayout()
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(2)
        sub_bar_layout.addLayout(self.tabs_layout)

        self.empty_hint = QLabel("sin acciones abiertas — elige una del panel izquierdo")
        self.empty_hint.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        sub_bar_layout.addWidget(self.empty_hint)
        sub_bar_layout.addStretch()

        # --- area de contenido ---------------------------------------
        self.content_area = QStackedWidget()
        self.content_area.setStyleSheet(f"background: {Colors.BG};")

        self.welcome_widget = self._build_welcome()
        self.content_area.addWidget(self.welcome_widget)

        # --- columna derecha: cabecera unica + config arriba, parametros abajo ---
        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_params_placeholder())

        self.env_panel = EnvPanel(project)
        self.env_panel.values_changed.connect(self._on_env_changed)

        self.right_column = QSplitter(Qt.Orientation.Vertical)
        self.right_column.addWidget(self.env_panel)
        self.right_column.addWidget(self.params_stack)
        self.right_column.setSizes([420, 460])
        self.right_column.setChildrenCollapsible(True)

        self.right_header = self._build_right_header()

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.right_header)
        right_layout.addWidget(self.right_column, 1)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.content_area)
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([880, 330])

        # --- barra de estado -------------------------------------------
        self.status_bar = WorkspaceStatusBar(self.accent)
        self.status_bar.set_project(project.name, project.icon)
        self.status_bar.add_service("Túnel Postgres")

        self.layout.addWidget(self.sub_bar)
        self.layout.addWidget(self.splitter, 1)
        self.layout.addWidget(self.status_bar)

        self.tabs: list[SubTabButton] = []
        self._consoles: dict[SubTabButton, ConsoleView] = {}
        self._params: dict[SubTabButton, ParamsPanel] = {}

    # --- construccion ------------------------------------------------
    def _build_right_header(self) -> QWidget:
        """Cabecera unica de la columna derecha: reemplaza el rotulo fijo
        'Configuracion del repo' — muestra el repo activo sin pestana
        abierta, y el nombre de la accion en curso cuando hay una."""
        head = QWidget()
        head.setStyleSheet(f"background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        self.right_header_icon = QLabel(self.project.icon or "◇")
        self.right_header_icon.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_LG}px;")
        self.right_header_name = QLabel(self.project.name)
        self.right_header_name.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;"
        )
        self.favorite_star = StarToggle(accent=self.accent)
        self.favorite_star.toggled.connect(self._on_star_toggled)
        self.favorite_star.setVisible(False)

        lay.addWidget(self.right_header_icon)
        lay.addWidget(self.right_header_name)
        lay.addStretch()
        lay.addWidget(self.favorite_star)
        return head

    def _set_right_header(self, icon: str, name: str, capability_id: str = '') -> None:
        self.right_header_icon.setText(icon or "◇")
        self.right_header_name.setText(name)
        self._header_capability = capability_id
        self.favorite_star.setVisible(bool(capability_id))
        if capability_id:
            self.favorite_star.set_checked(
                favorites.is_favorite(self.project.path, capability_id), announce=False)

    def _on_star_toggled(self, value: bool) -> None:
        """La estrella marca la accion como favorita de ESTE repo; el rail
        se entera por la senal."""
        if not self._header_capability:
            return
        favorites.set_favorite(self.project.path, self._header_capability, value)
        self.favorites_changed.emit()

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        self.diamond_label = QLabel(self.project.icon or "◇")
        self.diamond_label.setStyleSheet(f"color: {self.accent}; font-size: 54px;")
        self.diamond_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.welcome_title = QLabel(self.project.name.upper())
        self.welcome_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_XXL}px; font-weight: 300; letter-spacing: 8px;"
        )
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Selecciona una accion del panel izquierdo")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_BASE}px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.path_label = QLabel(self.project.path)
        self.path_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(self.diamond_label, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.welcome_title, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        lay.addWidget(self.path_label, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _build_params_placeholder(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {Colors.SURFACE};")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(20, 20, 20, 20)
        hint = QLabel("Los parámetros de la acción\naparecen aquí")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        lay.addWidget(hint)
        return w

    # --- reordenar arrastrando ---------------------------------------
    def _tab_layout(self):
        return self.tabs_layout

    # --- API ---------------------------------------------------------
    def open_tab(self, capability: Capability, axis_value: str = '') -> ConsoleView:
        """Abre (o enfoca) la pestana de una accion. **No ejecuta nada**:
        ejecutar es apretar Ejecutar en el panel de parametros."""
        title = f"{capability.name} {axis_value}".strip()

        for tab in self.tabs:
            if tab.title == title:
                self._activate(tab)
                return self._consoles[tab]

        tab = SubTabButton(title, capability.icon, self.accent)
        self.tabs_layout.addWidget(tab)
        self.tabs.append(tab)

        console = ConsoleView(self.content_area)
        console.append_log(f"─── {capability.name} ───", "info")
        console.append_log("Ajusta los parámetros a la derecha y pulsa Ejecutar.", "info")
        self.content_area.addWidget(console)
        self._consoles[tab] = console

        panel = ParamsPanel(capability, self.project, self.env_panel)
        panel.set_env(self.env_panel.values())
        panel.execute_requested.connect(lambda payload, t=tab: self._run(t, payload))
        self.params_stack.addWidget(panel)
        self._params[tab] = panel

        tab.clicked.connect(lambda t=tab: self._activate(t))
        tab.close_requested.connect(lambda t=tab: self.close_tab(t))

        self.empty_hint.setVisible(False)
        self._activate(tab)
        return console

    def close_tab(self, tab: SubTabButton) -> None:
        if tab not in self.tabs:
            return
        idx = self.tabs.index(tab)
        was_active = tab.is_active

        console = self._consoles.pop(tab)
        self.content_area.removeWidget(console)
        console.deleteLater()

        panel = self._params.pop(tab, None)
        if panel is not None:
            self.params_stack.removeWidget(panel)
            panel.deleteLater()

        self.tabs.remove(tab)
        self.tabs_layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()

        if self.tabs:
            if was_active:
                self._activate(self.tabs[min(idx, len(self.tabs) - 1)])
        else:
            self.empty_hint.setVisible(True)
            self.content_area.setCurrentWidget(self.welcome_widget)
            self.params_stack.setCurrentIndex(0)
            self.env_panel.filter_for(None)
            self._set_right_header(self.project.icon, self.project.name)

    def current_console(self) -> ConsoleView | None:
        w = self.content_area.currentWidget()
        return w if isinstance(w, ConsoleView) else None

    def current_params(self) -> ParamsPanel | None:
        w = self.params_stack.currentWidget()
        return w if isinstance(w, ParamsPanel) else None

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.status_bar.set_accent(accent)
        self.diamond_label.setStyleSheet(f"color: {accent}; font-size: 54px;")
        for tab in self.tabs:
            tab.set_accent(accent)
        for panel in self._params.values():
            panel.set_accent(accent)
        self.favorite_star.set_accent(accent)
        self.env_panel.set_accent(accent)

    def set_status(self, text: str) -> None:
        self.status_bar.set_status(text)

    # --- interno ------------------------------------------------------
    def _activate(self, tab: SubTabButton) -> None:
        for t in self.tabs:
            t.set_active(t is tab)
        console = self._consoles.get(tab)
        if console is not None:
            self.content_area.setCurrentWidget(console)
        panel = self._params.get(tab)
        if panel is not None:
            self.params_stack.setCurrentWidget(panel)
            self.env_panel.filter_for(panel.relevant_keys())
            self._set_right_header(panel.capability.icon, panel.capability.name,
                                   panel.capability.id)
            QTimer.singleShot(0, self._fit_params_height)

    def _fit_params_height(self) -> None:
        """El panel de parametros solo ocupa lo que su contenido necesita;
        el resto de la columna derecha queda para el .env."""
        panel = self.current_params()
        if panel is None:
            return
        total = self.right_column.height()
        params_h = max(160, min(panel.natural_height(), total - 120))
        self.right_column.setSizes([total - params_h, params_h])

    def _on_env_changed(self, values: dict) -> None:
        for panel in self._params.values():
            panel.set_env(values)

    def _run(self, tab: SubTabButton, payload: dict) -> None:
        """Ejecucion simulada: reporta exactamente lo que correria (stub, PLAN.md §10)."""
        console = self._consoles.get(tab)
        if console is None:
            return
        console.append_log("─" * 46, "info")

        variants = {k: v for k, v in payload['variants'].items() if v}
        for name, values in variants.items():
            console.append_log(f"{name}: {', '.join(values)}", "info")
        for name, value in payload['options'].items():
            console.append_log(f"{name}: {value}", "info")

        combos = 1
        for values in variants.values():
            combos *= max(1, len(values))
        steps = payload['steps']
        console.append_log(f"{len(steps)} paso(s) × {combos} variante(s)", "info")

        for step_id in steps:
            for _ in range(combos):
                pass
            console.append_log(f"paso «{step_id}» — no implementado (stub)", "warn")

        if payload['missing_env']:
            console.append_log(
                f"faltan claves: {', '.join(payload['missing_env'])}", "error"
            )
        else:
            console.append_log("Simulación completada", "ok")
