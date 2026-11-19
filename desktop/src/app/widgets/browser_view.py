"""The embedded browser of a launcher tab.

A Vite dev server delivers a URL, not a log: the console is the
by-product (ADR-0008). This view is the other half of that tab, and not
a rail button, because opening a URL runs nothing, records nothing and
has no parameters.

QtWebEngine ships in PySide6-Addons and the `PySide6` metapackage brings
it, but a `PySide6-Essentials` install does not: the import is guarded
and, without it, the view becomes a notice with a button that opens the
system browser. The tab keeps working; all that is lost is seeing it in
here.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Colors, Fonts

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView

    WEBENGINE = True
except ImportError:  # pragma: no cover
    QWebEngineView = None
    WEBENGINE = False


def open_external(url: str) -> None:
    """Open the URL in the system browser."""
    if url:
        webbrowser.open(url)


class BrowserView(QWidget):
    """A minimal bar (back, forward, reload, outside) and the page."""

    closed = Signal()

    def __init__(self, url: str = "", parent: QWidget | None = None) -> None:
        """Build the bar and page, or the no-QtWebEngine notice."""
        super().__init__(parent)
        self._url = url
        self.pal = NEUTRAL

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_bar())
        self._fallback: QWidget | None = None
        self.page: Any = None

        if QWebEngineView is not None:
            self.page = QWebEngineView(self)
            self.page.urlChanged.connect(self._on_url_changed)
            root.addWidget(self.page, 1)
        else:
            root.addWidget(self._build_fallback(), 1)

        self._restyle()

        if url:
            self.load(url)

    # --- building ---
    def _build_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        self._bar = bar
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(4)

        self.back_btn = self._tool("‹", "Atrás", self._go_back)
        self.fwd_btn = self._tool("›", "Adelante", self._go_forward)
        self.reload_btn = self._tool("↻", "Recargar", self.reload)

        self.url_label = QLabel(self._url)
        self.url_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-family: {Fonts.MONO}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.external_btn = self._tool(
            "↗", "Abrir en el navegador del sistema", lambda: open_external(self._url)
        )

        lay.addWidget(self.back_btn)
        lay.addWidget(self.fwd_btn)
        lay.addWidget(self.reload_btn)
        lay.addSpacing(6)
        lay.addWidget(self.url_label, 1)
        lay.addWidget(self.external_btn)
        return bar

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        bar = theme.TOOL_BAR.on(self.pal)
        self._bar.setStyleSheet(f"background: {bar.bg}; border-bottom: 1px solid {bar.border};")
        if self._fallback is not None:
            self._fallback.setStyleSheet(f"background: {theme.CANVAS.on(self.pal).bg};")
            button = theme.FILLED_BUTTON.on(self.pal)
            self._opener.setStyleSheet(f"""
                QPushButton {{
                    background: {button.bg}; color: {button.fg};
                    border: none; border-radius: 6px; padding: 8px 16px;
                    font-size: {Fonts.SIZE_SM}px;
                }}
                QPushButton:hover {{ background: {button.hover}; }}
            """)

    def _tool(self, glyph: str, tip: str, slot: Callable[[], None]) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setFixedSize(24, 24)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_BASE}px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT}; }}
        """)
        btn.clicked.connect(slot)
        return btn

    def _build_fallback(self) -> QWidget:
        """Without QtWebEngine: say why and offer the usual way out."""
        box = QWidget()
        self._fallback = box
        lay = QVBoxLayout(box)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        text = QLabel(
            "Esta instalación de PySide6 no trae QtWebEngine.\n"
            "Instala «PySide6-Addons» para ver la página aquí dentro."
        )
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;"
        )

        opener = QPushButton("Abrir en el navegador del sistema")
        opener.setCursor(Qt.CursorShape.PointingHandCursor)
        self._opener = opener
        opener.clicked.connect(lambda: open_external(self._url))

        lay.addWidget(text)
        lay.addWidget(opener, 0, Qt.AlignmentFlag.AlignHCenter)
        return box

    # --- API ---
    @property
    def url(self) -> str:
        """Return the URL the task published."""
        return self._url

    def load(self, url: str) -> None:
        """Load a URL."""
        self._url = url
        self.url_label.setText(url)
        if self.page is not None and url:
            self.page.setUrl(QUrl(url))

    def reload(self) -> None:
        """Reload, or load the endpoint's URL if no page is loaded yet.

        That is the normal case when the dev server took longer than the
        timeout: the tab stayed with the announced URL unloaded, and ↻
        is what one presses.
        """
        if self.page is None:
            return
        if self.page.url().isEmpty():
            self.load(self._url)
        else:
            self.page.reload()

    def _go_back(self) -> None:
        if self.page is not None:
            self.page.back()

    def _go_forward(self) -> None:
        if self.page is not None:
            self.page.forward()

    def _on_url_changed(self, url: QUrl) -> None:
        """Change the label when navigating inside the app.

        `_url` stays the root the task published: it is what ↗ opens and
        what reloads when the dev server restarts.
        """
        self.url_label.setText(url.toString())
