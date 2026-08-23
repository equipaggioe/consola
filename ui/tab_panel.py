from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPainterPath

from ui.theme import Colors, Fonts
from core.registry import Capability
from core.projects import Project
from ui.console_view import ConsoleView


class SubTabButton(QWidget):
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
        self.close_btn.setVisible(False)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.close_btn)

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
        self.close_btn.setVisible(True)
        self._sync_text()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.close_btn.setVisible(False)
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit()
        super().mousePressEvent(event)

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
        elif self._hovered:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))
        p.end()


class ViewSwitcher(QWidget):
    """Barra inferior del espacio de trabajo: vistas de la ejecucion activa."""
    view_changed = Signal(str)

    VIEWS = ["Consola", "Bitacora", "Historial", "Configuracion"]

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setFixedHeight(34)
        self.setStyleSheet(f"""
            ViewSwitcher {{
                background: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(20)

        self.labels: dict[str, QLabel] = {}
        for name in self.VIEWS:
            lbl = QLabel(name)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.mousePressEvent = lambda e, n=name: self.set_view(n)
            self.labels[name] = lbl
            layout.addWidget(lbl)

        layout.addStretch()

        self.status_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")
        layout.addWidget(self.status_label)

        self._current = self.VIEWS[0]
        self._restyle()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def set_view(self, name: str) -> None:
        self._current = name
        self._restyle()
        self.view_changed.emit(name)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _restyle(self) -> None:
        for name, lbl in self.labels.items():
            if name == self._current:
                lbl.setStyleSheet(
                    f"color: {self.accent}; font-size: {Fonts.SIZE_SM}px; font-weight: 600;"
                )
            else:
                lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;")


class TabPanel(QWidget):
    """Espacio de trabajo de UN repositorio.

    Contiene el segundo nivel de pestanas (las ejecuciones de ese repo),
    el area de consola y la barra de vistas. Cada repo tiene su propia
    instancia, asi que las sub-pestanas nunca se mezclan entre repos.
    """

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.accent = project.color

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

        self.empty_hint = QLabel("sin ejecuciones — lanza una accion del panel izquierdo")
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

        # --- barra de vistas -----------------------------------------
        self.view_switcher = ViewSwitcher(self.accent)

        self.layout.addWidget(self.sub_bar)
        self.layout.addWidget(self.content_area, 1)
        self.layout.addWidget(self.view_switcher)

        self.tabs: list[SubTabButton] = []
        self._consoles: dict[SubTabButton, ConsoleView] = {}

    # --- construccion ------------------------------------------------
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

    # --- API ---------------------------------------------------------
    def open_tab(self, capability: Capability, axis_value: str = '') -> ConsoleView:
        title = f"{capability.name} {axis_value}".strip()

        # Si ya existe una pestana para esta capacidad, se reutiliza.
        for tab in self.tabs:
            if tab.title == title:
                self._activate(tab)
                return self._consoles[tab]

        tab = SubTabButton(title, capability.icon, self.accent)
        self.tabs_layout.addWidget(tab)
        self.tabs.append(tab)

        console = ConsoleView(self.content_area)
        self.content_area.addWidget(console)
        self._consoles[tab] = console

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

    def current_console(self) -> ConsoleView | None:
        w = self.content_area.currentWidget()
        return w if isinstance(w, ConsoleView) else None

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.view_switcher.set_accent(accent)
        self.diamond_label.setStyleSheet(f"color: {accent}; font-size: 54px;")
        for tab in self.tabs:
            tab.set_accent(accent)

    def set_status(self, text: str) -> None:
        self.view_switcher.set_status(text)

    # --- interno ------------------------------------------------------
    def _activate(self, tab: SubTabButton) -> None:
        for t in self.tabs:
            t.set_active(t is tab)
        console = self._consoles.get(tab)
        if console is not None:
            self.content_area.setCurrentWidget(console)
