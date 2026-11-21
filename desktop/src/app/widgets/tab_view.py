"""The content of an action tab.

A launcher delivers a URL and not a log: the console is the first of two
views, and the second, the browser, is what is needed when a dev server
came up (ADR-0008).

The same box serves «Explorar base» (ADR-0015): a tree and a grid
instead of text, sharing the parameters panel and the tab's footer. That
is why the switcher is called "view" and not "browser".
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import db_explorer, session
from app.services.envfile import Config
from app.services.language import QT_TRANSLATE_NOOP
from app.services.palettes import NEUTRAL, Palette
from app.services.projects import Project
from app.services.registry import Capability
from app.theme import Fonts, mono
from app.widgets.browser_view import BrowserView, open_external
from app.widgets.console_view import ConsoleView
from app.widgets.led_indicator import LedIndicator

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


class TabView(QWidget):
    """The header with the endpoint, and the console or second view."""

    # Clear: the tab decides whether it also stops its task
    cleared = Signal()

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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = self._build_header()
        self._restyle()

        self.console = ConsoleView(self)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.console)

        root.addWidget(self.header)
        root.addWidget(self.stack, 1)

    # --- building ---
    def _build_header(self) -> QFrame:
        """Build the bar that names the view below, like a section's.

        The right column's sections (`widgets/accordion.py`) say what
        they hold; this one says it for the left: «Consola», or the
        second view when it is the one showing. After the name goes the
        endpoint the task published, which appears and disappears with
        the URL. Clear does not live here: it is in the footer, next to
        Run.
        """
        bar = QFrame()
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 8, 0)
        lay.setSpacing(8)
        self.header_title = QLabel(QCoreApplication.translate("tab_view", CONSOLA).upper())

        self.led = LedIndicator(bar, size=9)
        self.led.setAccessibleName(QCoreApplication.translate("TabView", "Estado del endpoint"))
        self.state_label = QLabel("")
        self.state_label.setFont(theme.font(Fonts.SIZE_XS))

        self.url_label = QLabel("")
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

        # Everything of the endpoint shows and hides together.
        self._endpoint_widgets = [
            self.led,
            self.state_label,
            self.url_label,
            self.copy_btn,
            self.external_btn,
            self.view_btn,
        ]

        lay.addWidget(self.header_title)
        lay.addSpacing(8)
        lay.addWidget(self.led)
        lay.addWidget(self.state_label)
        lay.addWidget(self.url_label)
        lay.addStretch()
        lay.addWidget(self.copy_btn)
        lay.addWidget(self.external_btn)
        lay.addWidget(self.view_btn)
        self._show_endpoint(False)
        return bar

    def _show_endpoint(self, visible: bool) -> None:
        db = self.capability.has_db_view
        for w in self._endpoint_widgets:
            if w is self.view_btn:
                # It has its own rule: only with a second view to show.
                # `set_endpoint` decides it.
                w.setVisible(visible and (self._web or (db and self._explorer is not None)))
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
        btn.setFixedHeight(22)
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
        theme.CONSOLE_HEADER.on(self.pal).band(self.header, "bottom")
        self.header_title.setFont(theme.caption())
        theme.HINT.on(self.pal).dress(self.state_label)
        for chip in self._chips:
            theme.CHIP.on(self.pal).dress(chip, fill=False)

    # --- endpoint ---
    @Slot(str, str, bool, str)
    def set_endpoint(self, url: str, label: str, web: bool, state: str) -> None:
        """Show the endpoint from `ctx.serve()` and its state.

        It comes twice per endpoint: when announced (`starting`) and
        when the port truly answers (`ready`) or is given up (`down`).
        """
        self._url = url
        self._web = web and self.capability.has_web_view
        self.url_label.setText(url)
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
        self.state_label.setText(f"{label} · {text}" if label else text)
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
            if self.capability.has_db_view:
                self.show_explorer()
            else:
                self.show_browser()
        else:
            self.show_console()

    def show_console(self) -> None:
        """Show the console."""
        self.stack.setCurrentWidget(self.console)
        self.view_btn.setText(
            QCoreApplication.translate("tab_view", VIEW_NAMES.get(self.capability.view, ""))
        )
        self.header_title.setText(QCoreApplication.translate("tab_view", CONSOLA).upper())

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
        self.view_btn.setText(QCoreApplication.translate("tab_view", CONSOLA))
        self.header_title.setText(
            QCoreApplication.translate("tab_view", VIEW_NAMES["web"]).upper()
        )

    def show_explorer(self) -> None:
        """Show the explorer."""
        if self._explorer is None:
            return
        self.stack.setCurrentWidget(self._explorer)
        self.view_btn.setText(QCoreApplication.translate("tab_view", CONSOLA))
        self.header_title.setText(QCoreApplication.translate("tab_view", VIEW_NAMES["db"]).upper())

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
        self.stack.addWidget(self._explorer)
        self.show_explorer()

    def _stop_explorer(self) -> None:
        if self._explorer is None:
            return
        self._explorer.shutdown()
        self.stack.removeWidget(self._explorer)
        self._explorer.deleteLater()
        self._explorer = None

    def on_shown(self) -> None:
        """Reread what was queried when the tab returns to the front.

        It happens on showing, not with a reload button.
        """
        if self._explorer is not None:
            self._explorer.refresh()

    def shutdown(self) -> None:
        """Release whatever has its own threads, as the tab closes."""
        self._stop_explorer()

    # --- console (delegation) ---
    def append_log(self, text: str, level: str = "info") -> None:
        """Append one line to the console."""
        self.console.append_log(text, level)
