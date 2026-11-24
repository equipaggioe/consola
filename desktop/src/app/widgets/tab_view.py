"""The content of an action tab.

A launcher delivers a URL and not a log: the console is the first of two
views, and the second, the browser, is what is needed when a dev server
came up (ADR-0008).

The same box serves «Explorar base» (ADR-0015): a tree and a grid,
sharing the parameters panel and the tab's footer. The explorer goes in
a second section below the console, and both fold like the right
column's (`widgets/accordion_section.py`).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QPoint, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import db_explorer, section_visibility, session
from app.services.announce import announce
from app.services.envfile import Config
from app.services.language import QT_TRANSLATE_NOOP
from app.services.palettes import NEUTRAL, Palette
from app.services.projects import Project
from app.services.registry import Capability
from app.theme import Colors, Fonts, Metrics, mono
from app.widgets.accordion_section import AccordionSection
from app.widgets.browser_view import BrowserView, open_external
from app.widgets.console_view import ConsoleView
from app.widgets.elided_label import ElidedLabel
from app.widgets.led_indicator import LedIndicator
from app.widgets.splitter import Splitter

# The console of the tab, the word and not the app's name.
CONSOLA = QT_TRANSLATE_NOOP("tab_view", "Consola")
# The label of the chip leading to the second view, by
# `Capability.view`.
VIEW_NAMES = {
    "web": QT_TRANSLATE_NOOP("tab_view", "Navegador"),
    "db": QT_TRANSLATE_NOOP("tab_view", "Explorador"),
}

if TYPE_CHECKING:
    from app.widgets.db_explorer_view import DbExplorerView

# Qt's QWIDGETSIZE_MAX, which PySide does not export: no maximum.
_NO_MAXIMUM = 16_777_215


# The console's filter chips: the levels each one shows, and its label
# with the count.
FILTERS = {
    "error": (frozenset({"error"}), QT_TRANSLATE_NOOP("TabView", "Errores {0}")),
    "warn": (frozenset({"warn"}), QT_TRANSLATE_NOOP("TabView", "Avisos {0}")),
    "cmd": (frozenset({"cmd"}), QT_TRANSLATE_NOOP("TabView", "Comandos {0}")),
}


class TabView(QWidget):
    """The console's section, with the endpoint, and the explorer's."""

    # Clear: the tab decides whether it also stops its task
    cleared = Signal()
    # A section checked or unchecked in its headers' menu: id, visible
    section_toggled = Signal(str, bool)

    def __init__(
        self, capability: Capability, project: Project | None = None, parent: QWidget | None = None
    ) -> None:
        """Build the header and the console."""
        super().__init__(parent)
        self.capability = capability
        self.project = project
        self._url = ""
        self._web = False
        self._browser: BrowserView | None = None
        # imported on first use
        self._explorer: DbExplorerView | None = None
        self.pal = NEUTRAL
        self._chips: list[QPushButton] = []

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self.console = ConsoleView(self)
        self.stack = QStackedWidget(self)
        # Room at the right of the console's scroll bar for the grip of
        # the right column's line, which lies over it
        # (`widgets/splitter.py`), in the console's background.
        self.stack.setAutoFillBackground(True)
        self.stack.setContentsMargins(0, 0, Metrics.GRIP // 2, 0)
        self.stack.addWidget(self.console)
        self.console_section = AccordionSection(
            QCoreApplication.translate("tab_view", CONSOLA), self.stack
        )
        self.header = self.console_section.header
        # How many lines of each filter the console holds.
        self._counts = dict.fromkeys(FILTERS, 0)
        self._build_header()
        # «Explorar base»: the explorer's section, below the console,
        # while the connection lives.
        self.explorer_section: AccordionSection | None = None
        self.console.logged.connect(self._on_logged)
        self.console.emptied.connect(self._on_emptied)

        # The sections share the height in a splitter: its bars change
        # it by hand, with the mouse or the arrows. A bar of 1 px, which
        # Qt grabs in 5 (its «tiny mode»), painted as the header below
        # it: it does not show, only the cursor changes over it.
        self._split = Splitter(
            Qt.Orientation.Vertical,
            QCoreApplication.translate("TabView", "Alto de las secciones"),
        )
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(1)
        self._restyle()
        self._root.addWidget(self._split)
        # What is left when every section is folded.
        self._root.addStretch(0)
        self._add_section(self.console_section, 0)
        self.fit_sections()

    # --- building ---
    def _build_header(self) -> None:
        """Put the endpoint in the console section's header.

        The header names the view below: «Consola», or the browser when
        it is the one showing. After the name goes the endpoint the task
        published, which appears and disappears with the URL. Clear does
        not live here: it is in the footer, next to Run.
        """
        bar = self.header
        self.led = LedIndicator(bar, size=9)
        self.led.setAccessibleName(QCoreApplication.translate("TabView", "Estado del endpoint"))
        self.state_label = ElidedLabel(keep=0)
        self.state_label.setFont(theme.font(Fonts.SIZE_XS))

        self.url_label = ElidedLabel(keep=0)
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_label.setFont(mono(theme.font(Fonts.SIZE_XS)))

        self.copy_btn = self._chip(
            QCoreApplication.translate("TabView", "Copiar"),
            QCoreApplication.translate("TabView", "Copiar la URL al portapapeles"),
            self._copy_url,
        )
        self.external_btn = self._chip(
            QCoreApplication.translate("TabView", "Abrir ↗"),
            QCoreApplication.translate("TabView", "Abrir en el navegador del sistema"),
            lambda: open_external(self._url),
        )
        second = QCoreApplication.translate("tab_view", VIEW_NAMES.get(self.capability.view, ""))
        self.view_btn = self._chip(
            second,
            QCoreApplication.translate("TabView", "Ver {0} en esta pestaña").format(
                second.lower()
            ),
            self._toggle_view,
        )
        self.view_btn.setVisible(False)

        # The filter of the log: one chip per filter that has lines.
        # Several can be on at once; with none on, everything shows.
        self.filter_btns: dict[str, QPushButton] = {}
        tips = {
            "error": QCoreApplication.translate(
                "TabView", "Ver solo los errores; otro clic quita el filtro"
            ),
            "warn": QCoreApplication.translate(
                "TabView", "Ver solo los avisos; otro clic quita el filtro"
            ),
            "cmd": QCoreApplication.translate(
                "TabView", "Ver solo los comandos que corrió; otro clic quita el filtro"
            ),
        }
        for key, tip in tips.items():
            btn = self._chip("", tip, self._apply_filter)
            btn.setCheckable(True)
            self.filter_btns[key] = btn

        # Everything of the endpoint shows and hides together.
        self._endpoint_widgets = [
            self.led,
            self.state_label,
            self.url_label,
            self.copy_btn,
            self.external_btn,
            self.view_btn,
        ]

        # After the chevron and the name, before the stretch and the
        # summary; the chips go at the right end, the filters last.
        lay = bar.layout()
        assert isinstance(lay, QHBoxLayout)
        lay.insertSpacing(2, 8)
        for offset, widget in enumerate((self.led, self.state_label, self.url_label)):
            lay.insertWidget(3 + offset, widget)
        for chip in (self.copy_btn, self.external_btn, self.view_btn, *self.filter_btns.values()):
            lay.addWidget(chip)
        self._show_endpoint(False)
        self._sync_filters()

    def _add_section(self, section: AccordionSection, index: int) -> None:
        """Put a section in the splitter, with its fold and its menu."""
        self._split.insertWidget(index, section)
        self._split.setStretchFactor(index, 1)
        section.toggled.connect(self.fit_sections)
        header = section.header
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def on_menu(pos: QPoint) -> None:
            self._show_sections_menu(header.mapToGlobal(pos))

        header.customContextMenuRequested.connect(on_menu)

    def _sections(self) -> list[tuple[str, AccordionSection, bool]]:
        """Return each section, its id and whether it has content."""
        every: list[tuple[str, AccordionSection, bool]] = [("consola", self.console_section, True)]
        if self.explorer_section is not None:
            every.append(("explorador", self.explorer_section, True))
        return every

    def _show_sections_menu(self, global_pos: QPoint) -> None:
        """Check which sections show, like the right column's menu."""
        menu = QMenu(self)
        menu.addSection(QCoreApplication.translate("TabView", "Secciones visibles"))
        hidden = section_visibility.hidden_sections()
        ids = ["consola"]
        if self.capability.has_db_view:
            ids.insert(1, "explorador")
        for sid in ids:
            item = menu.addAction(section_visibility.title(sid))
            item.setCheckable(True)
            item.setChecked(sid not in hidden)

            def on_toggled(visible: bool, s: str = sid) -> None:
                self.section_toggled.emit(s, visible)

            item.toggled.connect(on_toggled)
        menu.exec(global_pos)

    @Slot()
    def fit_sections(self) -> None:
        """Show the sections and share the height among the open ones.

        A section shows if it has something and the Ver menu does not
        hide it. A folded one keeps only its header; the open ones split
        the rest in equal parts, which the bars then change by hand.
        With all folded, the stretch below takes the rest.
        """
        hidden = section_visibility.hidden_sections()
        shown = []
        for sid, section, has in self._sections():
            section.setVisible(has and sid not in hidden)
            if not section.isHidden():
                shown.append(section)
        for section in shown:
            folded = section.header.HEIGHT
            section.setMaximumHeight(_NO_MAXIMUM if section.is_expanded() else folded)
        anyone = any(s.is_expanded() for s in shown)
        self._root.setStretch(0, 1 if anyone else 0)
        self._root.setStretch(1, 0 if anyone else 1)
        # Relative weights: the splitter spreads its height by them.
        sizes = []
        for i in range(self._split.count()):
            widget = self._split.widget(i)
            assert isinstance(widget, AccordionSection)
            if widget.isHidden():
                sizes.append(0)
            else:
                sizes.append(10_000 if widget.is_expanded() else widget.header.HEIGHT)
        self._split.setSizes(sizes)

    @Slot(str, str)
    def _on_logged(self, _text: str, level: str) -> None:
        """Count a line in its filter's chip."""
        if level in self._counts:
            self._counts[level] += 1
            self._sync_filters()

    @Slot()
    def _on_emptied(self) -> None:
        """Count from zero, and show everything again."""
        self._counts = dict.fromkeys(FILTERS, 0)
        self._show_all()

    @Slot()
    def _show_all(self) -> None:
        """Turn the filters off: the console shows every line."""
        for btn in self.filter_btns.values():
            btn.setChecked(False)
        self._apply_filter()

    @Slot()
    def _apply_filter(self) -> None:
        """Show the levels of the chips that are on, or all of them."""
        on = [key for key, btn in self.filter_btns.items() if btn.isChecked()]
        levels = frozenset().union(*(FILTERS[key][0] for key in on)) if on else None
        self.console.set_filter(levels)
        self._sync_filters()

    def _sync_filters(self) -> None:
        """Show each chip with its count, only while it has lines.

        None shows while the browser takes the console's place.
        """
        for key, btn in self.filter_btns.items():
            count = self._counts[key]
            btn.setText(QCoreApplication.translate("TabView", FILTERS[key][1]).format(count))
            btn.setVisible(count > 0 and self.stack.currentWidget() is self.console)
        self._dress_filters()

    def _dress_filters(self) -> None:
        """Paint the chips that are on in the accent, errors in red."""
        for key, btn in self.filter_btns.items():
            look = theme.CHIP_ON if btn.isChecked() else theme.CHIP
            look.on(self.pal).dress(btn, fill=False)
            if key == "error" and not btn.isChecked():
                colors = btn.palette()
                colors.setColor(QPalette.ColorRole.ButtonText, Colors.ERROR)
                btn.setPalette(colors)

    def _show_endpoint(self, visible: bool) -> None:
        db = self.capability.has_db_view
        for w in self._endpoint_widgets:
            if w is self.view_btn:
                # Only the browser shares the console's place: the
                # explorer has its own section.
                w.setVisible(visible and self._web)
            elif w in (self.copy_btn, self.external_btn):
                # A database's URL is masked: copying it or «opening» it
                # in the browser is useless.
                w.setVisible(visible and not db)
            else:
                w.setVisible(visible)

    @Slot()
    def clear_console(self) -> None:
        """Empty the log and put the action's header back.

        Emptying completely would leave a nameless tab,
        indistinguishable from a just-opened one; these three lines are
        the same it was born with.
        """
        self.console.clear_console()
        self.console.append_log(f"─── {self.capability.name} ───", "info")
        if self.capability.description:
            self.console.append_log(self.capability.description, "info")
        self.cleared.emit()

    def _chip(self, text: str, tip: str, slot: Callable[[], None]) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(Metrics.TARGET)
        btn.setProperty(theme.CHIP_BUTTON, True)
        btn.setFont(theme.font(Fonts.SIZE_XS))
        self._chips.append(btn)
        btn.clicked.connect(slot)
        return btn

    # --- repo color ---
    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()
        self.console.set_palette(pal)
        if self._browser is not None:
            self._browser.set_palette(pal)
        if self._explorer is not None:
            self._explorer.set_palette(pal)

    def _restyle(self) -> None:
        theme.CONSOLE.on(self.pal).dress(self.stack)
        self.console_section.set_palette(self.pal)
        if self.explorer_section is not None:
            self.explorer_section.set_palette(self.pal)
        theme.HINT.on(self.pal).dress(self.state_label)
        for chip in self._chips:
            theme.CHIP.on(self.pal).dress(chip, fill=False)
        self._dress_filters()
        # A bar's line is Dark (`Style`); the header color hides it.
        colors = self._split.palette()
        header = theme.SECTION_HEADER.on(self.pal).palette()
        colors.setColor(QPalette.ColorRole.Dark, header.color(QPalette.ColorRole.Window))
        self._split.setPalette(colors)

    # --- endpoint ---
    @Slot(str, str, bool, str)
    def set_endpoint(self, url: str, label: str, web: bool, state: str) -> None:
        """Show the endpoint from `ctx.serve()` and its state.

        It comes twice per endpoint: when announced (`starting`) and
        when the port truly answers (`ready`) or is given up (`down`).
        """
        self._url = url
        self._web = web and self.capability.has_web_view
        self.url_label.set_full(url)
        self._set_state(state, label)

        if state == session.READY:
            # What was asked was to bring up a page or connect a
            # database: showing it finishes the work and is no surprise.
            # The console stays one click away, and if the process falls
            # it comes back by itself (`endpoint_down`).
            if self.capability.has_db_view:
                self._start_explorer(url)
            elif self._web:
                self.show_browser()
            elif self._browser is not None:
                self._browser.load(url)
        self._show_endpoint(True)

    def endpoint_down(self) -> None:
        """Stop offering the URL as alive: the task ended or fell."""
        if not self._url:
            return
        self._set_state(session.DOWN, self.state_label.property("label") or "")
        self.show_console()
        self._stop_explorer()
        self._show_endpoint(True)

    def _set_state(self, state: str, label: str = "") -> None:
        texts = {
            session.STARTING: ("amber", QCoreApplication.translate("TabView", "arrancando")),
            session.READY: ("green", QCoreApplication.translate("TabView", "listo")),
            session.DOWN: ("red", QCoreApplication.translate("TabView", "caído")),
        }
        led, text = texts.get(state, ("off", state))
        self.led.set_state(led)
        self.state_label.setProperty("label", label)
        said = f"{label} · {text}" if label else text
        self.state_label.set_full(said)
        # The state changes while the focus is elsewhere: a screen
        # reader would not read the label (WCAG 4.1.3).
        announce(self.window(), said, urgent=state == session.DOWN)
        alive = state != session.DOWN
        self.copy_btn.setEnabled(alive)
        self.external_btn.setEnabled(alive)

    @Slot()
    def _copy_url(self) -> None:
        QGuiApplication.clipboard().setText(self._url)
        self.console.append_log(
            QCoreApplication.translate("TabView", "URL copiada: {0}").format(self._url), "ok"
        )

    # --- views ---
    @Slot()
    def _toggle_view(self) -> None:
        if self.stack.currentWidget() is self.console:
            self.show_browser()
        else:
            self.show_console()

    def _name_view(self, name: str) -> None:
        """Name in the console section's header the view it shows."""
        self.header.title.setText(name.upper())
        self.header.setAccessibleName(name)

    def show_console(self) -> None:
        """Show the console, and its filter."""
        self.stack.setCurrentWidget(self.console)
        self._sync_filters()
        self.view_btn.setText(
            QCoreApplication.translate("tab_view", VIEW_NAMES.get(self.capability.view, ""))
        )
        self._name_view(QCoreApplication.translate("tab_view", CONSOLA))

    def show_browser(self) -> None:
        """Create the browser the first time it is needed.

        Lazy on purpose: a QWebEngineView is a separate process, and
        opening three SPAs should not start three engines until someone
        looks at one.
        """
        if self._browser is None:
            self._browser = BrowserView(self._url, self)
            self._browser.set_palette(self.pal)
            self.stack.addWidget(self._browser)
        elif self._browser.url != self._url:
            self._browser.load(self._url)
        self.stack.setCurrentWidget(self._browser)
        self._sync_filters()
        self.view_btn.setText(QCoreApplication.translate("tab_view", CONSOLA))
        self._name_view(QCoreApplication.translate("tab_view", VIEW_NAMES["web"]))

    def show_explorer(self) -> None:
        """Open the explorer's section."""
        if self.explorer_section is not None:
            self.explorer_section.set_expanded(True)

    # --- database explorer ---
    def _start_explorer(self, safe_url: str) -> None:
        """Open the explorer on the connection `explore_db` published.

        The connection, with its password, comes from the session and
        not the bar: only the masked URL travels there.
        """
        if self._explorer is not None or self.project is None:
            self.show_explorer()
            return
        url = session.read(self.project.name, db_explorer.session_key(safe_url))
        if not url:
            self.console.append_log(
                QCoreApplication.translate("TabView", "La tarea no publicó la conexión."), "error"
            )
            return
        from app.widgets.db_explorer_view import DbExplorerView

        server_root = Path(self.project.path) / Config.for_project(self.project.path).get(
            "SERVER_DIR", "server"
        )
        self._explorer = DbExplorerView(str(url), server_root, self.pal, self)
        self.explorer_section = AccordionSection(
            QCoreApplication.translate("tab_view", VIEW_NAMES["db"]), self._explorer
        )
        self.explorer_section.set_palette(self.pal)
        # The open table, what it holds and Contar, after the name.
        lay = self.explorer_section.header.layout()
        assert isinstance(lay, QHBoxLayout)
        title, subtitle, count = self._explorer.heading
        lay.insertSpacing(2, 8)
        lay.insertWidget(3, title)
        lay.insertWidget(4, subtitle)
        lay.addWidget(count)
        # Right below the console.
        self._add_section(self.explorer_section, 1)
        self.fit_sections()

    def _stop_explorer(self) -> None:
        if self._explorer is None or self.explorer_section is None:
            return
        self._explorer.shutdown()
        # The explorer goes with it: it is its body.
        self.explorer_section.setParent(None)
        self.explorer_section.deleteLater()
        self.explorer_section = None
        self._explorer = None
        self.fit_sections()

    def on_shown(self) -> None:
        """Reread what was queried when the tab returns to the front.

        It happens on showing, not with a reload button. The console
        comes back with every line: a filter does not stay hiding lines
        of a tab one was not looking at.
        """
        self._show_all()
        if self._explorer is not None:
            self._explorer.refresh()

    def shutdown(self) -> None:
        """Release whatever has its own threads, as the tab closes."""
        self._stop_explorer()

    # --- console (delegation) ---
    def append_log(self, text: str, level: str = "info") -> None:
        """Append one line to the console."""
        self.console.append_log(text, level)
