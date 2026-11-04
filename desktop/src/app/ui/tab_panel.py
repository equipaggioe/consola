"""The workspace of one repository, with its tabs and right column."""

from __future__ import annotations

import time
from typing import Any, override

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, Signal
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
    QFrame,
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

from app.core import context, protection, sysinfo, toolstatus
from app.core.catalog import forget_machine_cache
from app.core.projects import Project
from app.core.registry import Capability, registry
from app.core.toolstatus import Tool
from app.theme import Colors, Fonts
from app.ui import favorites, palettes, params_store, repo_logo, section_visibility
from app.ui.command_info_panel import CommandInfoPanel
from app.ui.console_view import ConsoleView
from app.ui.env_panel import EnvPanel
from app.ui.guard_dialog import BlockedDialog, ReminderDialog
from app.ui.palettes import Palette
from app.ui.params_panel import ParamsPanel
from app.ui.security_panel import SecurityPanel
from app.ui.tab_view import TabView
from app.ui.task_runner import TaskRunner
from app.ui.widgets import (
    AccordionSection,
    FavoriteStar,
    ReorderableBar,
    ReorderableTab,
    SectionResizeGrip,
)
from app.ui.widgets.led import LedIndicator


class SubTabButton(ReorderableTab):
    """A second-level tab: one run inside the active repo.

    Visually subordinate to the top level: lower, smaller type and
    underlined, not with a top bar, in the repo's color.
    """

    clicked = Signal()
    close_requested = Signal()

    HEIGHT = 34

    def __init__(self, title: str, icon: str, pal: Palette, parent: QWidget | None = None) -> None:
        """Build the tab."""
        super().__init__(parent)
        self.title = title
        self.pal = pal
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

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self.update()

    def set_active(self, active: bool) -> None:
        """Set whether it is the active tab."""
        self.is_active = active
        self._sync_text()
        self.update()

    def _sync_text(self) -> None:
        f = QFont(self.title_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        f.setBold(self.is_active)
        self.title_label.setFont(f)
        color = (
            Colors.TEXT
            if self.is_active
            else (Colors.TEXT_DIM if self._hovered else Colors.TEXT_MUTED)
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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        accent = QColor(self.pal.accent)

        if self.is_active:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(accent.red(), accent.green(), accent.blue(), 34))
            underline = QPainterPath()
            underline.addRoundedRect(
                QRectF(r.left() + 8, r.bottom() - 3, r.width() - 16, 2.5), 1.2, 1.2
            )
            p.fillPath(underline, accent)
        elif self._hovered or self.is_dragging:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(self.pal.surface_hover))

        if self.is_dragging:
            pen = QPen(accent)
            pen.setWidthF(1.2)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(2.5, 4.5, -2.5, -3.5), 7, 7)
        p.end()


