from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget
)
from PySide6.QtGui import QPainter, QColor, QKeySequence, QShortcut

from ui.rail import ActionRail
from ui.tab_panel import TabPanel
from ui.project_tabs import ProjectTabBar, ProjectTab
from ui.status_bar import StatusBar
from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import MOCK_PROJECTS, Project


class BrandMark(QWidget):
    """Marca de la aplicacion, alineada con el rail y tenida por el repo activo."""

    def __init__(self, width: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, ProjectTab.HEIGHT)
        self.accent = Colors.ACCENT

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(9)

        self.diamond = QLabel("◇")
        self.diamond.setStyleSheet(f"background: transparent; color: {self.accent}; font-size: {Fonts.SIZE_XL}px;")

        self.title = QLabel("CONSOLA")
        self.title.setStyleSheet(f"""
            background: transparent;
            color: {Colors.TEXT};
            font-size: {Fonts.SIZE_LG}px;
            font-weight: 700;
            letter-spacing: 4px;
        """)

        layout.addWidget(self.diamond)
        layout.addWidget(self.title)
        layout.addStretch()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.diamond.setStyleSheet(
            f"background: transparent; color: {accent}; font-size: {Fonts.SIZE_XL}px;"
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(Colors.CHROME))
        p.fillRect(0, self.height() - 2, self.width(), 2, QColor(self.accent))
        p.end()


class MainWindow(QMainWindow):
    """Ventana principal: repos (nivel 1) › ejecuciones (nivel 2) › vistas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Consola")
        self.resize(1500, 950)
        self.setMinimumSize(1000, 650)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- Nivel 1: barra superior con marca + pestanas de repos ------
        self.rail = ActionRail()

        self.top_chrome = QWidget()
        self.top_chrome.setFixedHeight(ProjectTab.HEIGHT)
        self.top_chrome.setStyleSheet(f"background: {Colors.CHROME};")
        top_layout = QHBoxLayout(self.top_chrome)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.brand = BrandMark(self.rail.minimumWidth())
        self.project_tabs = ProjectTabBar()

        top_layout.addWidget(self.brand)
        top_layout.addWidget(self.project_tabs, 1)

        self.main_layout.addWidget(self.top_chrome)

        # --- Cuerpo: rail + espacio de trabajo del repo activo ----------
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.workspace_stack = QStackedWidget()
        self.workspaces: dict[int, TabPanel] = {}

        body_layout.addWidget(self.rail)
        body_layout.addWidget(self.workspace_stack, 1)
        self.main_layout.addLayout(body_layout, 1)

        # --- Barra de estado --------------------------------------------
        self.status_bar = StatusBar()
        self.main_layout.addWidget(self.status_bar)

        # --- Conexiones ---------------------------------------------------
        self.rail.action_requested.connect(self._on_action_requested)
        self.project_tabs.project_selected.connect(self._on_project_selected)
        self.project_tabs.project_added.connect(self._on_project_added)
        self.project_tabs.project_removed.connect(self._on_project_removed)

        for project in MOCK_PROJECTS:
            self._ensure_workspace(project)
            self.project_tabs.add_project(project)

        self._install_shortcuts()

    # --- atajos ----------------------------------------------------------
    def _install_shortcuts(self) -> None:
        for i in range(1, 10):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i - 1: self._select_index(idx))
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(lambda: self._cycle(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(lambda: self._cycle(-1))
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self.project_tabs._pick_repo)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.rail.filter_box.setFocus)

    def _select_index(self, idx: int) -> None:
        if 0 <= idx < len(self.project_tabs.tabs):
            self.project_tabs.select_tab(self.project_tabs.tabs[idx])

    def _cycle(self, delta: int) -> None:
        tabs = self.project_tabs.tabs
        if not tabs:
            return
        current = self.project_tabs._active
        i = tabs.index(current) if current in tabs else 0
        self.project_tabs.select_tab(tabs[(i + delta) % len(tabs)])

    # --- espacios de trabajo ---------------------------------------------
    def _ensure_workspace(self, project: Project) -> TabPanel:
        key = id(project)
        workspace = self.workspaces.get(key)
        if workspace is None:
            workspace = TabPanel(project)
            self.workspaces[key] = workspace
            self.workspace_stack.addWidget(workspace)
        return workspace

    @property
    def current_workspace(self) -> TabPanel | None:
        w = self.workspace_stack.currentWidget()
        return w if isinstance(w, TabPanel) else None

    # --- reacciones -------------------------------------------------------
    def _on_project_added(self, project: Project) -> None:
        self._ensure_workspace(project)
        self._on_project_selected(project)

    def _on_project_removed(self, project: Project) -> None:
        workspace = self.workspaces.pop(id(project), None)
        if workspace is not None:
            self.workspace_stack.removeWidget(workspace)
            workspace.deleteLater()

    def _on_project_selected(self, project: Project) -> None:
        workspace = self._ensure_workspace(project)
        self.workspace_stack.setCurrentWidget(workspace)

        self.rail.set_project(project)
        self.brand.set_accent(project.color)
        self.status_bar.set_accent(project.color)
        self.status_bar.set_project(project.name)
        self.setWindowTitle(f"Consola — {project.name}")

    def _on_action_requested(self, capability_id: str) -> None:
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if not capability or workspace is None:
            return
        console = workspace.open_tab(capability)
        if console is not None:
            console.write_stub_message(f"{capability.name} · {workspace.project.name}")
