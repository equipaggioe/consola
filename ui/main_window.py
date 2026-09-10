from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QSplitter, QPushButton
)
from PySide6.QtGui import QPainter, QColor, QKeySequence, QShortcut, QIcon, QPixmap, QFont
from PySide6.QtCore import Qt, QEvent, QTimer

from ui.rail import ActionRail
from ui.menu_bar import ActionMenuBar
from ui.title_bar import TitleBar
from ui.tab_panel import TabPanel, WorkspaceStatusBar
from ui.project_tabs import ProjectTabBar, ProjectTab
from ui import project_store, params_store, readiness, favorites
from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import Project


def _brand_icon() -> QIcon:
    """El mismo rombo de la marca (`ui/title_bar.py`), como icono de ventana —
    para que la barra de tareas y el conmutador de ventanas de Windows lo
    muestren tambien, no solo
    la esquina superior izquierda del contenido."""
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


class MainWindow(QMainWindow):
    """Ventana principal: repos (nivel 1) › ejecuciones (nivel 2) › vistas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Consola")
        self.setWindowIcon(_brand_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1000, 650)
        # Sin marco del sistema: la marca, el catalogo de acciones y el modo
        # «solo favoritos» comparten fila con minimizar/maximizar/cerrar
        # (`ui/title_bar.py`). El precio es poner nosotros el arrastre y el
        # redimensionado por los bordes — `_edge_at` y el filtro de eventos
        # del widget central, apoyados en `startSystemMove/Resize` para que
        # Windows siga dando su encaje a los lados.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        # Barra de menu: el catalogo entero de acciones, sin ocupar ancho.
        # Convive con el rail, no lo reemplaza — las dos superficies emiten
        # las mismas senales y caen en los mismos manejadores. Ya no es el
        # `menuBar()` de la ventana: es un tramo de la barra de titulo.
        self.action_menu = ActionMenuBar(self)

        self.central_widget = QWidget()
        self.central_widget.setStyleSheet(f"background: {Colors.CHROME};")
        self.central_widget.setMouseTracking(True)
        self.central_widget.installEventFilter(self)
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        # Los margenes son el marco de agarre para redimensionar: dejan una
        # franja del widget central sin tapar por sus hijos, que es donde
        # `eventFilter` puede ver el puntero. Maximizada valen 0 (`changeEvent`).
        m = self.RESIZE_MARGIN
        self.main_layout.setContentsMargins(m, m, m, m)
        self.main_layout.setSpacing(0)

        # --- Nivel 0: barra de titulo (marca, menus, favoritos, ventana) ---
        self.title_bar = TitleBar(self.action_menu)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.only_favorites_changed.connect(self._on_only_favorites)
        self.main_layout.addWidget(self.title_bar)

        # --- Nivel 1: barra superior con las pestanas de repos ----------
        # La marca se fue de aqui: ahora abre la barra de titulo, y esta fila
        # es solo repos.
        self.rail = ActionRail()

        self.top_chrome = QWidget()
        self.top_chrome.setFixedHeight(ProjectTab.HEIGHT)
        self.top_chrome.setStyleSheet(f"background: {Colors.CHROME};")
        top_layout = QHBoxLayout(self.top_chrome)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        self.project_tabs = ProjectTabBar()
        top_layout.addWidget(self.project_tabs, 1)

        self.main_layout.addWidget(self.top_chrome)

        # --- Cuerpo: rail + espacio de trabajo del repo activo ----------
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.workspace_stack = QStackedWidget()
        # Indexados por la ruta normalizada del repo, no por la identidad del
        # objeto: CPython reusa la direccion de uno liberado, asi que quitar
        # un repo y anadir otro podia darle al nuevo el espacio de trabajo del
        # viejo. La ruta es la identidad real de un repo — es la misma con la
        # que se guardan sus parametros y su `.consola/config.env`.
        self.workspaces: dict[str, TabPanel] = {}
        # No hay una lista de repos de fabrica (`core/projects.py`): la primera
        # vez que se abre Consola, y cada vez que se cierra el ultimo repo, la
        # pila muestra esto en vez de un TabPanel.
        self.empty_state = self._build_empty_state()
        self.workspace_stack.addWidget(self.empty_state)

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
        self.status_bar.security_clicked.connect(self._on_security_clicked)
        self.main_layout.addWidget(self.status_bar)

        # --- Conexiones ---------------------------------------------------
        self.rail.action_requested.connect(self._on_action_requested)
        self.rail.run_requested.connect(self._on_run_requested)
        self.project_tabs.project_selected.connect(self._on_project_selected)
        self.project_tabs.project_added.connect(self._on_project_added)
        self.project_tabs.project_removed.connect(self._on_project_removed)
        self.project_tabs.order_changed.connect(self._sync_repo_menu)

        self.action_menu.action_requested.connect(self._on_action_requested)
        self.action_menu.run_requested.connect(self._on_run_requested)
        self.action_menu.add_project_requested.connect(self.project_tabs._pick_repo)
        self.action_menu.close_project_requested.connect(self._close_active_project)
        self.action_menu.project_chosen.connect(self._select_project_by_path)
        self.action_menu.focus_filter_requested.connect(self.rail.filter_box.setFocus)
        self.action_menu.rail_auto_width_requested.connect(self.rail.clear_user_width)

        # Favoritas: tres superficies para el mismo conjunto —el filete de la
        # fila del rail, la estrella de la cabecera de parametros y el podado
        # de los menus—. Quien marca lo guarda, y desde aca se avisa al resto.
        self.rail.favorites_changed.connect(self._on_favorites_changed)
        self._on_only_favorites(favorites.only_favorites(), save=False)

        proyectos = project_store.load()
        for project in proyectos:
            self._ensure_workspace(project)
        self.project_tabs.load_projects(proyectos)
        self._sync_repo_menu()
        if not proyectos:
            self._show_empty_state()

        self._install_shortcuts()

    # --- estado vacio: sin ningun repositorio en pestanas -----------------
    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {Colors.BG};")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        diamond = QLabel("◇")
        diamond.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 54px;")
        diamond.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("SIN REPOSITORIOS ABIERTOS")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_XXL}px; "
            f"font-weight: 300; letter-spacing: 6px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Añade la carpeta de un proyecto para empezar")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_BASE}px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        add_btn = QPushButton("+  Añadir repositorio")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(38)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ACCENT}; color: {Colors.BG};
                border: none; border-radius: 6px; padding: 0 24px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
        """)
        add_btn.clicked.connect(lambda: self.project_tabs._pick_repo())

        lay.addWidget(diamond, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(16)
        lay.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _show_empty_state(self) -> None:
        self.workspace_stack.setCurrentWidget(self.empty_state)
        self.rail.clear_project()
        self.action_menu.set_project_active(False)
        self._refresh_readiness()
        self.title_bar.set_accent(Colors.ACCENT)
        self.status_bar.clear()
        self.setWindowTitle("Consola")

    # --- atajos ----------------------------------------------------------
    def _install_shortcuts(self) -> None:
        """Solo los que no cuelgan de ningun item de menu.

        Ctrl+T (anadir repo), Ctrl+L (filtrar) y Ctrl+1..9 (saltar a un repo)
        viven ahora en `ui/menu_bar.py`, sobre la propia `QAction`: asi el
        atajo se lee al lado de lo que dispara. Declararlos tambien aqui daria
        un atajo ambiguo y no responderia ninguno de los dos.
        """
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(lambda: self._cycle(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(lambda: self._cycle(-1))

    def _select_project_by_path(self, path: str) -> None:
        """Item del menu Repositorio: activa ese repo. Va por ruta y no por
        indice porque la lista se puede reordenar arrastrando pestanas."""
        tab = self.project_tabs.find_tab(path)
        if tab is not None:
            self.project_tabs.select_tab(tab)

    def _close_active_project(self) -> None:
        tab = self.project_tabs._active
        if tab is not None:
            self.project_tabs.remove_tab(tab)

    def _sync_repo_menu(self) -> None:
        """El menu Repositorio refleja las pestanas: cuales hay, en que orden
        (de ahi salen los Ctrl+1..9) y cual esta activa."""
        active = self.project_tabs.active_project
        self.action_menu.set_projects(
            [t.project for t in self.project_tabs.tabs],
            active.path if active else None)

    def _cycle(self, delta: int) -> None:
        tabs = self.project_tabs.tabs
        if not tabs:
            return
        current = self.project_tabs._active
        i = tabs.index(current) if current in tabs else 0
        self.project_tabs.select_tab(tabs[(i + delta) % len(tabs)])

    # --- espacios de trabajo ---------------------------------------------
    def _ensure_workspace(self, project: Project) -> TabPanel:
        key = project_store.identity(project.path)
        workspace = self.workspaces.get(key)
        if workspace is None:
            workspace = TabPanel(project)
            workspace.env_panel.saved.connect(self._on_env_saved)
            workspace.security_panel.changed.connect(
                lambda _state, w=workspace: self._on_protection_changed(w))
            workspace.params_changed.connect(self._on_params_changed)
            workspace.machine_changed.connect(self.status_bar.refresh_tools)
            workspace.favorite_changed.connect(self._on_favorites_changed)
            self.workspaces[key] = workspace
            self.workspace_stack.addWidget(workspace)
        return workspace

    @property
    def current_workspace(self) -> TabPanel | None:
        w = self.workspace_stack.currentWidget()
        return w if isinstance(w, TabPanel) else None

    # --- ventana sin marco: mover, maximizar, redimensionar --------------
    # Franja de borde que agarra el redimensionado. Los hijos de
    # `central_widget` estan metidos hacia adentro por los margenes del layout,
    # asi que los eventos de esta franja llegan al widget central — que es
    # donde los espera `eventFilter`.
    RESIZE_MARGIN = 5

    def _toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event):
        """Maximizada, la ventana pega contra los bordes de la pantalla: ni
        marco de agarre ni glifo de maximizar."""
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self.title_bar.set_maximized(maximized)
            m = 0 if maximized else self.RESIZE_MARGIN
            self.main_layout.setContentsMargins(m, m, m, m)
        super().changeEvent(event)

    def _edge_at(self, pos) -> Qt.Edge:
        """Que borde toca el puntero, o `Qt.Edge(0)` si esta adentro."""
        if self.isMaximized():
            return Qt.Edge(0)
        m = self.RESIZE_MARGIN
        w, h = self.central_widget.width(), self.central_widget.height()
        edges = Qt.Edge(0)
        if pos.x() <= m:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= w - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= m:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= h - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    _CURSORS = {
        Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
        Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
        Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
        Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
        Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
    }

    # --- ancho del rail y bordes de la ventana ---------------------------
    def eventFilter(self, obj, event):
        """Doble clic en el separador del rail = volver al ancho automatico.
        Sobre el widget central, los bordes redimensionan la ventana."""
        if obj is self.central_widget:
            kind = event.type()
            if kind == QEvent.Type.MouseMove:
                edges = self._edge_at(event.position().toPoint())
                self.central_widget.setCursor(
                    self._CURSORS.get(edges, Qt.CursorShape.ArrowCursor))
            elif kind == QEvent.Type.MouseButtonPress:
                edges = self._edge_at(event.position().toPoint())
                handle = self.windowHandle()
                if edges and handle is not None:
                    handle.startSystemResize(edges)
                    return True
            elif kind == QEvent.Type.Leave:
                self.central_widget.unsetCursor()
            return super().eventFilter(obj, event)
        # El filtro del widget central se instala en pleno `__init__`, antes de
        # que exista el splitter: por eso su rama va primero y esta consulta
        # solo se hace cuando el evento no es suyo.
        splitter = getattr(self, 'body_splitter', None)
        if (splitter is not None and obj is splitter.handle(1)
                and event.type() == QEvent.Type.MouseButtonDblClick):
            self.rail.clear_user_width()
            return True
        return super().eventFilter(obj, event)

    # --- solo favoritos: un modo, tres superficies ------------------------
    def _on_only_favorites(self, value: bool, save: bool = True) -> None:
        """El interruptor de la barra de titulo. Poda a la vez el rail y los
        menus de grupo: es el mismo conjunto de acciones visto de dos maneras,
        y que una superficie mostrara todo y la otra no seria confuso."""
        if save:
            favorites.set_only_favorites(value)
        self.rail.set_only_favorites(value)
        self.action_menu.set_only_favorites(value)
        self.action_menu.set_favorites(favorites.favorite_ids())

    def _on_favorites_changed(self, *_args) -> None:
        """Se marco o desmarco una favorita en cualquiera de las superficies:
        las otras se ponen al dia. Guardar ya lo hizo quien la marco."""
        ids = favorites.favorite_ids()
        self.action_menu.set_favorites(ids)
        self.rail.refresh_favorites()
        workspace = self.current_workspace
        if workspace is not None:
            workspace.refresh_favorite_star()

    def _on_rail_dragged(self, pos: int, index: int) -> None:
        # `pos` es la posicion del separador = ancho del rail. El rail se
        # clampa solo en `set_user_width`.
        self.rail.set_user_width(pos)

    def _sync_rail_width(self) -> None:
        """Aplica el ancho preferido del rail (fijado por el usuario, o el que
        pide el contenido) al splitter."""
        sizes = self.body_splitter.sizes()
        total = sum(sizes) or self.width()
        target = self.rail.preferred_width()
        self.body_splitter.setSizes([target, max(1, total - target)])

    # --- reacciones -------------------------------------------------------
    def _on_project_added(self, project: Project) -> None:
        self._ensure_workspace(project)
        self._on_project_selected(project)
        self._sync_repo_menu()

    def _on_project_removed(self, project: Project) -> None:
        workspace = self.workspaces.pop(project_store.identity(project.path), None)
        if workspace is not None:
            self.workspace_stack.removeWidget(workspace)
            workspace.deleteLater()
        # Lo elegido en sus paneles ya no se va a volver a mirar en esta sesion:
        # se baja al repo lo que quedara pendiente y se suelta el cache.
        params_store.forget(project.path)
        self._sync_repo_menu()
        if not self.project_tabs.tabs:
            self._show_empty_state()

    def closeEvent(self, event):
        """Los parametros se escriben en rafagas de medio segundo
        (`ui/params_store.py`): al cerrar hay que bajar lo pendiente, o el
        ultimo cambio se pierde por marcar una casilla y cerrar enseguida."""
        params_store.flush()
        super().closeEvent(event)

    def _on_project_selected(self, project: Project) -> None:
        workspace = self._ensure_workspace(project)
        self.workspace_stack.setCurrentWidget(workspace)

        self.rail.set_project(project)
        self.action_menu.set_project_active(True)
        self._refresh_readiness()
        self._sync_repo_menu()
        self.title_bar.set_accent(project.color)
        self.status_bar.set_project(project.name, project.icon)
        self.status_bar.set_accent(project.color)
        self._refresh_protection(workspace)
        self.setWindowTitle(f"Consola — {project.name}")

    def _refresh_protection(self, workspace: TabPanel) -> None:
        """Lo que el repo de ESE espacio de trabajo tiene protegido ahora
        mismo, para el indicador de la barra de estado. Lee el panel
        (`security_panel.state()`), que es la misma fuente que consulta el
        seguro al correr (`TabPanel._guard_ok`): el indicador no puede decir
        una cosa y el guard aplicar otra."""
        self.status_bar.set_protection(workspace.security_panel.state())

    def _on_protection_changed(self, workspace: TabPanel) -> None:
        if workspace is self.current_workspace:
            self._refresh_protection(workspace)

    def _on_security_clicked(self) -> None:
        """Clic en el indicador de la barra de estado: salta a la seccion
        Seguridad del repo activo (`docs/seguro-destructivos.md` §4)."""
        workspace = self.current_workspace
        if workspace is not None:
            workspace.reveal_security()

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

    def _refresh_readiness(self) -> None:
        """Que acciones pueden correr ya sobre el repo activo.

        La cuenta se hace una sola vez (`ui/readiness.py`) y se reparte a las
        dos superficies que la muestran: el ▶ de cada fila del rail y el
        marcador ▸ del menu. Si cada una la calculara por su cuenta podrian
        discrepar, y son la misma pregunta.
        """
        ready = readiness.ready_ids(self.project_tabs.active_project)
        self.rail.refresh_readiness(ready)
        self.action_menu.set_ready(ready)

    def _on_params_changed(self) -> None:
        """Apagar un paso puede dejar de reclamar claves (y encenderlo,
        volver a pedirlas): el boton de correr del rail se recalcula."""
        self._refresh_readiness()

    def _on_env_saved(self, *_args) -> None:
        """La configuracion guardada cambio: puede haber acciones nuevas
        listas para correr sin abrir la pestana, o que dejaron de estarlo."""
        self._refresh_readiness()
