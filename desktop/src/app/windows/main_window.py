"""The main window."""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QResizeEvent,
    QShortcut,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import (
    favorites,
    palettes,
    params_store,
    project_store,
    readiness,
    section_visibility,
)
from app.services.catalog import applicable_ids
from app.services.palettes import NEUTRAL, Palette
from app.services.projects import Project
from app.services.registry import registry
from app.services.repo_logo import RepoLogo
from app.theme import Colors, Fonts
from app.widgets.action_menu_bar import ActionMenuBar
from app.widgets.action_search import ActionSearch
from app.widgets.project_tab_bar import ProjectTabBar
from app.widgets.tab_panel import TabPanel
from app.widgets.title_bar import TitleBar
from app.widgets.workspace_status_bar import WorkspaceStatusBar

# How long to wait before recounting which actions are ready. Short: the
# time a burst of typing takes to stop, and what is recomputed is
# nothing looked at while typing (the ▶ of the search's rows).
_READINESS_MS = 200

# The window's size and position, and the state of its bars.
_GEOMETRY_KEY = "main_window/geometry"
_STATE_KEY = "main_window/state"


def _brand_icon() -> QIcon:
    """Return the brand's diamond (`widgets/title_bar.py`) as an icon.

    So Windows's taskbar and window switcher show it too.
    """
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
    """An invisible strip over an edge or corner of the window.

    It resizes with `startSystemResize`. It goes over the content
    instead of leaving a margin of its own, so the title bar touches the
    edge.
    """

    THICKNESS = 5
    CORNER = 10

    def __init__(self, window: QWidget, edges: Qt.Edge, cursor: Qt.CursorShape) -> None:
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

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemResize(self._edges)


