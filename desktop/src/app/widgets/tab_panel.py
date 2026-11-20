"""The workspace of one repository, with its tabs and right column."""

from __future__ import annotations

import time
from typing import Any, override

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.dialogs.blocked_dialog import BlockedDialog
from app.dialogs.reminder_dialog import ReminderDialog
from app.services import (
    context,
    palettes,
    params_store,
    protection,
    repo_logo,
    section_visibility,
)
from app.services.catalog import forget_machine_cache
from app.services.palettes import Palette
from app.services.projects import Project
from app.services.registry import Capability, registry
from app.services.section_visibility import title as section_title
from app.services.task_runner import TaskRunner
from app.theme import Colors, Fonts
from app.widgets.accordion_section import AccordionSection
from app.widgets.command_info_panel import CommandInfoPanel
from app.widgets.console_view import ConsoleView
from app.widgets.env_panel import EnvPanel
from app.widgets.machine_panel import MachinePanel
from app.widgets.params_panel import ParamsPanel
from app.widgets.reorderable_bar import ReorderableBar
from app.widgets.reorderable_tab import ReorderableTab
from app.widgets.repo_logo_view import RepoLogoView
from app.widgets.section_resize_grip import SectionResizeGrip
from app.widgets.security_panel import SecurityPanel
from app.widgets.tab_view import TabView


class _SubTabButton(ReorderableTab):
    """A second-level tab: one run inside the active repo.

    A folder tab, like the repo tabs of the title bar: the active one
    paints in the console's background and opens into it, with no line
    below, so the console and the right column read as its content. Its
    name goes in white and bold. The others carry the repo's hue on the
    bar's step, with an outline and their name dimmed. No icon: the
    name already says which action it is.
    """

    close_requested = Signal()

    HEIGHT = 34

    def __init__(self, title: str, pal: Palette, parent: QWidget | None = None) -> None:
        """Build the tab."""
        super().__init__(parent)
        self.title = title
        self.pal = pal
        self.is_active = False
        self._hovered = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("_SubTabButton { background: transparent; }")
        self.setAccessibleName(title)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(7)

        self.title_label = QLabel(title)

        self.close_btn = QPushButton("×")
        self.close_btn.setAccessibleName(
            QCoreApplication.translate("_SubTabButton", "Cerrar pestaña")
        )
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

        layout.addWidget(self.title_label)
        layout.addWidget(self.close_btn)

        self._init_reorder()
        self._sync_text()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._sync_text()
        self.update()

    def set_active(self, active: bool) -> None:
        """Set whether it is the active tab."""
        self.is_active = active
        self._sync_text()
        self.update()
        self._announce_active()

    def _sync_text(self) -> None:
        f = QFont(self.title_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        f.setBold(self.is_active)
        self.title_label.setFont(f)
        # Active: in bold.
        color = (
            theme.RUN_TAB_ACTIVE.on(self.pal).fg
            if self.is_active
            else (Colors.TEXT_LABEL if self._hovered else theme.RUN_TAB.on(self.pal).fg)
        )
        self.title_label.setStyleSheet(f"background: transparent; color: {color};")

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self._sync_text()
        self.update()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._reorder_move(event)
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._reorder_release(event)
        super().mouseReleaseEvent(event)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the tab.

        It reaches the bar's bottom edge: the active one covers the
        bar's line with the console's background, and that gap in the
        line is what joins it to what is below.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 0.5, -1.5, 0)
        # Rounded on top and open below: it goes on into the content.
        path = QPainterPath()
        path.moveTo(r.left(), r.bottom() + 1)
        path.lineTo(r.left(), r.top() + 7)
        path.quadTo(r.left(), r.top(), r.left() + 7, r.top())
        path.lineTo(r.right() - 7, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + 7)
        path.lineTo(r.right(), r.bottom() + 1)

        if self.is_active:
            active = theme.RUN_TAB_ACTIVE.on(self.pal)
            p.fillPath(path, QColor(active.bg))
            edge = QColor(active.border)
        else:
            # Its fill stops one row short: the bar's line runs on
            # under it, and only the active one breaks it.
            tab = theme.RUN_TAB.on(self.pal)
            p.save()
            p.setClipRect(QRectF(self.rect()).adjusted(0, 0, 0, -1))
            p.fillPath(path, QColor(tab.bg))
            p.restore()
            edge = QColor(tab.border)
            edge.setAlpha(200 if (self._hovered or self.is_dragging) else 110)
        pen = QPen(edge)
        pen.setWidthF(1.0)
        if self.is_dragging:
            pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


def _config_tab() -> Capability:
    """Return the tab of «Configuración del repo».

    It is no catalog action: nothing runs it, so it is not registered;
    it only gives the tab its name, icon and tooltip.
    """
    return Capability(
        id="repo_config",
        name=QCoreApplication.translate("tab_panel", "Configuración del repo"),
        group="",
        kind="once",
        icon="⚙️",
        description=QCoreApplication.translate(
            "tab_panel",
            "Lo que hicieron los botones de Configuración del repo: guardar e importar.",
        ),
    )