class PadlockChip(QLabel):
    """A protection target on the status bar.

    Its short name with a padlock, closed (protected) or open
    (unprotected). A click jumps to the Security section.
    """

    clicked = Signal()

    def __init__(
        self, chip: str, label: str, protected: bool, pal: Palette, parent: QWidget | None = None
    ) -> None:
        """Build the chip."""
        super().__init__(f"{'🔒' if protected else '🔓'} {chip}", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Closed = safe (the repo's color); open = exposed to a
        # destructive action with no net, and that is red in every repo.
        color = pal.accent if protected else Colors.ERROR
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )
        self.setToolTip(
            f"{label}: {'protegido' if protected else 'sin proteger'}. "
            "Clic para administrar en Configuración → Seguridad."
        )

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class WorkspaceStatusBar(QWidget):
    """The workspace's bottom bar: active repo, services and state."""

    # click on the active repo's guards indicator
    security_clicked = Signal()

    def __init__(self, pal: Palette, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        self.pal = pal
        # What the padlocks last showed: on changing color they have to
        # be repainted, and the repo holds the state, not the bar.
        self._protection: dict[str, Any] = {}
        self.setFixedHeight(34)
        # Without this a QWidget subclass paints neither background nor
        # border from its style sheet: the top line separating it from
        # the content did not show (same reason as in
        # `ui/widgets/accordion.py`).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(10)
        layout.addLayout(self.services_layout)

        layout.addStretch()

        # From here rightward, each section is separated from the
        # previous by a thin line: environment, guards and state read as
        # distinct blocks.
        self._sep_tools = self._divider()
        layout.addWidget(self._sep_tools)

        # Environment state: it checks itself, not with a button. It
        # goes before the clock because it is the machine's information,
        # not this run's.
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setSpacing(10)
        layout.addLayout(self.tools_layout)
        self._tools: dict[str, tuple[LedIndicator, QLabel]] = {}
        self.refresh_tools()

        # Available RAM: unlike the SDKs, it changes all the time and
        # not only after an install, so it has its own timer.
        self.ram_label = QLabel()
        self.ram_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        self.tools_layout.addWidget(self.ram_label)
        self._ram_timer = QTimer(self)
        self._ram_timer.timeout.connect(self.refresh_ram)
        self._ram_timer.start(5000)
        self.refresh_ram()

        self._sep_security = self._divider()
        layout.addWidget(self._sep_security)

        # The active repo's protection targets (`core/protection.py`),
        # each with its open or closed padlock, always in view whichever
        # action is open above (`ADR-0018` §4). A click on any jumps to
        # the Security section.
        self.security_box = QWidget()
        self.security_box.setStyleSheet("background: transparent;")
        self._security_row = QHBoxLayout(self.security_box)
        self._security_row.setContentsMargins(0, 0, 0, 0)
        self._security_row.setSpacing(9)
        layout.addWidget(self.security_box)

        self._sep_status = self._divider()
        layout.addWidget(self._sep_status)

        self.status_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.status_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        layout.addWidget(self.status_label)

        self._restyle()

    def _divider(self) -> QFrame:
        """Return a thin vertical line between two bar sections."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {self.pal.border}; border: none;")
        line.setFixedHeight(16)
        return line

    def refresh_tools(self) -> None:
        """Look at the disk again and repaint the environment's LEDs.

        It is called on building the bar and after each machine action,
        such as installing an SDK: since the install leaves its
        variables in the process's `os.environ`, the LED turns green
        without restarting anything.
        """
        for tool in toolstatus.detect():
            if tool.key not in self._tools:
                self._tools[tool.key] = self._build_tool(tool)
            led, label = self._tools[tool.key]
            # 'on', not 'green': the pulsing green says «this is
            # running», and an installed tool is a still fact.
            led.set_state("on" if tool.found else "off")
            tip = f"{tool.label}: {tool.detail}"
            led.setToolTip(tip)
            label.setToolTip(tip)
            label.setStyleSheet(
                f"color: {Colors.TEXT_DIM if tool.found else Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )

    def refresh_ram(self) -> None:
        """Show available and total RAM, rounded to the GB.

        Enough to see at a glance whether to close something before
        launching a heavy build.
        """
        ram = sysinfo.available_ram()
        if ram is None:
            self.ram_label.setVisible(False)
            return
        available, total = ram
        self.ram_label.setVisible(True)
        self.ram_label.setText(f"RAM {available:.1f}/{total:.1f} GB")
        threshold = total * 0.15
        color = Colors.TEXT_DIM if available > threshold else Colors.WARNING
        self.ram_label.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )

    def _build_tool(self, tool: Tool) -> tuple[LedIndicator, QLabel]:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=8)
        label = QLabel(tool.label)
        clayout.addWidget(led)
        clayout.addWidget(label)

        self.tools_layout.addWidget(container)
        return led, label

    def add_service(self, name: str) -> None:
        """Add a service indicator."""
        container = QWidget()
        container.setObjectName(f"service_{name}")
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=9)
        led.set_state("green")
        clayout.addWidget(led)

        label = QLabel(name)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        clayout.addWidget(label)

        self.services_layout.addWidget(container)

    def set_status(self, text: str) -> None:
        """Set the state's text."""
        self.status_label.setText(text)

    def clear(self) -> None:
        """Show nothing about guards or tasks: no repository is open.

        See `ui/main_window.py::_show_empty_state`.
        """
        self.security_box.setVisible(False)
        # With no guards to show, the divider preceding them is not
        # needed.
        self._sep_security.setVisible(False)
        self.set_status("")

    def set_protection(self, state: dict[str, Any]) -> None:
        """Refresh the padlocks with the state of EACH target.

        From `core/protection.TARGETS`, not only the protected ones: a
        target with no guard is also a datum, and its open padlock shows
        at a glance. `state` is `{target_id: bool}`
        (`ui/security_panel.py`). It is called on changing repo and each
        time a switch is touched.
        """
        self._protection = dict(state)
        while self._security_row.count():
            item = self._security_row.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()

        self.security_box.setVisible(True)
        self._sep_security.setVisible(True)
        for target in protection.TARGETS:
            protected = protection.is_protected(state, target)
            chip = PadlockChip(target.chip, target.label, protected, self.pal)
            chip.clicked.connect(self.security_clicked.emit)
            self._security_row.addWidget(chip)
        self._restyle()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()
        # Padlocks paint in the accent when closed, so they have to be
        # redone; with an empty bar there are none to redo.
        if self.security_box.isVisible():
            self.set_protection(self._protection)

    def _restyle(self) -> None:
        self.setStyleSheet(f"""
            WorkspaceStatusBar {{
                background: {self.pal.surface};
                border-top: 1px solid {self.pal.border};
            }}
        """)
        for line in (self._sep_tools, self._sep_security, self._sep_status):
            line.setStyleSheet(f"background: {self.pal.border}; border: none;")


class TabPanel(ReorderableBar):
    """The workspace of ONE repository.

    It holds the second level of tabs, that repo's runs, the console
    area and the views bar. Each repo has its own instance, so sub-tabs
    never mix between repos.
    """

    params_changed = Signal()  # some panel saved new parameters
    machine_changed = (
        Signal()
        # a machine task changed the environment (SDK installed, AVD
        # created)
    )
    # a favorite was marked or unmarked from the star
    favorite_changed = Signal()
    # a section of the side column was shown or hidden a task left a new
    # repo on disk (clone): its folder, to open it as a tab
    sections_changed = Signal()
    repo_ready = Signal(str)
    # config.env was reread: the `RepoLogo`, for the repo's tab
    logo_changed = Signal(object)

    # Floor of an accordion section's body when dragging it by hand.
    MIN_BODY = 48

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
        self.sub_bar.setFixedHeight(SubTabButton.HEIGHT + 4)
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

        # --- content area ---
        self.content_area = QStackedWidget()

        self.welcome_widget = self._build_welcome()
        self.content_area.addWidget(self.welcome_widget)

        # --- right column: a single header and an accordion of sections
        # ---
        #
        # An accordion and not tabs because the three read together: a
        # `ParamsPanel` block may say config keys are missing, «VPS_IP»,
        # and that key is in the section below. With tabs, the message
        # would point at something out of view. See
        # `ui/widgets/accordion.py`.
        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_params_placeholder())

        self.env_panel = EnvPanel(project)
        self.env_panel.values_changed.connect(self._on_env_changed)
        self.env_panel.reloaded.connect(self._on_env_reloaded)
        self.env_panel.saved.connect(self._refresh_logo)

        # Guards do not come from `config.env`: they live in
        # `.consola/params.json` and save on touching them, without
        # going through Settings's Save button (`ui/security_panel.py`).
        self.security_panel = SecurityPanel(project)
        self.security_panel.changed.connect(self._refresh_security_summary)

        # Top section: the open action's long description and its steps.
        # Its header always says «Acción»; folded, that is all that
        # shows.
        self.info_panel = CommandInfoPanel()
        self.info_section = AccordionSection("Acción", self.info_panel, expanded=False)
        # Folded at first: its header already sums up how many targets
        # are protected (`_refresh_security_summary`), so opening it is
        # only to touch the guards, not to find out.
        self.security_section = AccordionSection("Seguridad", self.security_panel, expanded=False)
        # Open at first and without folding by itself: it is the section
        # used on each run, and opening an action only to have to open
        # this too is one click too many. `_relayout_right` gives it its
        # full natural height.
        self.params_section = AccordionSection("Parámetros", self.params_stack, expanded=True)
        self.config_section = AccordionSection("Configuración del repo", self.env_panel)
        # config.env's state goes in the section's label, not on a
        # separate line of its footer.
        self.env_panel.file_status_changed.connect(self.config_section.set_summary)
        self.config_section.set_summary(self.env_panel.file_status)

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
        )
        # The key each one saves under in `ui/section_visibility.py`.
        self._section_ids = {
            self.info_section: "accion",
            self.security_section: "seguridad",
            self.params_section: "parametros",
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
            # Settings is last: it has no one to negotiate with below.
            if section is not self.config_section:
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

        # action the header shows, for the star
        self._header_cap_id = ""
        self.right_header = self._build_right_header()
        # The header never hides: with all sections hidden there is
        # still somewhere to right-click to bring them back.
        self.right_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def on_header_menu(pos: QPoint) -> None:
            self._show_sections_menu(self.right_header.mapToGlobal(pos))

        self.right_header.customContextMenuRequested.connect(on_header_menu)
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
        right_layout.addWidget(self.right_header)
        right_layout.addWidget(self.right_column, 1)
        right_layout.addWidget(self.run_footer)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.content_area)
        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([880, 330])

        # `MainWindow` builds the single status bar across the whole
        # window, below the workspace (`ui/main_window.py`). This panel
        # only tells it, with `machine_changed`, when a machine task
        # touches the environment.

        self.root_layout.addWidget(self.sub_bar)
        self.root_layout.addWidget(self.splitter, 1)

        self.tabs: list[SubTabButton] = []
        # A tab is a box with the console and, when the action publishes
        # an endpoint, a browser next to it (`ui/tab_view.py`,
        # ADR-0008). `_consoles` exists because almost all this file
        # speaks to the console and not the box.
        self._views: dict[SubTabButton, TabView] = {}
        self._consoles: dict[SubTabButton, ConsoleView] = {}
        self._params: dict[SubTabButton, ParamsPanel] = {}
        self._runners: set[TaskRunner] = (
            set()
        )  # live references: without this Qt collects them mid-thread
        # which tab has a running task
        self._busy: dict[SubTabButton, TaskRunner] = {}
        # While saved tabs reopen they should not be saved step by step:
        # it saves once when the loop ends.
        self._restoring = False

        # The whole workspace is born with the repo's color: the
        # accordion's headers and panels build in gray and their first
        # palette comes from here, the same a theme change applies.
        self.set_palette(self.pal)
        self._refresh_security_summary(self.security_panel.state())
        self._restore_tabs()
        QTimer.singleShot(0, self._relayout_right)

    def _restore_tabs(self) -> None:
        """Reopen the action tabs left open last time, in their order.

        From `ui/params_store.py`. None runs anything: opening a tab is
        only that.
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
    def _build_right_header(self) -> QWidget:
        """Build the right column's single header.

        It shows the active repo with no tab open, and the current
        action's name when there is one.
        """
        head = QWidget()
        # By name: without a selector, the bottom line was inherited by
        # each child.
        head.setObjectName("rightHeader")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        # With no action open, the repo's logo; with one, the action's
        # emoji.
        self.right_header_logo = repo_logo.RepoLogoView(20, self.logo)
        self.right_header_icon = QLabel()
        self.right_header_icon.setStyleSheet(
            f"background: transparent; font-size: {Fonts.SIZE_LG}px;"
        )
        self.right_header_icon.setVisible(False)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(1)
        self.right_header_name = QLabel(self.project.name)
        self.right_header_name.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;"
        )
        # The action's description lives in the accordion's «Acción»
        # section, which shows it whole with its steps. Here only the
        # name.
        titles.addWidget(self.right_header_name)

        # Mark the open action a favorite, next to its name: the other
        # place to mark is the search row's stripe, which has to be gone
        # to. With no action open the header shows the repo, and there
        # is nothing to mark.
        self.fav_star = FavoriteStar(self.pal.accent)
        self.fav_star.setEnabled(False)
        self.fav_star.marked.connect(self._on_star_marked)

        lay.addWidget(self.right_header_logo, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.right_header_icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(titles, 1)
        lay.addWidget(self.fav_star, 0, Qt.AlignmentFlag.AlignVCenter)
        return head

    def _on_star_marked(self, value: bool) -> None:
        cap_id = self._header_cap_id
        if not cap_id:
            return
        favorites.set_favorite(cap_id, value)
        self.favorite_changed.emit()

    def refresh_favorite_star(self) -> None:
        """Catch the star up when another surface marked its action.

        It saves nothing again.
        """
        if self._header_cap_id:
            self.fav_star.set_favorite(favorites.is_favorite(self._header_cap_id))

    def _set_right_header(self, capability: Capability | None) -> None:
        """Show the open action, or the repo if there is none."""
        self.right_header_logo.setVisible(capability is None)
        self.right_header_icon.setVisible(capability is not None)
        if capability is None:
            self.right_header_name.setText(self.project.name)
        else:
            self.right_header_icon.setText(capability.icon)
            self.right_header_name.setText(capability.name)
        self._header_cap_id = capability.id if capability is not None else ""
        self.fav_star.setEnabled(bool(self._header_cap_id))
        self.fav_star.set_favorite(
            bool(self._header_cap_id) and favorites.is_favorite(self._header_cap_id)
        )

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        self.welcome_logo = repo_logo.RepoLogoView(64, self.logo)

        self.welcome_title = QLabel(self.project.name.upper())
        self.welcome_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_XXL}px; font-weight: 300; "
            f"letter-spacing: 8px;"
        )
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Selecciona una accion del panel izquierdo")
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
        hint = QLabel("Los parámetros de la acción\naparecen aquí")
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
        btn = QPushButton("▶  Ejecutar")
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
        this button in this repo (`ui/params_store`), and the defaults
        only if never touched.
        """
        console = self.open_tab(capability)
        panel = self.current_params()
        if panel is None:
            return
        if not panel.try_run():
            # The search thought it could run: say why not, in the same
            # console where the result would have appeared.
            for reason in panel.blockers():
                console.append_log(f"no se puede correr: {reason}", "warn")

    def open_tab(self, capability: Capability, axis_value: str = "") -> ConsoleView:
        """Open or focus an action's tab. **It runs nothing**.

        Running is pressing Run in the parameters panel.
        """
        return self._open(capability, axis_value)[1].console

    def _open(self, capability: Capability, axis_value: str = "") -> tuple[SubTabButton, TabView]:
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

        tab = SubTabButton(title, capability.icon, self.pal)
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
        console.append_log("Ajusta los parámetros a la derecha y pulsa Ejecutar.", "info")
        self.content_area.addWidget(view)
        self._views[tab] = view
        self._consoles[tab] = console
        view.cleared.connect(lambda t=tab: self._on_cleared(t))

        panel = ParamsPanel(capability, self.project, self.env_panel)
        panel.set_env(self.env_panel.values())

        def on_execute(payload: dict[str, Any], t: SubTabButton = tab) -> None:
            self._run(t, payload)

        def on_stop(serial: str, t: SubTabButton = tab) -> None:
            self._stop_live(t, serial)

        panel.execute_requested.connect(on_execute)
        panel.params_changed.connect(self.params_changed.emit)
        panel.params_changed.connect(lambda p=panel: self._refilter_env(p))
        panel.stop_requested.connect(on_stop)
        panel.clear_requested.connect(view.clear_console)
        self.params_stack.addWidget(panel)
        self.run_footer.addWidget(panel.footer)
        self._params[tab] = panel

        tab.clicked.connect(lambda t=tab: self._activate(t))
        tab.close_requested.connect(lambda t=tab: self.close_tab(t))

        self.empty_hint.setVisible(False)
        self._activate(tab)
        self._persist_tabs()
        return tab, view

    def _retitle(self, tab: SubTabButton, title: str) -> None:
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
        tab._sync_text()

    def _next_title(self, title: str) -> str:
        """Return the first free title: `Emulador`, `Emulador 2`..."""
        used = {t.title for t in self.tabs}
        n = 2
        while f"{title} {n}" in used:
            n += 1
        return f"{title} {n}"

    def _stop_live(self, tab: SubTabButton, serial: str) -> None:
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

    def _on_cleared(self, tab: SubTabButton) -> None:
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
        kills (`core/process.py::bind_to_app`).
        """
        runners = list(self._runners)
        for runner in runners:
            runner.cancel()
        for tab in list(self._views):
            self._views[tab].shutdown()
        deadline = time.monotonic() + timeout_ms / 1000
        for runner in runners:
            runner.wait(max(0, int((deadline - time.monotonic()) * 1000)))

    def close_tab(self, tab: SubTabButton) -> None:
        """Close a tab and stop what runs in it."""
        if tab not in self.tabs:
            return
        # Closing the tab stops what was running in it: for the
        # emulator, that is `adb emu kill` and not killing its process
        # (`core/tasks/emulators.py`). Signals cut first because the
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
            self._set_right_header(None)
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
        self.security_panel.set_palette(pal)
        self.info_panel.set_palette(pal)
        for section in self._all_sections:
            section.set_palette(pal)
        for grip in self._grips.values():
            grip.set_palette(pal)
        self.fav_star.set_accent(pal.accent)

    def _restyle(self) -> None:
        """Paint the backgrounds THIS panel sets.

        The runs sub-bar, the console's canvas, the right column's
        header and the two placeholders. Each panel repaints what is
        inside it.
        """
        # The action tabs bar is NOT tinted: it goes in the neutral gray
        # `Colors.SURFACE` in all eight themes. The line below does
        # belong to the repo.
        self.sub_bar.setStyleSheet(f"""
            QWidget#subBar {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {self.pal.border};
            }}
        """)
        self.content_area.setStyleSheet(f"background: {self.pal.bg};")
        self.right_header.setStyleSheet(
            f"QWidget#rightHeader {{ background: {self.pal.surface}; "
            f"border-bottom: 1px solid {self.pal.border}; }}"
        )
        self._params_placeholder.setStyleSheet(f"background: {self.pal.panel};")
        self._footer_placeholder.setStyleSheet(
            f"background: {self.pal.surface}; border-top: 1px solid {self.pal.border};"
        )
        self._footer_placeholder_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.pal.surface_alt}; color: {Colors.TEXT_MUTED};
                border: none; border-radius: 6px; padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
        """)

    def reveal_security(self) -> None:
        """Open this repo's Security section.

        The status bar's indicator calls it (`ui/main_window.py`).
        """
        self.security_section.set_expanded(True)

    # --- internal ---
    def _activate(self, tab: SubTabButton) -> None:
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
            self._set_right_header(panel.capability)
            self.info_panel.set_capability(panel.capability)
            # Opening an action opens its parameters; if it was folded
            # by hand, it opens again: it is what the click went looking
            # for.
            self.params_section.set_expanded(True, announce=False)
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

        A resized window, or the header grew with the action's
        description. Settings's height is «what is left».
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

        # The excess goes to the last open section, normally Settings,
        # but if folded Parameters absorbs it, and so on upward.
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
            # Settings also has a roomier minimum.
            reserve = self.MIN_BODY * sum(1 for s in sections[i + 1 :] if s.is_expanded())
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

    def apply_section_visibility(self) -> None:
        """Show or hide the sections by the saved preference."""
        hidden = section_visibility.hidden_sections()
        for section in self._all_sections:
            section.setHidden(self._section_ids[section] in hidden)
        self._relayout_right()

    def _show_sections_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addSection("Secciones visibles")
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

    def _section_wanted(self, section: AccordionSection) -> int:
        """Return the body height an open section asks for."""
        manual = self._manual.get(section)
        if manual is not None:
            return manual
        if section is self.info_section:
            return self._info_wanted()
        if section is self.security_section:
            return self._security_wanted()
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

    def _refresh_security_summary(self, state: dict[str, Any]) -> None:
        """Show how many targets are protected in the section's header.

        So closing it costs no information: folded it still says the one
        datum it opens for.
        """
        protected = len(protection.repo_protections(state))
        total = len(protection.TARGETS)
        self.security_section.set_summary(
            f"{protected} de {total} protegidos" if protected else "sin seguros"
        )

    def _on_env_changed(self, values: dict[str, Any]) -> None:
        for panel in self._params.values():
            panel.set_env(values)

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

    def _refresh_logo(self, *_args) -> None:
        """Reread the logo: `BRAND_ICON` may have changed."""
        self.logo = repo_logo.resolve(self.project.path)
        self.right_header_logo.set_logo(self.logo)
        self.welcome_logo.set_logo(self.logo)
        self.logo_changed.emit(self.logo)

    def _run(self, tab: SubTabButton, payload: dict[str, Any]) -> None:
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
        if not self._guard_ok(capability, payload, console):
            return

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
    def _guard_ok(
        self, capability: Capability, payload: dict[str, Any], console: ConsoleView
    ) -> bool:
        """Let pass, warn or block, by `core/protection.decide`.

        What decides is not «it is destructive» but «what it breaks,
        with THESE parameters, and whether that is protected in THIS
        repo»: a dry run of `clean_artifacts` asks nothing,
        `teardown_db` against `local` does not decide the same as
        against `remote`, and a protected target does not open a door to
        skip the guard: it closes it.
        """
        decision, targets = protection.decide(self.security_panel.state(), capability.id, payload)
        if decision == protection.Decision.ALLOW:
            return True

        if decision == protection.Decision.BLOCK:
            BlockedDialog(self.project, capability.name, targets, self).exec()
            which = ", ".join(t.label for t in targets)
            console.append_log(
                f"Bloqueado: {capability.name} toca {which} y este repo lo "
                f"tiene protegido. El seguro se quita en Configuracion, "
                f"seccion Seguridad.",
                "error",
            )
            return False

        dialog = ReminderDialog(self.project, capability.name, targets, self)
        if dialog.exec() == ReminderDialog.DialogCode.Accepted:
            return True
        console.append_log(
            f"Cancelado: {capability.name} no llego a correr sobre {self.project.name}.", "warn"
        )
        return False

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
        tab: SubTabButton,
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
                f"{len(values)} apps marcadas: una pestaña por cada una ({', '.join(values)}).",
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
        self, tab: SubTabButton, capability: Capability, payload: dict[str, Any]
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
        console.append_log(f"{capability.name}: cada paso va a su propia pestaña.", "info")
        launched = []
        for step_id in payload.get("steps") or []:
            sub_cap = registry.get_capability(step_id)
            if sub_cap is None:
                console.append_log(f"paso desconocido: {step_id}", "warn")
                continue
            console.append_log(f"→ {sub_cap.name}", "info")
            self.quick_run(sub_cap)
            launched.append(sub_cap.name)
        self._activate(tab)
        if launched:
            console.append_log(f"Lanzados: {', '.join(launched)}.", "ok")
        else:
            console.append_log("Ningún paso marcado.", "warn")

    def _run_real(
        self,
        tab: SubTabButton,
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

        # The log book does not exist yet (`core/store.py`,
        # docs/arquitectura/30_riesgos_y_pendientes.md): until it does,
        # a note is not lost but left marked in the console.
        def on_note(entry: str) -> None:
            console.append_log(f"✱ {entry}", "ok")

        def on_ask(question: str, shape: str, danger: bool, expect: str) -> None:
            self._answer_task(runner, question, shape, danger, expect)

        runner.noted.connect(on_note)
        runner.ask_requested.connect(on_ask)

        def _on_done(ok: bool) -> None:
            console.append_log("Hecho" if ok else "Terminó con errores", "ok" if ok else "error")
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
        (`core/context.py::ASK_*`) and not by how the question looks:

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
        that never comes. An empty answer is a «no» for `confirm`.
        """
        if expect:
            answer, ok = QInputDialog.getText(
                self, "Confirmar", question, QLineEdit.EchoMode.Normal
            )
            runner.provide_answer(answer if ok else "")
            return

        if shape in (context.ASK_SECRET, context.ASK_TEXT):
            mode = (
                QLineEdit.EchoMode.Password
                if shape == context.ASK_SECRET
                else QLineEdit.EchoMode.Normal
            )
            answer, ok = QInputDialog.getText(self, "Dato requerido", question, mode)
            # Cancelling is not answering empty: for some questions
            # empty means «use the derived value»
            # (`core/context.py::ASK_CANCELLED`).
            runner.provide_answer(answer if ok else context.ASK_CANCELLED)
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
        box.setWindowTitle("Confirmar" if danger else "Pregunta")
        box.setText(question)
        box.addButton("Sí", QMessageBox.ButtonRole.YesRole)
        no = box.addButton("No", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.exec()
        runner.provide_answer("no" if box.clickedButton() is no else "si")

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
        console.append_log(f"{len(steps)} paso(s) × {combos} variante(s)", "info")

        for step_id in steps:
            for _ in range(combos):
                pass
            console.append_log(f"paso «{step_id}» — no implementado (stub)", "warn")

        if payload["missing_env"]:
            console.append_log(f"faltan claves: {', '.join(payload['missing_env'])}", "error")
        else:
            console.append_log("Simulación completada", "ok")
