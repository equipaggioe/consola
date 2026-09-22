from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton
)
from PySide6.QtGui import QPainter, QColor, QKeySequence, QShortcut, QIcon, QPixmap, QFont
from PySide6.QtCore import Qt, QEvent

from ui.menu_bar import ActionMenuBar
from ui.action_search import ActionSearch
from ui.title_bar import TitleBar
from ui.tab_panel import TabPanel, WorkspaceStatusBar
from ui.project_tabs import ProjectTabBar
from ui import project_store, params_store, readiness, favorites
from ui.theme import Colors, Fonts
from ui.palettes import Palette, NEUTRAL
from ui import palettes
from ui.widgets import ToggleSwitch
from core.catalog import applicable_ids
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


class _EdgeGrip(QWidget):
    """Franja invisible sobre una orilla o esquina de la ventana sin marco:
    redimensiona con `startSystemResize`. Va por encima del contenido en vez
    de dejarle un margen propio, asi la barra de titulo toca la orilla."""

    THICKNESS = 5
    CORNER = 10

    def __init__(self, window: QWidget, edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(window)
        self._edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")

    def place(self, w: int, h: int) -> None:
        t, c = self.THICKNESS, self.CORNER
        e = self._edges
        left, right = bool(e & Qt.Edge.LeftEdge), bool(e & Qt.Edge.RightEdge)
        top, bottom = bool(e & Qt.Edge.TopEdge), bool(e & Qt.Edge.BottomEdge)
        if (left or right) and (top or bottom):
            self.setGeometry(0 if left else w - c, 0 if top else h - c, c, c)
        elif left or right:
            self.setGeometry(0 if left else w - t, c, t, h - 2 * c)
        else:
            self.setGeometry(c, 0 if top else h - t, w - 2 * c, t)
        self.raise_()

    def mousePressEvent(self, event):
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemResize(self._edges)


class MainWindow(QMainWindow):
    """Ventana principal: repos (nivel 1) › ejecuciones (nivel 2) › vistas."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Consola")
        self.setWindowIcon(_brand_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1000, 650)
        # Sin marco del sistema: la marca y las pestanas de repos comparten
        # fila con minimizar/maximizar/cerrar (`ui/title_bar.py`). El precio es poner nosotros el arrastre y el
        # redimensionado por los bordes — `_EdgeGrip`, apoyado en
        # `startSystemMove/Resize` para que Windows siga dando su encaje a los lados.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        # Barra de menu: el catalogo entero de acciones, sin ocupar ancho.
        # Junto con el buscador de la misma fila, emite las mismas senales y
        # cae en los mismos manejadores. No es el
        # `menuBar()` de la ventana (eso la pondria por encima de la barra de
        # titulo, que tiene que quedar arriba de todo por los botones de
        # ventana): es una franja mas dentro del layout central.
        self.action_menu = ActionMenuBar(self)

        self.central_widget = QWidget()
        # Selector por nombre y no `QWidget` a secas: una hoja sin selector
        # cascadea a todo hijo sin la suya propia, y el borde de contorno
        # (`_apply_window_border`) terminaba dibujado alrededor de cada campo
        # de texto y cada boton, no solo del borde de la ventana.
        self.central_widget.setObjectName("centralWidget")
        # Sin repo elegido todavia: los grises pelados. Los repinta
        # `_apply_palette` en cuanto hay uno activo.
        self.pal = NEUTRAL
        self.central_widget.setStyleSheet(f"QWidget#centralWidget {{ background: {Colors.BG}; }}")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        # Solo el pixel del borde de contorno: el contenido toca la orilla de la
        # ventana. Maximizada vale 0 (`changeEvent`).
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)

        # --- Nivel 1: barra de titulo con las pestanas de repos ---------
        # Como un navegador: marca, pestanas y botones de ventana en el borde
        # de arriba. Un repo abierto es el contexto de todo lo que se ve
        # debajo, igual que la pestana de un navegador — y asi la ventana se
        # ahorra una fila entera de alto.
        self.project_tabs = ProjectTabBar()

        self.title_bar = TitleBar(self.project_tabs)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        self.main_layout.addWidget(self.title_bar)

        # --- Nivel 2: barra de menu + el modo «solo favoritos» ----------
        self.main_layout.addWidget(self._build_menu_row())

        # --- Cuerpo: espacio de trabajo del repo activo ------------------
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

        self.main_layout.addWidget(self.workspace_stack, 1)

        # --- barra de estado: una sola, a lo ancho de toda la ventana ---
        # Vive aca y no dentro de cada TabPanel para que llegue de borde a
        # borde. Refleja el repo activo y se refresca cuando una tarea de
        # maquina toca el entorno (`TabPanel.machine_changed`).
        self.status_bar = WorkspaceStatusBar(NEUTRAL)
        self.status_bar.security_clicked.connect(self._on_security_clicked)
        self.main_layout.addWidget(self.status_bar)

        # Encima de todo el contenido, asi que se crean al final.
        E = Qt.Edge
        C = Qt.CursorShape
        self._grips = [_EdgeGrip(self, edges, cursor) for edges, cursor in (
            (E.LeftEdge, C.SizeHorCursor), (E.RightEdge, C.SizeHorCursor),
            (E.TopEdge, C.SizeVerCursor), (E.BottomEdge, C.SizeVerCursor),
            (E.LeftEdge | E.TopEdge, C.SizeFDiagCursor),
            (E.RightEdge | E.BottomEdge, C.SizeFDiagCursor),
            (E.RightEdge | E.TopEdge, C.SizeBDiagCursor),
            (E.LeftEdge | E.BottomEdge, C.SizeBDiagCursor),
        )]

        # --- Conexiones ---------------------------------------------------
        self.project_tabs.project_selected.connect(self._on_project_selected)
        self.project_tabs.project_added.connect(self._on_project_added)
        self.project_tabs.project_removed.connect(self._on_project_removed)
        self.project_tabs.project_retinted.connect(self._on_project_retinted)

        self.action_menu.action_requested.connect(self._on_action_requested)
        self.action_menu.focus_search_requested.connect(self.action_search.box.setFocus)

        self.action_search.action_requested.connect(self._on_action_requested)
        self.action_search.run_requested.connect(self._on_run_requested)

        # Favoritas: tres superficies para el mismo conjunto —el filete de la
        # fila del buscador, la estrella de la cabecera de parametros y el
        # podado de los menus—. Quien marca lo guarda, y desde aca se avisa al
        # resto.
        self.action_search.favorites_changed.connect(self._on_favorites_changed)
        self._on_only_favorites(favorites.only_favorites(), save=False)

        proyectos = project_store.load()
        for project in proyectos:
            self._ensure_workspace(project)
        self.project_tabs.load_projects(proyectos)
        if not proyectos:
            self._show_empty_state()

        self._install_shortcuts()

    # --- fila del menu ----------------------------------------------------
    def _build_menu_row(self) -> QWidget:
        """El catalogo de acciones y, a la derecha, el modo «solo favoritos».

        El interruptor no es una accion sino un modo de ver: poda los menus
        de esta barra, asi que va en la misma fila que lo que recorta, no en
        la barra de titulo (donde solo hay chrome de ventana).
        """
        row = QWidget()
        # Selector por nombre y no `QWidget` a secas: una hoja sin selector se
        # hereda a los hijos, y el rotulo del interruptor salia subrayado con
        # el mismo `border-bottom` que cierra la fila.
        row.setObjectName("menuRow")
        self.menu_row = row
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 14, 0)
        lay.setSpacing(0)

        lay.addWidget(self.action_menu, 1)

        # Buscador: la lista de coincidencias cae desde esta fila
        # (`ui/action_search.py`).
        self.action_search = ActionSearch()
        lay.addWidget(self.action_search, 0, Qt.AlignmentFlag.AlignVCenter)

        self.fav_switch = ToggleSwitch("solo favoritos", favorites.only_favorites())
        self.fav_switch.toggled.connect(self._on_only_favorites)
        lay.addWidget(self.fav_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

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
        self.action_menu.set_project_active(False)
        self.action_search.set_project_active(False)
        self._refresh_readiness()
        self._apply_palette(NEUTRAL)
        self.status_bar.clear()
        self.setWindowTitle("Consola")

    # --- atajos ----------------------------------------------------------
    def _install_shortcuts(self) -> None:
        """Los que no cuelgan de ningun item de menu. Ctrl+L vive en
        `ui/menu_bar.py`, sobre su `QAction`: declararlo tambien aqui daria un
        atajo ambiguo y no responderia ninguno de los dos."""
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(lambda: self._cycle(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(lambda: self._cycle(-1))
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self.project_tabs._pick_repo)
        # Por posicion al momento de apretar: reordenar pestanas renumera solo.
        for i in range(9):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self).activated.connect(
                lambda i=i: self._select_nth(i))

    def _select_nth(self, i: int) -> None:
        tabs = self.project_tabs.tabs
        if i < len(tabs):
            self.project_tabs.select_tab(tabs[i])

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
            workspace.sections_changed.connect(self._on_sections_changed)
            workspace.repo_ready.connect(self.project_tabs.open_path)
            self.workspaces[key] = workspace
            self.workspace_stack.addWidget(workspace)
        return workspace

    @property
    def current_workspace(self) -> TabPanel | None:
        w = self.workspace_stack.currentWidget()
        return w if isinstance(w, TabPanel) else None

    # --- ventana sin marco: mover, maximizar, redimensionar --------------
    def _toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for grip in self._grips:
            grip.place(self.width(), self.height())

    def changeEvent(self, event):
        """Maximizada, la ventana pega contra los bordes de la pantalla: ni
        agarre, ni glifo de maximizar, ni borde de contorno."""
        if event.type() == QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self.title_bar.set_maximized(maximized)
            m = 0 if maximized else 1
            self.main_layout.setContentsMargins(m, m, m, m)
            for grip in self._grips:
                grip.setVisible(not maximized)
            self._apply_window_border()
        elif event.type() == QEvent.Type.ActivationChange:
            self._apply_window_border()
        super().changeEvent(event)

    def _apply_window_border(self) -> None:
        """Sin marco del sistema, Windows no le dibuja ninguna silueta a la
        ventana: sin esto, restaurada se confunde contra un fondo oscuro de
        escritorio. El borde toma el color del repo activo —lo pone
        `_apply_accent`, la misma fuente que el fondo de la barra de titulo—
        y solo mientras la ventana tiene el foco, como hace Windows con su
        propio marco. Sin foco se pinta de `border` —el mismo separador
        teñido que usa el resto de la ventana— y no desaparece: asi el
        contenido no se corre un pixel al activar/desactivar.
        Maximizada no hace falta: la ventana pega contra los bordes de la
        pantalla, como el marco de agarre."""
        if self.isMaximized():
            self.central_widget.setStyleSheet(
                f"QWidget#centralWidget {{ background: {self.pal.bg}; }}")
        else:
            color = self.pal.accent if self.isActiveWindow() else self.pal.border
            self.central_widget.setStyleSheet(
                f"QWidget#centralWidget {{ background: {self.pal.bg}; "
                f"border: 1px solid {color}; }}")

    # --- paleta del repo activo --------------------------------------------
    def _apply_palette(self, pal: Palette) -> None:
        """La paleta del repo activo, en todo lo que vive fuera de su espacio
        de trabajo: la barra de titulo, la fila del menu y sus menus
        desplegados, el interruptor de favoritos, el buscador, la barra de
        estado y el borde de contorno de la ventana (`_apply_window_border`)."""
        self.pal = pal
        self.title_bar.set_palette(pal)
        self.action_menu.set_palette(pal)
        self.fav_switch.set_accent(pal.accent)
        self.action_search.set_palette(pal)
        self.status_bar.set_palette(pal)
        self.menu_row.setStyleSheet(
            f"QWidget#menuRow {{ background: {pal.chrome}; "
            f"border-bottom: 1px solid {pal.border}; }}")
        self._apply_window_border()

    # --- favoritas ---------------------------------------------------------
    def _on_only_favorites(self, value: bool, save: bool = True) -> None:
        """El interruptor de la fila del menu: poda los menus de grupo. El
        buscador no lo obedece — busca siempre sobre todas las acciones."""
        if save:
            favorites.set_only_favorites(value)
        self.action_menu.set_only_favorites(value)
        self.action_menu.set_favorites(favorites.favorite_ids())

    def _on_favorites_changed(self, *_args) -> None:
        """Se marco o desmarco una favorita en cualquiera de las superficies:
        las otras se ponen al dia. Guardar ya lo hizo quien la marco."""
        ids = favorites.favorite_ids()
        self.action_menu.set_favorites(ids)
        self.action_search.set_favorites(ids)
        workspace = self.current_workspace
        if workspace is not None:
            workspace.refresh_favorite_star()

    # --- reacciones -------------------------------------------------------
    def _on_project_added(self, project: Project) -> None:
        self._ensure_workspace(project)
        self._on_project_selected(project)

    def _on_project_retinted(self, project: Project) -> None:
        """El repo eligio otro color desde el menu de su pestana. Se repinta su
        espacio de trabajo aunque no sea el activo: el de al lado no puede
        quedarse con los fondos del color viejo esperando a que lo miren."""
        workspace = self.workspaces.get(project_store.identity(project.path))
        pal = palettes.get(project.theme)
        if workspace is not None:
            workspace.set_palette(pal)
        if workspace is self.current_workspace:
            self._apply_palette(pal)
            self._refresh_protection(workspace)

    def _on_project_removed(self, project: Project) -> None:
        workspace = self.workspaces.pop(project_store.identity(project.path), None)
        if workspace is not None:
            self.workspace_stack.removeWidget(workspace)
            workspace.deleteLater()
        # Lo elegido en sus paneles ya no se va a volver a mirar en esta sesion:
        # se baja al repo lo que quedara pendiente y se suelta el cache.
        params_store.forget(project.path)
        if not self.project_tabs.tabs:
            self._show_empty_state()

    def closeEvent(self, event):
        """Los parametros se escriben en rafagas de medio segundo
        (`ui/params_store.py`): al cerrar hay que bajar lo pendiente, o el
        ultimo cambio se pierde por marcar una casilla y cerrar enseguida.

        Tambien detiene las tareas vivas de todos los repos: sin esto un tunel
        SSH o un backend quedaban corriendo sin Consola."""
        params_store.flush()
        for workspace in self.workspaces.values():
            workspace.shutdown()
        super().closeEvent(event)

    def _on_project_selected(self, project: Project) -> None:
        workspace = self._ensure_workspace(project)
        self.workspace_stack.setCurrentWidget(workspace)

        self.action_menu.set_project_active(True)
        self.action_search.set_project_active(True)
        self._refresh_applicable(project)
        self._refresh_readiness()
        self._apply_palette(palettes.get(project.theme))
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
        Seguridad del repo activo (`ADR-0018` §4)."""
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
        """Boton ▶ del buscador: abre la pestana y ejecuta de una."""
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if capability and workspace is not None:
            workspace.quick_run(capability)

    def _refresh_applicable(self, project: Project) -> None:
        """Que acciones tienen sentido en el repo que se acaba de elegir.

        Se recalcula al cambiar de pestana y no al arrancar: lo que la decide
        es lo que hay dentro de ESE repo (`core/catalog.py::applicable_ids`), y
        dos repos de la barra no tienen por que coincidir.
        """
        ids = applicable_ids(project.path)
        self.action_menu.set_applicable(ids)
        self.action_search.set_applicable(ids)

    def _refresh_readiness(self) -> None:
        """Que acciones pueden correr ya sobre el repo activo.

        La cuenta vive en `ui/readiness.py`; la muestra el ▶ de cada fila del
        buscador.
        """
        ready = readiness.ready_ids(self.project_tabs.active_project)
        self.action_search.set_ready(ready)

    def _on_sections_changed(self) -> None:
        """La visibilidad de las secciones es global: se elige desde un repo y
        vale para todos."""
        for workspace in self.workspaces.values():
            workspace.apply_section_visibility()

    def _on_params_changed(self) -> None:
        """Apagar un paso puede dejar de reclamar claves (y encenderlo,
        volver a pedirlas): el ▶ del buscador se recalcula."""
        self._refresh_readiness()

    def _on_env_saved(self, *_args) -> None:
        """La configuracion guardada cambio: puede haber acciones nuevas
        listas para correr sin abrir la pestana, o que dejaron de estarlo."""
        self._refresh_readiness()