class MainWindow(QMainWindow):
    """The main window: repos (level 1) › runs (level 2) › views."""

    def __init__(self) -> None:
        """Build the window and open the saved repos."""
        super().__init__()
        self.setWindowTitle("Consola")
        self.setWindowIcon(_brand_icon())
        self.resize(1500, 950)
        self.setMinimumSize(1000, 650)
        # No system frame: the brand and repo tabs share a row with
        # minimize, maximize and close (`widgets/title_bar.py`). The
        # price is supplying the drag and the edge resizing ourselves:
        # `_EdgeGrip`, resting on `startSystemMove/Resize` so Windows
        # keeps giving its side snapping.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

        # It gathers in one pass the requests for recounting the
        # search's ▶ (`_refresh_readiness`).
        self._readiness_timer = QTimer(self)
        self._readiness_timer.setSingleShot(True)
        self._readiness_timer.setInterval(_READINESS_MS)
        self._readiness_timer.timeout.connect(self._do_refresh_readiness)

        # Menu bar: the whole action catalog, taking no width. With the
        # search on the same row, it emits the same signals and falls on
        # the same handlers. It is not the window's `menuBar()`, which
        # would sit above the title bar, which has to stay on top for
        # the window buttons: it is one more strip in the central
        # layout.
        self.action_menu = ActionMenuBar(self)

        self.central_widget = QWidget()
        # A selector by name and not a bare `QWidget`: a sheet without a
        # selector cascades to every child without its own, and the
        # outline border (`_apply_window_border`) ended up drawn around
        # each text field and button, not just the window's edge.
        self.central_widget.setObjectName("centralWidget")
        # With no repo chosen yet: the bare grays. `_apply_palette`
        # repaints them as soon as one is active.
        self.pal = NEUTRAL
        self.central_widget.setStyleSheet(f"QWidget#centralWidget {{ background: {Colors.BG}; }}")
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)
        # Only the outline border's pixel: the content touches the
        # window's edge. Maximized it is 0 (`changeEvent`).
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)

        # --- Level 1: title bar with the repo tabs ---
        #
        # Like a browser: brand, tabs and window buttons on the top
        # edge. An open repo is the context of all that shows below,
        # like a browser's tab, and the window saves a whole row of
        # height.
        self.project_tabs = ProjectTabBar()

        self.title_bar = TitleBar(self.project_tabs)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        self.main_layout.addWidget(self.title_bar)

        # --- Level 2: menu bar and search ---
        self.main_layout.addWidget(self._build_menu_row())

        # --- Body: the active repo's workspace ---
        self.workspace_stack = QStackedWidget()
        # Indexed by the repo's normalized path, not the object's
        # identity: CPython reuses a freed one's address, so removing a
        # repo and adding another could give the new one the old
        # workspace. The path is a repo's real identity, the same its
        # parameters and `.consola/config.env` save under.
        self.workspaces: dict[str, TabPanel] = {}
        # There is no factory list of repos (`services/projects.py`):
        # the first time Consola opens, and each time the last repo
        # closes, the stack shows this instead of a TabPanel.
        self.empty_state = self._build_empty_state()
        self.workspace_stack.addWidget(self.empty_state)

        self.main_layout.addWidget(self.workspace_stack, 1)

        # --- status bar: only one, across the whole window ---
        #
        # It lives here and not in each TabPanel so it reaches edge to
        # edge. It reflects the active repo and refreshes when a machine
        # task touches the environment (`TabPanel.machine_changed`).
        self.status_bar = WorkspaceStatusBar(NEUTRAL)
        self.status_bar.security_clicked.connect(self._on_security_clicked)
        self.main_layout.addWidget(self.status_bar)

        # Over all the content, so they are created last.
        edge = Qt.Edge
        cursor_shape = Qt.CursorShape
        self._grips = [
            _EdgeGrip(self, edges, cursor)
            for edges, cursor in (
                (edge.LeftEdge, cursor_shape.SizeHorCursor),
                (edge.RightEdge, cursor_shape.SizeHorCursor),
                (edge.TopEdge, cursor_shape.SizeVerCursor),
                (edge.BottomEdge, cursor_shape.SizeVerCursor),
                (edge.LeftEdge | edge.TopEdge, cursor_shape.SizeFDiagCursor),
                (edge.RightEdge | edge.BottomEdge, cursor_shape.SizeFDiagCursor),
                (edge.RightEdge | edge.TopEdge, cursor_shape.SizeBDiagCursor),
                (edge.LeftEdge | edge.BottomEdge, cursor_shape.SizeBDiagCursor),
            )
        ]

        # --- Connections ---
        self.project_tabs.project_selected.connect(self._on_project_selected)
        self.project_tabs.project_added.connect(self._on_project_added)
        self.project_tabs.project_removed.connect(self._on_project_removed)
        self.project_tabs.project_retinted.connect(self._on_project_retinted)

        self.action_menu.action_requested.connect(self._on_action_requested)
        self.action_menu.only_favorites_toggled.connect(self._on_only_favorites)
        self.action_menu.section_toggled.connect(self._on_section_toggled)

        self.action_search.action_requested.connect(self._on_action_requested)
        self.action_search.run_requested.connect(self._on_run_requested)

        # Favorites: three surfaces for one set, the search row's
        # stripe, the star next to Run and the menus' pruning. Whoever
        # marks saves it, and from here the rest are told.
        self.action_search.favorites_changed.connect(self._on_favorites_changed)
        self._on_only_favorites(favorites.only_favorites(), save=False)

        projects = project_store.load()
        for project in projects:
            self._ensure_workspace(project)
        self.project_tabs.load_projects(projects)
        if not projects:
            self._show_empty_state()

        self._install_shortcuts()
        self._restore_layout()

    def _restore_layout(self) -> None:
        # The size, position and state of the last close. The first time
        # nothing is saved, and the window keeps its default size.
        settings = QSettings()
        geometry = settings.value(_GEOMETRY_KEY)
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = settings.value(_STATE_KEY)
        if state is not None:
            self.restoreState(state)

    # --- menu row ---
    def _build_menu_row(self) -> QWidget:
        """Build the action menus and the search.

        «Solo favoritos» is in the bar's Ver menu
        (`widgets/action_menu_bar.py`).
        """
        row = QWidget()
        # A selector by name and not a bare `QWidget`: a sheet without a
        # selector inherits to the children, which came out underlined
        # by the same `border-bottom` that closes the row.
        row.setObjectName("menuRow")
        self.menu_row = row
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 14, 0)
        lay.setSpacing(0)

        lay.addWidget(self.action_menu, 1)

        # Search: the list of matches falls from this row
        # (`widgets/action_search.py`).
        self.action_search = ActionSearch()
        lay.addWidget(self.action_search, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    # --- empty state: no repository in tabs ---
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
            f"font-weight: 300; letter-spacing: 6px;"
        )
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

    # --- shortcuts ---
    def _install_shortcuts(self) -> None:
        """Set the window's shortcuts; none hangs from a menu item."""
        QShortcut(QKeySequence("Ctrl+Tab"), self).activated.connect(lambda: self._cycle(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self).activated.connect(lambda: self._cycle(-1))
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self.project_tabs._pick_repo)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(
            lambda: self.action_search.box.setFocus()
        )
        # By position on pressing: reordering tabs renumbers by itself.
        for i in range(9):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self).activated.connect(
                lambda i=i: self._select_nth(i)
            )

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

    # --- workspaces ---
    def _ensure_workspace(self, project: Project) -> TabPanel:
        key = project_store.identity(project.path)
        workspace = self.workspaces.get(key)
        if workspace is None:
            workspace = TabPanel(project)
            workspace.env_panel.saved.connect(self._on_env_saved)

            def on_protection(_state: dict[str, Any], w: TabPanel = workspace) -> None:
                self._on_protection_changed(w)

            def on_logo(logo: RepoLogo, p: str = project.path) -> None:
                self._on_logo_changed(p, logo)

            workspace.security_panel.changed.connect(on_protection)
            workspace.params_changed.connect(self._on_params_changed)
            workspace.machine_changed.connect(self.status_bar.refresh_tools)
            workspace.favorite_changed.connect(self._on_favorites_changed)
            workspace.sections_changed.connect(self._on_sections_changed)
            workspace.machine_saved.connect(self._on_machine_saved)
            workspace.repo_ready.connect(self.project_tabs.open_path)
            workspace.logo_changed.connect(on_logo)
            self.workspaces[key] = workspace
            self.workspace_stack.addWidget(workspace)
        return workspace

    @property
    def current_workspace(self) -> TabPanel | None:
        """Return the active repo's workspace, if any."""
        w = self.workspace_stack.currentWidget()
        return w if isinstance(w, TabPanel) else None

    # --- frameless window: move, maximize, resize ---
    @Slot()
    def _toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        for grip in self._grips:
            grip.place(self.width(), self.height())

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Maximized, the window hits the screen's edges.

        So no grip, no maximize glyph and no outline border.
        """
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
        """Paint the window's outline, since the system draws none.

        Without a system frame, Windows draws no silhouette for the
        window: without this, restored, it blends with a dark desktop.
        The border takes the active repo's color, set by
        `_apply_accent`, the same source as the title bar's background,
        and only while the window has focus, as Windows does with its
        own frame. Without focus it paints in `border`, the tinted
        separator the rest of the window uses, and does not disappear:
        so the content does not shift a pixel on activating. Maximized
        it is not needed.
        """
        window = theme.WINDOW.on(self.pal)
        if self.isMaximized():
            self.central_widget.setStyleSheet(
                f"QWidget#centralWidget {{ background: {window.bg}; }}"
            )
        else:
            color = window.focus if self.isActiveWindow() else window.border
            self.central_widget.setStyleSheet(
                f"QWidget#centralWidget {{ background: {window.bg}; border: 1px solid {color}; }}"
            )

    # --- the active repo's palette ---
    def _apply_palette(self, pal: Palette) -> None:
        """Apply the repo's palette to what lives outside its workspace.

        The title bar, the menu row and its open menus, the search, the
        status bar and the window's outline
        (`_apply_window_border`).
        """
        self.pal = pal
        self.title_bar.set_palette(pal)
        self.action_menu.set_palette(pal)
        self.action_search.set_palette(pal)
        self.status_bar.set_palette(pal)
        bar = theme.MENU_BAR.on(pal)
        self.menu_row.setStyleSheet(
            f"QWidget#menuRow {{ background: {bar.bg}; border-bottom: 1px solid {bar.border}; }}"
        )
        self._apply_window_border()

    # --- favorites ---
    @Slot(bool)
    def _on_only_favorites(self, value: bool, save: bool = True) -> None:
        """React to «Solo favoritos» of the Ver menu: it prunes menus.

        The search does not obey it: it always searches all actions.
        """
        if save:
            favorites.set_only_favorites(value)
        self.action_menu.set_only_favorites(value)
        self.action_menu.set_favorites(favorites.favorite_ids())

    @Slot()
    def _on_favorites_changed(self, *_args) -> None:
        """React to a favorite marked on any surface.

        The others catch up.

        Whoever marked it already saved.
        """
        ids = favorites.favorite_ids()
        self.action_menu.set_favorites(ids)
        self.action_search.set_favorites(ids)
        for workspace in self.workspaces.values():
            workspace.refresh_favorite_stars()

    # --- reactions ---
    @Slot(object)
    def _on_project_added(self, project: Project) -> None:
        self._ensure_workspace(project)
        self._on_project_selected(project)

    @Slot(object)
    def _on_project_retinted(self, project: Project) -> None:
        """React to a repo choosing another color from its tab's menu.

        Its workspace repaints even if not active: the neighbor cannot
        keep the old color's backgrounds waiting to be looked at.
        """
        workspace = self.workspaces.get(project_store.identity(project.path))
        pal = palettes.get(project.theme)
        if workspace is not None:
            workspace.set_palette(pal)
        if workspace is not None and workspace is self.current_workspace:
            self._apply_palette(pal)
            self._refresh_protection(workspace)

    @Slot(object)
    def _on_project_removed(self, project: Project) -> None:
        workspace = self.workspaces.pop(project_store.identity(project.path), None)
        if workspace is not None:
            self.workspace_stack.removeWidget(workspace)
            workspace.deleteLater()
        # What was chosen in its panels will not be looked at again this
        # session: what is pending goes down to the repo and the cache
        # is released.
        params_store.forget(project.path)
        if not self.project_tabs.tabs:
            self._show_empty_state()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        """Save what is pending and stop live tasks.

        Parameters write in half-second bursts
        (`services/params_store.py`): on closing, pending writes go
        down, or the last change is lost by checking a box and closing
        right away.

        It also saves the window's size, position and state, which
        `_restore_layout` reads on the next start, and stops live tasks
        of all repos: without this an SSH tunnel or a backend stayed
        running without Consola.
        """
        params_store.flush()
        settings = QSettings()
        settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(_STATE_KEY, self.saveState())
        for workspace in self.workspaces.values():
            workspace.shutdown()
        super().closeEvent(event)

    @Slot(object)
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
        """Show what THAT workspace's repo protects right now.

        It is for the status bar's indicator. It reads the panel
        (`security_panel.state()`), the same source the guard consults
        when running (`TabPanel._guard`): the indicator cannot say
        one thing and the guard apply another.
        """
        self.status_bar.set_protection(workspace.security_panel.state())

    def _on_protection_changed(self, workspace: TabPanel) -> None:
        if workspace is self.current_workspace:
            self._refresh_protection(workspace)

    @Slot()
    def _on_security_clicked(self) -> None:
        """Jump to the active repo's Security section.

        It is a click on the status bar's indicator (`ADR-0018` §4).
        """
        workspace = self.current_workspace
        if workspace is not None:
            workspace.reveal_security()

    @Slot(str)
    def _on_action_requested(self, capability_id: str) -> None:
        """Open or focus the action's tab; the click does not run it.

        Running is pressing Run in the parameters panel.
        """
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if capability and workspace is not None:
            workspace.open_tab(capability)

    @Slot(str)
    def _on_run_requested(self, capability_id: str) -> None:
        """Open the tab and run at once: the search's ▶ button."""
        capability = registry.get_capability(capability_id)
        workspace = self.current_workspace
        if capability and workspace is not None:
            workspace.quick_run(capability)

    def _refresh_applicable(self, project: Project) -> None:
        """Set which actions make sense in the repo just chosen.

        It recomputes on changing tab and not at startup: what decides
        is what is inside THAT repo
        (`services/catalog.py::applicable_ids`), and two repos on the
        bar need not match.
        """
        ids = applicable_ids(project.path)
        self.action_menu.set_applicable(ids)
        self.action_search.set_applicable(ids)

    def _refresh_readiness(self) -> None:
        """Recount which actions can run now on the active repo.

        The count lives in `services/readiness.py`; the ▶ of each search
        row shows it.

        It is requested, not done: the count walks the repo for all the
        actions and, among others, each keystroke of a text field fires
        it (`widgets/params_panel.py::_persist`,
        `widgets/env_panel.py`). Computed at once, a burst of typing
        queued a pass per key and letters appeared seconds later. The
        timer gathers the burst into one pass, as
        `services/params_store.py` does with writing to disk.
        """
        self._readiness_timer.start()

    @Slot()
    def _do_refresh_readiness(self) -> None:
        ready = readiness.ready_ids(self.project_tabs.active_project)
        self.action_search.set_ready(ready)

    @Slot(str, bool)
    def _on_section_toggled(self, section_id: str, visible: bool) -> None:
        """React to a section checked or unchecked in the Ver menu."""
        section_visibility.set_section_hidden(section_id, not visible)
        self._on_sections_changed()

    @Slot()
    def _on_sections_changed(self) -> None:
        """Section visibility is global.

        Chosen from one repo, it holds for all.
        """
        for workspace in self.workspaces.values():
            workspace.apply_section_visibility()

    @Slot()
    def _on_machine_saved(self) -> None:
        """Reread the machine keys in every workspace.

        They hold for every repo: each repo's machine section shows the
        new values, and its steps check against them.
        """
        for workspace in self.workspaces.values():
            workspace.reload_machine()
        self._refresh_readiness()

    @Slot()
    def _on_params_changed(self) -> None:
        """Recount: a step turned off or on changes the keys it claims.

        So the search's ▶ recomputes.
        """
        self._refresh_readiness()

    def _on_logo_changed(self, path: str, logo: RepoLogo) -> None:
        tab = self.project_tabs.find_tab(path)
        if tab is not None:
            tab.set_logo(logo)

    @Slot()
    def _on_env_saved(self, *_args) -> None:
        """React to saved configuration changing.

        There may be new actions ready to run without opening the tab,
        or some no longer ready.
        """
        self._refresh_readiness()
