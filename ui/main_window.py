from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QSplitter
)
from PySide6.QtGui import QPainter, QColor, QKeySequence, QShortcut, QIcon, QPixmap, QFont
from PySide6.QtCore import Qt, QEvent, QTimer

from ui.rail import ActionRail
from ui.tab_panel import TabPanel, WorkspaceStatusBar
from ui.project_tabs import ProjectTabBar, ProjectTab
from ui import project_store
from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import Project


def _brand_icon() -> QIcon:
    """El mismo rombo de la marca (BrandMark), como icono de ventana — para
    que la barra de titulo del sistema (junto a minimizar/maximizar) lo
    muestre tambien, no solo la esquina superior izquierda del contenido."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont()
    font.setPixelSize(int(size * 0.8))
    painter.setFont(font)
    painter.setPen(QColor(Colors.ACCENT))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "◇")
    painter.end()
    return QIcon(pixmap)


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

    def set_width(self, width: int) -> None:
        """La marca ocupa la columna del rail: sigue su ancho para que el borde
        inferior coincida con el separador."""
        self.setFixedSize(width, ProjectTab.HEIGHT)

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
        self.setWindowIcon(_brand_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1000, 650)

        self.menuBar().setStyleSheet(f"""
            QMenuBar {{
                background: {Colors.CHROME}; color: {Colors.TEXT};
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QMenuBar::item {{ background: transparent; padding: 4px 10px; }}
            QMenuBar::item:selected {{ background: {Colors.SURFACE_HOVER}; }}
        """)

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

        self.brand = BrandMark(self.rail.preferred_width())
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

        # Rail y espacio de trabajo van en un splitter: el rail se ajusta solo
        # al contenido y ademas se puede fijar arrastrando el separador, igual
        # que el panel de parametros dentro de cada pestana. Doble clic en el
        # separador vuelve al ancho automatico.
        self.body_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.body_splitter.setChildrenCollapsible(False)
        self.body_splitter.setHandleWidth(4)
        self.body_splitter.addWidget(self.rail)
        self.body_splitter.addWidget(self.workspace_stack)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.splitterMoved.connect(self._on_rail_dragged)
        self.body_splitter.handle(1).installEventFilter(self)
        self.rail.width_hint_changed.connect(self._sync_rail_width)

        body_layout.addWidget(self.body_splitter, 1)
        self.main_layout.addLayout(body_layout, 1)
        QTimer.singleShot(0, self._sync_rail_width)

        # --- barra de estado: una sola, a lo ancho de toda la ventana ---
        # Vive aca y no dentro de cada TabPanel para que llegue de borde a borde,
        # por debajo del rail y del espacio de trabajo — no arrancando despues
        # del rail. Refleja el repo activo y se refresca cuando una tarea de
        # maquina toca el entorno (`TabPanel.machine_changed`).
        self.status_bar = WorkspaceStatusBar(Colors.ACCENT)
        self.main_layout.addWidget(self.status_bar)

        # --- Conexiones ---------------------------------------------------
        self.rail.action_requested.connect(self._on_action_requested)
        self.rail.run_requested.connect(self._on_run_requested)
        self.project_tabs.project_selected.connect(self._on_project_selected)
        self.project_tabs.project_added.connect(self._on_project_added)
        self.project_tabs.project_removed.connect(self._on_project_removed)

        self.project_tabs._loading = True
        for project in project_store.load():
            self._ensure_workspace(project)
            self.project_tabs.add_project(project)
        self.project_tabs._loading = False

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
            workspace.env_panel.saved.connect(self._on_env_saved)
            workspace.params_changed.connect(self._on_params_changed)
            workspace.machine_changed.connect(self.status_bar.refresh_tools)
            self.workspaces[key] = workspace
            self.workspace_stack.addWidget(workspace)
        return workspace

    @property
    def current_workspace(self) -> TabPanel | None:
        w = self.workspace_stack.currentWidget()
        return w if isinstance(w, TabPanel) else None

    # --- ancho del rail -------------------------------------------------
    def eventFilter(self, obj, event):
        """Doble clic en el separador del rail = volver al ancho automatico."""
        if obj is self.body_splitter.handle(1) and event.type() == QEvent.Type.MouseButtonDblClick:
            self.rail.clear_user_width()
            return True
        return super().eventFilter(obj, event)

    def _on_rail_dragged(self, pos: int, index: int) -> None:
        # `pos` es la posicion del separador = ancho del rail. El rail se clampa
        # solo en `set_user_width`; la marca copia el resultado ya clampado.
        self.brand.set_width(self.rail.set_user_width(pos))

    def _sync_rail_width(self) -> None:
        """Aplica el ancho preferido del rail (fijado por el usuario, o el que
        pide el contenido) al splitter y a la marca."""
        sizes = self.body_splitter.sizes()
        total = sum(sizes) or self.width()
        target = self.rail.preferred_width()
        self.body_splitter.setSizes([target, max(1, total - target)])
        self.brand.set_width(target)

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
        self.status_bar.set_project(project.name, project.icon)
        self.status_bar.set_accent(project.color)
        self.setWindowTitle(f"Consola — {project.name}")

    def _on_action_requested(self, capability_id: str) -> None:
        """El clic abre (o enfoca) la pestana de la accion; no ejecuta.
        Ejecutar es apretar Ejecutar en el panel de parametros."""
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if capability and workspace is not None:
            workspace.open_tab(capability)

    def _on_run_requested(self, capability_id: str) -> None:
        """Boton de correr del rail: abre la pestana y ejecuta de una."""
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if capability and workspace is not None:
            workspace.quick_run(capability)

    def _on_params_changed(self) -> None:
        """Apagar un paso puede dejar de reclamar claves (y encenderlo,
        volver a pedirlas): el boton de correr del rail se recalcula."""
        self.rail.refresh_readiness()

    def _on_env_saved(self, *_args) -> None:
        """La configuracion guardada cambio: puede haber acciones nuevas
        listas para correr sin abrir la pestana, o que dejaron de estarlo."""
        self.rail.refresh_readiness()