class TabPanel(ReorderableBar):
    """The workspace of ONE repository.

    It holds the second level of tabs, that repo's runs, the console
    area and the views bar. Each repo has its own instance, so sub-tabs
    never mix between repos.
    """

    params_changed = Signal()  # some panel saved new parameters
    # a favorite was marked or unmarked from a footer's star
    favorite_changed = Signal()
    machine_changed = (
        Signal()
        # a machine task changed the environment (SDK installed, AVD
        # created)
    )
    # a section of the side column was shown or hidden a task left a new
    # repo on disk (clone): its folder, to open it as a tab
    sections_changed = Signal()
    # The machine keys were saved, from its section or from this repo's
    # form: `MainWindow` rereads them in every workspace.
    machine_saved = Signal()
    repo_ready = Signal(str)
    # config.env was reread: the `RepoLogo`, for the repo's tab
    logo_changed = Signal(object)

    # Floor of an accordion section's body when dragging it by hand.
    MIN_BODY = 48
    # The gap above the run tabs: it sets them apart from the menu row.
    SUB_BAR_TOP = 8

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Build the workspace and reopen its saved tabs."""
        super().__init__(parent)
        self.project = project
        self.pal = palettes.get(project.theme)
        self.logo = repo_logo.resolve(project.path)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # --- sub-tabs bar ---
        self.sub_bar = QWidget()
        self.sub_bar.setObjectName("subBar")
        self.sub_bar.setFixedHeight(_SubTabButton.HEIGHT + self.SUB_BAR_TOP)
        sub_bar_layout = QHBoxLayout(self.sub_bar)
        # No bottom margin: the tabs reach the bar's line
        # (`_SubTabButton`).
        sub_bar_layout.setContentsMargins(10, self.SUB_BAR_TOP, 10, 0)
        sub_bar_layout.setSpacing(2)

        self.tabs_layout = QHBoxLayout()
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(2)
        sub_bar_layout.addLayout(self.tabs_layout)

        self.empty_hint = QLabel(
            QCoreApplication.translate(
                "TabPanel", "sin acciones abiertas — elige una del panel izquierdo"
            )
        )
        self.empty_hint.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        sub_bar_layout.addWidget(self.empty_hint)
        sub_bar_layout.addStretch()

        # --- content area ---
        self.content_area = QStackedWidget()

        self.welcome_widget = self._build_welcome()
        self.content_area.addWidget(self.welcome_widget)

        # --- right column: an accordion of sections ---
        #
        # An accordion and not tabs because the three read together: a
        # `ParamsPanel` block may say config keys are missing, «VPS_IP»,
        # and that key is in the section below. With tabs, the message
        # would point at something out of view. See
        # `widgets/accordion_section.py`.
        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_params_placeholder())

        self.env_panel = EnvPanel(project)
        self.env_panel.values_changed.connect(self._on_env_changed)
        self.env_panel.reloaded.connect(self._on_env_reloaded)
        self.env_panel.saved.connect(self._refresh_logo)
        self.env_panel.saved.connect(self._refresh_previews)

        # Guards do not come from `config.env`: they live in
        # `.consola/params.json` and save on touching them, without
        # going through Settings's Save button
        # (`widgets/security_panel.py`).
        self.security_panel = SecurityPanel(project)
        self.security_panel.changed.connect(self._refresh_security_summary)

        # Top section: the open action's long description and its steps.
        # Its header always says «Acción»; folded, that is all that
        # shows.
        self.info_panel = CommandInfoPanel()
        self.info_section = AccordionSection(
            section_title("accion"), self.info_panel, expanded=False
        )
        # Folded at first: its header already sums up how many targets
        # are protected (`_refresh_security_summary`), so opening it is
        # only to touch the guards, not to find out.
        self.security_section = AccordionSection(
            section_title("seguridad"), self.security_panel, expanded=False
        )
        # Open at first and without folding by itself: it is the section
        # used on each run, and opening an action only to have to open
        # this too is one click too many. `_relayout_right` gives it its
        # full natural height.
        self.params_section = AccordionSection(
            section_title("parametros"), self.params_stack, expanded=True
        )
        self.config_section = AccordionSection(section_title("configuracion"), self.env_panel)
        # The machine keys: the only place they edit. Last, below the
        # repo's, and hidden until the Ver menu shows it.
        self.machine_panel = MachinePanel(self.pal, self.env_panel.label_width)
        self.machine_panel.saved.connect(self.machine_saved.emit)
        self.machine_section = AccordionSection(section_title("maquina"), self.machine_panel)
        # config.env's state goes in the section's label, not on a
        # separate line of its footer.
        self.env_panel.file_status_changed.connect(self._show_file_status)
        self.env_panel.notice.connect(self._on_env_notice)
        self._show_file_status()

        # A layout and not a `QSplitter`: folding is setting a height
        # cap on the section, and a splitter keeps its own sizes apart;
        # the two controls fought and the allotment only settled a turn
        # later.
        #
        # `_relayout_right` shares out, computing each one's cap; the
        # layout only obeys. Leaving it to stretch factors was not
        # enough: `params_stack` and `env_panel` ask for heights
        # unrelated to what the column can give, and negotiating among
        # them one section ended up with another's height.
        #
        # Body height (without header) chosen by hand by dragging the
        # bar below. `None` = follow `_relayout_right`'s automatic
        # share. It clears by itself on folding the section: reopening
        # autosizes again.
        self._manual: dict[AccordionSection, int | None] = {}
        self._grips: dict[AccordionSection, SectionResizeGrip] = {}
        self._all_sections = (
            self.info_section,
            self.security_section,
            self.params_section,
            self.config_section,
            self.machine_section,
        )
        # The key each one saves under in
        # `services/section_visibility.py`.
        self._section_ids = {
            self.info_section: "accion",
            self.security_section: "seguridad",
            self.params_section: "parametros",
            self.machine_section: "maquina",
            self.config_section: "configuracion",
        }

        self.right_column = QWidget()
        self._column = QVBoxLayout(self.right_column)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)
        for section in self._all_sections:
            section.header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

            def on_section_menu(pos: QPoint, h: QWidget = section.header) -> None:
                self._show_sections_menu(h.mapToGlobal(pos))

            section.header.customContextMenuRequested.connect(on_section_menu)
            # `_relayout_right` decides who stretches with
            # `setStretchFactor`: it has to be the last open section not
            # fixed by hand, which is not always Settings. Without that,
            # with Settings folded the excess fell in the final spring
            # and left a dead gap.
            self._column.addWidget(section, 0)
            section.toggled.connect(self._on_section_toggled)
            # The last one has no one to negotiate with below.
            if section is not self._all_sections[-1]:
                self._manual[section] = None
                grip = SectionResizeGrip()
                grip.pressed.connect(lambda s=section: self._begin_resize(s))

                def on_grip_drag(delta: int, s: AccordionSection = section) -> None:
                    self._resize_section(s, delta)

                grip.dragged.connect(on_grip_drag)
                grip.reset.connect(lambda s=section: self._resize_section(s, None))
                self._column.addWidget(grip)
                self._grips[section] = grip
        # With ALL folded nobody is left to stretch: this spring eats
        # the excess so the headers stack on top.
        self._column.addStretch(0)
        # Only now: the filter fires `_relayout_right`, which needs the
        # sections and bars built.
        self.right_column.installEventFilter(self)  # see `eventFilter`

        self.apply_section_visibility()

        # Fixed footer with Run and Dry run: outside the accordion, so
        # the button does not fold with the Parameters section or need
        # scrolling to. A stack with one footer per open action
        # (`ParamsPanel.footer`), plus a disabled placeholder for when
        # there is none.
        self.run_footer = QStackedWidget()
        self.run_footer.addWidget(self._build_footer_placeholder())

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.right_column, 1)
        right_layout.addWidget(self.run_footer)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.content_area)
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([880, 330])

        # `MainWindow` builds the single status bar across the whole
        # window, below the workspace (`windows/main_window.py`). This
        # panel only tells it, with `machine_changed`, when a machine
        # task touches the environment.

        self.root_layout.addWidget(self.sub_bar)
        self.root_layout.addWidget(self.splitter, 1)

        self.tabs: list[_SubTabButton] = []
        # A tab is a box with the console and, when the action publishes
        # an endpoint, a browser next to it (`widgets/tab_view.py`,
        # ADR-0008). `_consoles` exists because almost all this file
        # speaks to the console and not the box.
        self._views: dict[_SubTabButton, TabView] = {}
        self._consoles: dict[_SubTabButton, ConsoleView] = {}
        self._params: dict[_SubTabButton, ParamsPanel] = {}
        self._runners: set[TaskRunner] = (
            set()
        )  # live references: without this Qt collects them mid-thread
        # which tab has a running task
        self._busy: dict[_SubTabButton, TaskRunner] = {}
        # While saved tabs reopen they should not be saved step by step:
        # it saves once when the loop ends.
        self._restoring = False
        # The tab where «Configuración del repo» writes what its buttons
        # did, as an action's tab; None until one of them is pressed.
        self._config_tab: _SubTabButton | None = None

        # The whole workspace is born with the repo's color: the
        # accordion's headers and panels build in gray and their first
        # palette comes from here, the same a theme change applies.
        self.set_palette(self.pal)
        self._refresh_security_summary(self.security_panel.state())
        self._restore_tabs()
        QTimer.singleShot(0, self._relayout_right)

    def _restore_tabs(self) -> None:
        """Reopen the action tabs left open last time, in their order.

        From `services/params_store.py`. None runs anything: opening a
        tab is only that.
        """
        self._restoring = True
        try:
            for cap_id in params_store.load_tabs(self.project.path):
                capability = registry.get_capability(cap_id)
                if capability is not None:
                    self.open_tab(capability)
        finally:
            self._restoring = False
        # Rewrite the cleaned list: if the catalog lost a button, its
        # saved id does not drag on.
        self._persist_tabs()

    def _persist_tabs(self) -> None:
        """Note which tabs stay open, in order, for the next start.

        A tab without a panel, half closed, is skipped.
        """
        if self._restoring:
            return
        ids = [self._params[t].capability.id for t in self.tabs if t in self._params]
        params_store.save_tabs(self.project.path, ids)

    @override
    def tabs_reordered(self) -> None:
        self._persist_tabs()

    # --- building ------------------------------------------------
    @Slot()
    def _show_file_status(self) -> None:
        """Show config.env's state in its section's header."""
        env = self.env_panel
        self.config_section.set_summary(env.file_status, env.file_detail, env.file_warn)

    @Slot(str, str)
    def _on_env_notice(self, text: str, level: str) -> None:
        """Write what a settings button did in the settings tab.

        Saving and importing act like an action's button: they open
        their tab, or bring it forward, and leave the result there.
        """
        tab = self._config_tab
        if tab is None:
            tab = self._open_config_tab()
        else:
            self._activate(tab)
        self._consoles[tab].append_log(text, level)

    def _open_config_tab(self) -> _SubTabButton:
        """Open the tab of «Configuración del repo».

        It has a console and no parameters: showing it, the settings
        section shows the whole file, unfiltered. It is not reopened at
        start, since it only holds a log (`_persist_tabs` skips it).
        """
        config = _config_tab()
        tab = _SubTabButton(config.name, self.pal)
        tab.setToolTip(config.description)
        self.tabs_layout.addWidget(tab)
        self.tabs.append(tab)
        view = TabView(config, self.project, self.content_area)
        view.set_palette(self.pal)
        view.console.append_log(f"─── {config.name} ───", "info")
        self.content_area.addWidget(view)
        self._views[tab] = view
        self._consoles[tab] = view.console
        view.cleared.connect(lambda t=tab: self._on_cleared(t))
        tab.clicked.connect(lambda t=tab: self._activate(t))
        tab.close_requested.connect(lambda t=tab: self.close_tab(t))
        self._config_tab = tab
        self.empty_hint.setVisible(False)
        self._activate(tab)
        return tab

    def refresh_favorite_stars(self) -> None:
        """Catch the stars up when another surface marked an action."""
        for panel in self._params.values():
            panel.refresh_favorite()

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        self.welcome_logo = RepoLogoView(64, self.logo)

        self.welcome_title = QLabel(self.project.name.upper())
        self.welcome_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_XXL}px; font-weight: 300; "
            f"letter-spacing: 8px;"
        )
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            QCoreApplication.translate("TabPanel", "Selecciona una accion del panel izquierdo")
        )
        subtitle.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_BASE}px;"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.path_label = QLabel(self.project.path)
        self.path_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;"
        )
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(self.welcome_logo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(8)
        lay.addWidget(self.welcome_title, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        lay.addWidget(self.path_label, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _build_params_placeholder(self) -> QWidget:
        w = QWidget()
        self._params_placeholder = w
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setContentsMargins(20, 20, 20, 20)
        hint = QLabel(
            QCoreApplication.translate("TabPanel", "Los parámetros de la acción\naparecen aquí")
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        lay.addWidget(hint)
        return w

    def _build_footer_placeholder(self) -> QWidget:
        """Show Run visible but disabled, with no action open.

        So the bar does not change height on opening the first action.
        """
        foot = QWidget()
        self._footer_placeholder = foot
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)
        lay.addStretch()
        btn = QPushButton(QCoreApplication.translate("TabPanel", "Ejecutar"))
        btn.setFixedHeight(34)
        btn.setEnabled(False)
        self._footer_placeholder_btn = btn
        lay.addWidget(btn)
        return foot

    # --- reorder by dragging ---------------------------------------
    @override
    def _tab_layout(self) -> QHBoxLayout:
        return self.tabs_layout

    # --- API ---------------------------------------------------------
    def quick_run(self, capability: Capability) -> None:
        """Open or reuse the tab and run at once: the search's ▶.

        With that tab's parameters: on opening they are those saved for
        this button in this repo (`services/params_store`), and the
        defaults only if never touched.
        """
        console = self.open_tab(capability)
        panel = self.current_params()
        if panel is None:
            return
        if not panel.try_run():
            # The search thought it could run: say why not, in the same
            # console where the result would have appeared.
            for reason in panel.blockers():
                console.append_log(
                    QCoreApplication.translate("TabPanel", "no se puede correr: {0}").format(
                        reason
                    ),
                    "warn",
                )

    def open_tab(self, capability: Capability, axis_value: str = "") -> ConsoleView:
        """Open or focus an action's tab. **It runs nothing**.

        Running is pressing Run in the parameters panel.
        """
        return self._open(capability, axis_value)[1].console

    def _open(self, capability: Capability, axis_value: str = "") -> tuple[_SubTabButton, TabView]:
        """Do the same as `open_tab`, also returning the tab.

        A `fanout` axis's sharing into tabs (ADR-0010) needs to run a
        task *in* the tab just opened, and that takes the button, not
        only its console.
        """
        title = f"{capability.name} {axis_value}".strip()

        for tab in self.tabs:
            if tab.title != title:
                continue
            # A tab busy with something running live is not reused:
            # another opens. That allows two emulators at once without
            # waiting for the first to close.
            if capability.kind == "live" and tab in self._busy:
                title = self._next_title(title)
                break
            self._activate(tab)
            return tab, self._views[tab]

        tab = _SubTabButton(title, self.pal)
        tab.setToolTip(capability.description)
        self.tabs_layout.addWidget(tab)
        self.tabs.append(tab)

        view = TabView(capability, self.project, self.content_area)
        # The tab is born with the repo's color, not the grays: without
        # this it only had it on changing theme.
        view.set_palette(self.pal)
        console = view.console
        console.append_log(f"─── {capability.name} ───", "info")
        if capability.description:
            console.append_log(capability.description, "info")
        self.content_area.addWidget(view)
        self._views[tab] = view
        self._consoles[tab] = console
        view.cleared.connect(lambda t=tab: self._on_cleared(t))

        panel = ParamsPanel(capability, self.project, self.env_panel)
        panel.set_env(self.env_panel.values())

        def on_execute(payload: dict[str, Any], t: _SubTabButton = tab) -> None:
            self._run(t, payload)

        def on_stop(serial: str, t: _SubTabButton = tab) -> None:
            self._stop_live(t, serial)

        panel.execute_requested.connect(on_execute)
        panel.params_changed.connect(self.params_changed.emit)
        panel.params_changed.connect(lambda p=panel: self._refilter_env(p))
        panel.stop_requested.connect(on_stop)
        panel.clear_requested.connect(view.clear_console)
        panel.favorite_changed.connect(self.favorite_changed.emit)
        self.params_stack.addWidget(panel)
        self.run_footer.addWidget(panel.footer)
        self._params[tab] = panel

        tab.clicked.connect(lambda t=tab: self._activate(t))
        tab.close_requested.connect(lambda t=tab: self.close_tab(t))

        self.empty_hint.setVisible(False)
        self._activate(tab)
        self._persist_tabs()
        return tab, view

    def _retitle(self, tab: _SubTabButton, title: str) -> None:
        """Rename an open tab.

        `fanout`'s sharing uses it: the generic «SPA Vite» tab becomes
        «SPA Vite panel» when known which one started. One tab per live
        process, and the name says which (ADR-0010).
        """
        used = {t.title for t in self.tabs if t is not tab}
        if title in used:
            title = self._next_title(title)
        tab.title = title
        tab.title_label.setText(title)
        tab.setAccessibleName(title)
        tab._sync_text()

    def _next_title(self, title: str) -> str:
        """Return the first free title: `Emulador`, `Emulador 2`..."""
        used = {t.title for t in self.tabs}
        n = 2
        while f"{title} {n}" in used:
            n += 1
        return f"{title} {n}"

    def _stop_live(self, tab: _SubTabButton, serial: str) -> None:
        """Stop something left running: the status header's ✕.

        It runs the hidden `stop_emulator` capability like any other
        task, same console and same log, instead of touching adb from
        the interface.
        """
        capability = registry.get_capability("stop_emulator")
        console = self._consoles.get(tab)
        if capability is None or capability.func is None or console is None:
            return
        self._run_real(tab, console, capability, {"serial": serial}, track=False)

    def _on_cleared(self, tab: _SubTabButton) -> None:
        """Clear closes the tab's SSH tunnels.

        A tunnel belongs to its task, since the explorer or the backend
        connects through it, so the task stops and it closes the tunnel.
        What has no tunnel keeps running.
        """
        runner = self._busy.get(tab)
        if runner is not None and runner.has_tunnel:
            runner.cancel()

    def shutdown(self, timeout_ms: int = 5000) -> None:
        """Stop each task as closing its tab would: Consola is closing.

        It waits for their clean shutdowns to end (the tunnel, `adb emu
        kill`). What does not get to close in that time the Job Object
        kills (`services/process.py::bind_to_app`).
        """
        runners = list(self._runners)
        for runner in runners:
            runner.cancel()
        for tab in list(self._views):
            self._views[tab].shutdown()
        deadline = time.monotonic() + timeout_ms / 1000
        for runner in runners:
            runner.wait(max(0, int((deadline - time.monotonic()) * 1000)))

    def close_tab(self, tab: _SubTabButton) -> None:
        """Close a tab and stop what runs in it."""
        if tab not in self.tabs:
            return
        # Closing the tab stops what was running in it: for the
        # emulator, that is `adb emu kill` and not killing its process
        # (`services/tasks/emulators.py`). Signals cut first because the
        # console is destroyed in this very method and the task stays
        # alive a few moments more.
        runner = self._busy.pop(tab, None)
        if runner is not None:
            try:
                runner.logged.disconnect()
                runner.noted.disconnect()
                runner.finished_ok.disconnect()
                runner.ask_requested.disconnect()
                runner.serve_requested.disconnect()
            except (RuntimeError, TypeError):
                pass
            runner.cancel()
        idx = self.tabs.index(tab)
        was_active = tab.is_active

        self._consoles.pop(tab, None)
        view = self._views.pop(tab)
        view.shutdown()
        self.content_area.removeWidget(view)
        view.deleteLater()

        panel = self._params.pop(tab, None)
        if panel is not None:
            self.params_stack.removeWidget(panel)
            self.run_footer.removeWidget(panel.footer)
            panel.footer.deleteLater()
            panel.deleteLater()

        if tab is self._config_tab:
            self._config_tab = None
        self.tabs.remove(tab)
        self.tabs_layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()
        self._persist_tabs()

        if self.tabs:
            if was_active:
                self._activate(self.tabs[min(idx, len(self.tabs) - 1)])
        else:
            self.empty_hint.setVisible(True)
            self.content_area.setCurrentWidget(self.welcome_widget)
            self.params_stack.setCurrentIndex(0)
            self.run_footer.setCurrentIndex(0)
            self.env_panel.filter_for(None)
            self.info_panel.set_capability(None)
            self.info_section.set_expanded(False, announce=False)
            # Parameters stays open: it is its default state, even if it
            # only shows the placeholder now.
            self._relayout_right()

    def current_console(self) -> ConsoleView | None:
        """Return the active tab's console.

        It resolves by the tab and not the visible widget: with the
        browser on top, the visible widget is not the console, but the
        console is still that tab's and where it has to write.
        """
        for tab in self.tabs:
            if tab.is_active:
                return self._consoles.get(tab)
        return None

    def current_view(self) -> TabView | None:
        """Return the active tab's view."""
        w = self.content_area.currentWidget()
        return w if isinstance(w, TabView) else None

    def current_params(self) -> ParamsPanel | None:
        """Return the active tab's parameters panel."""
        w = self.params_stack.currentWidget()
        return w if isinstance(w, ParamsPanel) else None

    def press_run(self, *, dry_run: bool) -> None:
        """Press Run, or Simulacro, of the active tab, as a click would.

        A button that is disabled, or a tab with no Simulacro, does
        nothing: the same as clicking it.
        """
        panel = self.current_params()
        button = None if panel is None else (panel.dry_btn if dry_run else panel.run_btn)
        if button is not None:
            button.click()

    def cycle_tab(self, step: int) -> None:
        """Activate the next or previous action tab, wrapping around."""
        if not self.tabs:
            return
        current = next((i for i, t in enumerate(self.tabs) if t.is_active), 0)
        self._activate(self.tabs[(current + step) % len(self.tabs)])

    def set_palette(self, pal: Palette) -> None:
        """Repaint the whole workspace: the repo chose another color.

        The accent is not enough: the palette is each panel's
        backgrounds, and each keeps the style sheet dictated when built.
        """
        self.pal = pal
        self._restyle()
        for tab in self.tabs:
            tab.set_palette(pal)
        for panel in self._params.values():
            panel.set_palette(pal)
        for console in self._consoles.values():
            console.set_palette(pal)
        for view in self._views.values():
            view.set_palette(pal)
        self.env_panel.set_palette(pal)
        self.machine_panel.set_palette(pal)
        self.security_panel.set_palette(pal)
        self.info_panel.set_palette(pal)
        for section in self._all_sections:
            section.set_palette(pal)
        for grip in self._grips.values():
            grip.set_palette(pal)

    def _restyle(self) -> None:
        """Paint the backgrounds THIS panel sets.

        The runs sub-bar, the console's canvas and the two placeholders.
        Each panel repaints what is inside it.
        """
        bar = theme.RUN_BAR.on(self.pal)
        footer = theme.FOOTER.on(self.pal)
        run = theme.RUN_BUTTON_OFF.on(self.pal)
        self.sub_bar.setStyleSheet(f"""
            QWidget#subBar {{
                background: {bar.bg};
                border-bottom: 1px solid {bar.border};
            }}
        """)
        self.content_area.setStyleSheet(f"background: {theme.CANVAS.on(self.pal).bg};")
        self._params_placeholder.setStyleSheet(
            f"background: {theme.SECTION_BODY.on(self.pal).bg};"
        )
        self._footer_placeholder.setStyleSheet(
            f"background: {footer.bg}; border-top: 1px solid {footer.border};"
        )
        self._footer_placeholder_btn.setStyleSheet(f"""
            QPushButton {{
                background: {run.bg}; color: {run.fg};
                border: none; border-radius: 6px; padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
        """)

    def reveal_security(self) -> None:
        """Open this repo's Security section.

        The status bar's indicator calls it (`windows/main_window.py`).
        """
        self.security_section.set_expanded(True)

    # --- internal ---
    def _activate(self, tab: _SubTabButton) -> None:
        for t in self.tabs:
            t.set_active(t is tab)
        view = self._views.get(tab)
        if view is not None:
            self.content_area.setCurrentWidget(view)
            view.on_shown()
        panel = self._params.get(tab)
        if panel is not None:
            self.params_stack.setCurrentWidget(panel)
            self.run_footer.setCurrentWidget(panel.footer)
            # Showing the tab IS the request to see the list up to date:
            # queried axes (the SDK's AVDs, the VPS's services) reread
            # here and not with a reload button. It goes without
            # `refresh`, so what expires fast is asked again and the
            # SDK's large catalogs stay from the cache.
            panel.reload_catalogs()
            self.env_panel.filter_for(panel.relevant_keys())
            self.info_panel.set_capability(panel.capability)
            # Opening an action opens its parameters; if it was folded
            # by hand, it opens again: it is what the click went looking
            # for.
            self.params_section.set_expanded(True, announce=False)
            QTimer.singleShot(0, self._relayout_right)
        else:
            # The settings tab: no parameters and the whole file.
            self.params_stack.setCurrentIndex(0)
            self.run_footer.setCurrentIndex(0)
            self.env_panel.filter_for(None)
            self.info_panel.set_capability(None)
            QTimer.singleShot(0, self._relayout_right)

    def _refilter_env(self, panel: ParamsPanel) -> None:
        """Refilter the settings when a value is marked or unmarked.

        That can add or remove keys of the settings panel
        (`AxisDef.uses_env`), and it only matters on the tab being
        looked at.
        """
        if self.current_params() is panel:
            self.env_panel.filter_for(panel.relevant_keys())

    @override
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Share out again: the right column changed height.

        A resized window. Settings's height is «what is left».
        """
        if obj is self.right_column and event.type() == QEvent.Type.Resize:
            self._relayout_right()
        return super().eventFilter(obj, event)

    def _relayout_right(self, *_args) -> None:
        """Compute the height of each visible section.

        Folded, a section is only its header. Open, Security keeps what
        its checkboxes need and Parameters what its action asks for, up
        to the long half of the column, so an action with many options
        does not leave the rest by a thread; Settings gets what is left,
        since it is the only one with a long scroll. A section dragged
        by hand (`_manual`) wins over all that.

        It shares out BODIES, not whole sections: `height` starts at the
        header and what adds is the body. Mixing the two units made the
        first dragged section jump its header's height at once.
        """
        total = self.right_column.height()
        if total <= 0:
            return
        sections = self._sections
        self._sync_grips()
        # Drag bars also take height. Without subtracting them more
        # pixels were shared than there are, and the layout had to
        # squeeze some body below its minimum to fit.
        spent = sum(s.header_height() for s in sections) + sum(
            SectionResizeGrip.HEIGHT for s in sections[:-1] if self._grip_visible(s)
        )
        height = {s: s.header_height() for s in sections}
        free = max(0, total - spent)

        # The excess goes to the last open section, Settings or the
        # machine section below it when shown, but if folded Parameters
        # absorbs it, and so on upward.
        # Otherwise, with it folded the rest fell in the final spring
        # and the last header came off the bottom edge, leaving a dead
        # gap.
        absorbing = next((s for s in reversed(sections) if s.is_expanded()), None)
        # The last open section has no bar of its own, with no one below
        # to negotiate with, so a manual height of its own is from an
        # old state: it drops. Otherwise that old value fell short and
        # the gap returned.
        if absorbing in self._manual:
            self._manual[absorbing] = None

        for i, section in enumerate(sections[:-1]):
            if not section.is_expanded():
                continue
            # Keep the floor for each open section left below: an open
            # section showing no body reads as broken. That makes the
            # bar stop on dragging instead of erasing what is below.
            # Settings also has a roomier minimum, and the machine
            # section keeps all its rows: they are few, and Settings
            # above would otherwise take everything.
            reserve = sum(self._floor(s) for s in sections[i + 1 :] if s.is_expanded())
            if (
                self._manual[section] is None
                and section is self.params_section
                and self.config_section.is_expanded()
            ):
                reserve = max(reserve, 120)
            # But the reserve cannot eat this very section's floor.
            reserve = min(reserve, max(0, free - self.MIN_BODY))
            dar = max(0, min(self._section_wanted(section), free - reserve))
            height[section] += dar
            free -= dar

        if absorbing is not None:
            height[absorbing] += free

        for section, value in height.items():
            # A cap and not a fixed height: with all three pinned, the
            # column imposed their sum as minimum height and the window
            # could no longer shrink. The floor stays at the header, the
            # one thing that cannot be given up.
            section.setMaximumHeight(value)
            section.setMinimumHeight(section.header_height())
            # And also the hint, which is how the layout truly shares
            # out (see `AccordionSection.set_allotted`).
            section.set_allotted(value)
            # If a pixel were still left over from rounding, the
            # absorbing section keeps it and not the final spring.
            self._column.setStretchFactor(section, 1 if section is absorbing else 0)

    @Slot()
    def _on_section_toggled(self, *_args) -> None:
        # Folding a section discards its manual height: reopening
        # expects the size its content computes, not what it had three
        # clicks ago.
        for section in self._manual:
            if not section.is_expanded():
                self._manual[section] = None
        self._relayout_right()

    def _begin_resize(self, section: AccordionSection) -> None:
        """Start a drag from the height the section has ON SCREEN.

        Without this the drag kept counting from the saved value, which
        the share may have cut for lack of room: there was a dead zone
        where moving the mouse moved nothing until recovering the
        difference.
        """
        if section in self._manual:
            self._manual[section] = max(0, section.height() - section.header_height())

    def _resize_section(self, section: AccordionSection, delta: int | None) -> None:
        """Fix a section's body height, or release it with `delta=None`.

        The rest share what is left in `_relayout_right`.
        """
        if delta is None:
            self._manual[section] = None
        else:
            base = self._manual[section]
            if base is None:
                base = max(0, section.height() - section.header_height())
            # Floor: below it the body's scroll is smaller than its own
            # bar and cannot even scroll. To shrink further there is the
            # chevron.
            self._manual[section] = max(self.MIN_BODY, base + delta)
        self._relayout_right()

    @property
    def _sections(self) -> tuple[AccordionSection, ...]:
        """Return the sections the user left in view, in order.

        The height share and the drag bars only count these.
        """
        return tuple(s for s in self._all_sections if not s.isHidden())

    def reload_machine(self) -> None:
        """Reread the machine keys that another form saved."""
        self.machine_panel.reload()
        self.env_panel.reload_machine()

    def apply_section_visibility(self) -> None:
        """Show or hide the sections by the saved preference."""
        hidden = section_visibility.hidden_sections()
        for section in self._all_sections:
            section.setHidden(self._section_ids[section] in hidden)
        self._relayout_right()

    def _show_sections_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addSection(QCoreApplication.translate("TabPanel", "Secciones visibles"))
        for section in self._all_sections:
            sid = self._section_ids[section]
            item = menu.addAction(section.header.title.text().capitalize())
            item.setCheckable(True)
            item.setChecked(not section.isHidden())

            def on_toggled(visible: bool, s: str = sid) -> None:
                self._set_section_visible(s, visible)

            item.toggled.connect(on_toggled)
        menu.exec(global_pos)

    def _set_section_visible(self, section_id: str, visible: bool) -> None:
        section_visibility.set_section_hidden(section_id, not visible)
        self.sections_changed.emit()

    def _grip_visible(self, section: AccordionSection) -> bool:
        """Return whether there is something to negotiate.

        The section is open and some section open below can trade
        height.
        """
        sections = self._sections
        if section not in sections:
            return False
        i = sections.index(section)
        return section.is_expanded() and any(s.is_expanded() for s in sections[i + 1 :])

    def _sync_grips(self) -> None:
        for section, grip in self._grips.items():
            grip.setVisible(self._grip_visible(section))

    def _floor(self, section: AccordionSection) -> int:
        """Return the body height kept for an open section below."""
        if section is self.machine_section:
            return self.machine_panel.content_height()
        return self.MIN_BODY

    def _section_wanted(self, section: AccordionSection) -> int:
        """Return the body height an open section asks for."""
        manual = self._manual.get(section)
        if manual is not None:
            return manual
        if section is self.info_section:
            return self._info_wanted()
        if section is self.security_section:
            return self._security_wanted()
        if section is self.machine_section:
            return self.machine_panel.content_height()
        if section is self.config_section:
            return self.env_panel.content_height()
        # Parameters asks for its whole natural height: the idea is
        # seeing all the action's options without scrolling.
        # `_relayout_right`'s reserve keeps Settings from being left
        # with nothing, not a cap here.
        return self._params_wanted()

    def _params_wanted(self) -> int:
        panel = self.current_params()
        if panel is None:
            return self.params_stack.sizeHint().height()
        return max(160, panel.natural_height())

    def _security_wanted(self) -> int:
        # From the content, not the scroll wrapping it: a `QScrollArea`
        # has no height of its own and would answer a generic
        # `sizeHint`.
        return self.security_panel.content_height()

    def _info_wanted(self) -> int:
        return self.info_panel.content_height() + 28

    @Slot(dict)
    def _refresh_security_summary(self, state: dict[str, Any]) -> None:
        """Show how many targets are protected in the section's header.

        So closing it costs no information: folded it still says the one
        datum it opens for.
        """
        protected = len(protection.repo_protections(state))
        total = len(protection.TARGETS)
        self.security_section.set_summary(
            QCoreApplication.translate("TabPanel", "{0} de {1} protegidos").format(
                protected, total
            )
            if protected
            else QCoreApplication.translate("TabPanel", "sin seguros")
        )

    @Slot(dict)
    def _on_env_changed(self, values: dict[str, Any]) -> None:
        for panel in self._params.values():
            panel.set_env(values)

    @Slot()
    def _on_env_reloaded(self) -> None:
        """Reload the parameters too when reloading `config.env`.

        It is no courtesy: queried axes come from asking the repo's VPS,
        and `config.env` says which VPS. Rereading the file without
        rereading the axes would leave the list answered by the previous
        machine. It is forced, skipping the cache, because this is the
        «I want the state right now» path.
        """
        for panel in self._params.values():
            panel.refresh_machine()
        self._refresh_logo()

    @Slot()
    def _refresh_previews(self, *_args) -> None:
        """Ask again what each open action will do.

        A preview reads the saved `config.env`, so saving can change it:
        `DB_EXTENSIONS` or `TURN` change the packages.
        """
        for panel in self._params.values():
            if panel.capability.preview:
                panel.reload_catalogs()

    @Slot()
    def _refresh_logo(self, *_args) -> None:
        """Reread the logo: `BRAND_ICON` may have changed."""
        self.logo = repo_logo.resolve(self.project.path)
        self.welcome_logo.set_logo(self.logo)
        self.logo_changed.emit(self.logo)

    def _run(self, tab: _SubTabButton, payload: dict[str, Any]) -> None:
        """Run for real what has a body: the single point of «Ejecutar».

        What has `func` runs; what has none stays simulated, so the rail
        and panel work the same while writing (ADR-0002). The capability
        itself builds the kwargs from its declaration (ADR-0003).
        """
        console = self._consoles.get(tab)
        if console is None:
            return

        capability = registry.get_capability(payload["capability_id"])
        if capability is None:
            self._run_stub(console, payload)
            return

        # The guard goes here and not in the parameters panel because
        # this is the only point BOTH ways of running pass through: the
        # Run button and the rail's run button (`quick_run`). Placing it
        # in the panel would leave the second path with no net.
        self._guard(tab, capability, payload, console)

    def _dispatch(
        self, tab: _SubTabButton, capability: Capability, payload: dict[str, Any]
    ) -> None:
        """Run what the guard let pass, by the capability's shape."""
        console = self._consoles[tab]
        # A concurrent composite runs nothing itself: it shares out its
        # steps, which are capabilities, one per tab (ADR-0011).
        if capability.concurrent:
            self._run_concurrent(tab, capability, payload)
            return

        if capability.func is None:
            self._run_stub(console, payload)
            return

        values = self._fanout_values(capability, payload)
        if values:
            self._run_fanout(tab, capability, payload, values)
        else:
            self._run_real(tab, console, capability, capability.kwargs_from(payload))

    # --- guard by target type ---
    def _guard(
        self,
        tab: _SubTabButton,
        capability: Capability,
        payload: dict[str, Any],
        console: ConsoleView,
    ) -> None:
        """Let pass, warn or block, by `services/protection.decide`.

        What decides is not «it is destructive» but «what it breaks,
        with THESE parameters, and whether that is protected in THIS
        repo»: a dry run of `clean_artifacts` asks nothing,
        `teardown_db` against `local` does not decide the same as
        against `remote`, and a protected target does not open a door to
        skip the guard: it closes it.

        The notices open with `open()`, so the run goes on from the
        reminder's `accepted`.
        """
        decision, targets = protection.decide(self.security_panel.state(), capability.id, payload)
        if decision == protection.Decision.ALLOW:
            self._dispatch(tab, capability, payload)
            return

        if decision == protection.Decision.BLOCK:
            blocked = BlockedDialog(self.project, capability.name, targets, self)
            blocked.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            blocked.open()
            which = ", ".join(QCoreApplication.translate("protection", t.label) for t in targets)
            console.append_log(
                QCoreApplication.translate(
                    "TabPanel",
                    "Bloqueado: {0} toca {1} y este repo lo tiene protegido. El seguro se "
                    "quita en Configuracion, seccion Seguridad.",
                ).format(capability.name, which),
                "error",
            )
            return

        reminder = ReminderDialog(self.project, capability.name, targets, self)
        reminder.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        def on_accepted() -> None:
            self._dispatch(tab, capability, payload)

        def on_rejected() -> None:
            console.append_log(
                QCoreApplication.translate(
                    "TabPanel", "Cancelado: {0} no llego a correr sobre {1}."
                ).format(capability.name, self.project.name),
                "warn",
            )

        reminder.accepted.connect(on_accepted)
        reminder.rejected.connect(on_rejected)
        reminder.open()

    # --- sharing into tabs ---
    def _fanout_values(self, capability: Capability, payload: dict[str, Any]) -> list[str]:
        """Return the values of the axis shared into tabs, if any.

        Only for what runs live: a `many` axis of a capability that ends
        (`build_vite`) loops inside its own console, because seeing the
        builds in a row is right. Three dev servers in one console are
        not (ADR-0010).
        """
        if capability.kind != "live" or not capability.fanout:
            return []
        return list((payload.get("variants") or {}).get(capability.fanout) or [])

    def _run_fanout(
        self,
        tab: _SubTabButton,
        capability: Capability,
        payload: dict[str, Any],
        values: list[str],
    ) -> None:
        """Run one tab per checked value, each with its live process.

        The first stays in the tab Run was pressed from, only changing
        name: so the normal case, a repo with one SPA, looks the same,
        without an extra tab.
        """

        def _payload_for(value: str) -> dict[str, Any]:
            variants = dict(payload.get("variants") or {})
            variants[capability.fanout] = [value]
            return {**payload, "variants": variants}

        first, rest = values[0], values[1:]
        self._retitle(tab, f"{capability.name} {first}")
        if rest:
            self._consoles[tab].append_log(
                QCoreApplication.translate(
                    "TabPanel", "{0} apps marcadas: una pestaña por cada una ({1})."
                ).format(len(values), ", ".join(values)),
                "info",
            )
        self._run_real(
            tab, self._consoles[tab], capability, capability.kwargs_from(_payload_for(first))
        )

        for value in rest:
            other, view = self._open(capability, value)
            self._run_real(
                other, view.console, capability, capability.kwargs_from(_payload_for(value))
            )
        self._activate(tab)

    def _run_concurrent(
        self, tab: _SubTabButton, capability: Capability, payload: dict[str, Any]
    ) -> None:
        """Run a concurrent composite: launch each step in its own tab.

        There is no `func` to call. Its steps are capabilities with
        their own button, and each starts with the parameters already
        saved for this repo: exactly what the rail's run button does, so
        `quick_run` is reused instead of rebuilding a payload by hand.

        The list's order is the dispatch's, and all that matters is that
        the backend goes first: the others wait for its endpoint from
        inside (`launchers.backend_url(wait=...)`), not by an interface
        `sleep`.
        """
        console = self._consoles[tab]
        console.append_log(
            QCoreApplication.translate(
                "TabPanel", "{0}: cada paso va a su propia pestaña."
            ).format(capability.name),
            "info",
        )
        launched = []
        for step_id in payload.get("steps") or []:
            sub_cap = registry.get_capability(step_id)
            if sub_cap is None:
                console.append_log(
                    QCoreApplication.translate("TabPanel", "paso desconocido: {0}").format(
                        step_id
                    ),
                    "warn",
                )
                continue
            console.append_log(f"→ {sub_cap.name}", "info")
            self.quick_run(sub_cap)
            launched.append(sub_cap.name)
        self._activate(tab)
        if launched:
            console.append_log(
                QCoreApplication.translate("TabPanel", "Lanzados: {0}.").format(
                    ", ".join(launched)
                ),
                "ok",
            )
        else:
            console.append_log(
                QCoreApplication.translate("TabPanel", "Ningún paso marcado."), "warn"
            )

    def _run_real(
        self,
        tab: _SubTabButton,
        console: ConsoleView,
        capability: Capability,
        kwargs: dict[str, Any],
        track: bool = True,
    ) -> None:
        """Run a capability for real.

        `track=False` is for what runs *inside* a foreign tab: the ✕
        stopping an orphan emulator must not pass as the tab's owner, or
        closing it would stop the shutdown and not the emulator that tab
        launched.
        """
        console.append_log("─" * 46, "info")
        panel = self._params.get(tab)
        if panel is not None:
            panel.run_btn.setEnabled(False)
            if panel.dry_btn is not None:
                panel.dry_btn.setEnabled(False)

        assert capability.func is not None
        runner = TaskRunner(capability.id, self.project, capability.func, kwargs)
        if track:
            self._busy[tab] = runner
        runner.logged.connect(console.append_log)
        # What the task publishes with `ctx.serve()`: the bar with the
        # URL and, if the capability declares `view='web'`, the browser
        # of this same tab.
        view = self._views.get(tab)
        if view is not None:
            runner.serve_requested.connect(view.set_endpoint)

        # The log book does not exist yet (`services/store.py`,
        # docs/arquitectura/30_riesgos_y_pendientes.md): until it does,
        # a note is not lost but left marked in the console.
        def on_note(entry: str) -> None:
            console.append_log(f"✱ {entry}", "ok")

        def on_ask(question: str, shape: str, danger: bool, expect: str) -> None:
            self._answer_task(runner, question, shape, danger, expect)

        runner.noted.connect(on_note)
        runner.ask_requested.connect(on_ask)

        def _on_done(ok: bool) -> None:
            console.append_log(
                QCoreApplication.translate("TabPanel", "Hecho")
                if ok
                else QCoreApplication.translate("TabPanel", "Terminó con errores"),
                "ok" if ok else "error",
            )
            # The process died: the URL stops being offered as alive and
            # the tab returns to the console, where the reason is.
            if view is not None:
                view.endpoint_down()
            self._runners.discard(runner)
            if self._busy.get(tab) is runner:
                self._busy.pop(tab, None)
            if panel is not None:
                panel.refresh_run_state()
            # What the task delivered is a repo
            # (`Capability.opens_repo`): the window opens it as a tab.
            # The capability declares that its result is a repo folder
            # and the interface does the rest: no button id is written
            # here.
            if ok and capability.opens_repo and runner.result:
                self.repo_ready.emit(str(runner.result))
            if capability.is_machine_wide:
                # Installing an image, creating an AVD or stopping an
                # emulator changes exactly what this group's panels
                # list. What is cached is forgotten and they reread:
                # otherwise a fresh AVD does not appear until reopening
                # the tab.
                forget_machine_cache()
                for other in self._params.values():
                    if other.capability.group == capability.group:
                        other.refresh_machine()
                # Installing an SDK changes the machine's environment:
                # the bar's indicators have to reflect it now, not on
                # the next start.
                self.machine_changed.emit()

        runner.finished_ok.connect(_on_done)
        # live reference while the thread runs
        self._runners.add(runner)
        runner.start()

    def _answer_task(
        self, runner: TaskRunner, question: str, shape: str, danger: bool, expect: str
    ) -> None:
        """Answer a task's question, on the interface thread.

        Four dialogs, chosen by what the task expects back
        (`services/context.py::ASK_*`) and not by how the question
        looks:

        - `expect`: an exact text has to be typed (deleting a database,
          overwriting a folder). A text field: the friction is the
          point.
        - `ASK_SECRET`: a datum that should not show while typing.
        - `ASK_TEXT`: a datum the task cannot deduce and that belongs
          neither to this repo nor this machine, so it has nowhere to be
          saved: a new SPA's folder name differs each time.
        - the rest: yes/no, with the dangerous button not the default,
          so one Enter too many discards nothing.

        It always calls `provide_answer`, also when the dialog closes
        with the X: without that the task stays waiting for an answer
        that never comes. An empty answer is a «no» for `confirm`. The
        dialogs open with `open()`, and the answer goes from their
        `finished`.
        """
        if expect or shape in (context.ASK_SECRET, context.ASK_TEXT):
            dialog = QInputDialog(self)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.setWindowTitle(
                QCoreApplication.translate("TabPanel", "Confirmar")
                if expect
                else QCoreApplication.translate("TabPanel", "Dato requerido")
            )
            dialog.setLabelText(question)
            if not expect and shape == context.ASK_SECRET:
                dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
            # Cancelling is not answering empty: for some questions
            # empty means «use the derived value»
            # (`services/context.py::ASK_CANCELLED`).
            cancelled = "" if expect else context.ASK_CANCELLED

            def on_text(result: int) -> None:
                accepted = result == QDialog.DialogCode.Accepted.value
                runner.provide_answer(dialog.textValue() if accepted else cancelled)

            dialog.finished.connect(on_text)
            dialog.open()
            return

        box = QMessageBox(self)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
        box.setWindowTitle(
            QCoreApplication.translate("TabPanel", "Confirmar")
            if danger
            else QCoreApplication.translate("TabPanel", "Pregunta")
        )
        box.setText(question)
        yes = box.addButton(
            QCoreApplication.translate("TabPanel", "Sí"), QMessageBox.ButtonRole.YesRole
        )
        no = box.addButton(
            QCoreApplication.translate("TabPanel", "No"), QMessageBox.ButtonRole.NoRole
        )
        box.setDefaultButton(no)

        def on_button(_result: int) -> None:
            # Only «Sí» is a yes: closing it any other way is a no.
            runner.provide_answer("si" if box.clickedButton() is yes else "no")

        box.finished.connect(on_button)
        box.open()

    def _run_stub(self, console: ConsoleView, payload: dict[str, Any]) -> None:
        """Simulate the run: report exactly what would run.

        A stub, ADR-0002.
        """
        console.append_log("─" * 46, "info")

        variants = {k: v for k, v in payload["variants"].items() if v}
        for name, values in variants.items():
            console.append_log(f"{name}: {', '.join(values)}", "info")
        for name, value in payload["options"].items():
            console.append_log(f"{name}: {value}", "info")

        combos = 1
        for values in variants.values():
            combos *= max(1, len(values))
        steps = payload["steps"]
        console.append_log(
            QCoreApplication.translate("TabPanel", "{0} paso(s) × {1} variante(s)").format(
                len(steps), combos
            ),
            "info",
        )

        for step_id in steps:
            for _ in range(combos):
                pass
            console.append_log(
                QCoreApplication.translate(
                    "TabPanel", "paso «{0}» — no implementado (stub)"
                ).format(step_id),
                "warn",
            )

        if payload["missing_env"]:
            console.append_log(
                QCoreApplication.translate("TabPanel", "faltan claves: {0}").format(
                    ", ".join(payload["missing_env"])
                ),
                "error",
            )
        else:
            console.append_log(
                QCoreApplication.translate("TabPanel", "Simulación completada"), "ok"
            )
