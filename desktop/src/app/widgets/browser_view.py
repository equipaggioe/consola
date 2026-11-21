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

from PySide6.QtCore import QCoreApplication, Qt, QUrl, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Colors, Fonts, Metrics, Spacing, mono

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
        bar = QFrame()
        bar.setFixedHeight(34)
        self._bar = bar
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(4)

        self.back_btn = self._tool(
            "‹", QCoreApplication.translate("BrowserView", "Atrás"), self._go_back
        )
        self.fwd_btn = self._tool(
            "›", QCoreApplication.translate("BrowserView", "Adelante"), self._go_forward
        )
        self.reload_btn = self._tool(
            "↻", QCoreApplication.translate("BrowserView", "Recargar"), self.reload
        )

        self.url_label = QLabel(self._url)
        self.url_label.setFont(mono(theme.font(Fonts.SIZE_XS)))

        self.external_btn = self._tool(
            "↗",
            QCoreApplication.translate("BrowserView", "Abrir en el navegador del sistema"),
            lambda: open_external(self._url),
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
        theme.TOOL_BAR.on(self.pal).band(self._bar, "bottom")
        theme.HINT.on(self.pal).dress(self.url_label)
        if self._fallback is not None:
            theme.CANVAS.on(self.pal).dress(self._fallback)
            theme.FILLED_BUTTON.on(self.pal).dress(self._opener, fill=False)

    def _tool(self, glyph: str, tip: str, slot: Callable[[], None]) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setFixedSize(24, 24)
        btn.setToolTip(tip)
        btn.setAccessibleName(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(theme.font(Fonts.SIZE_BASE))
        theme.glyph(btn, Colors.ON_SURFACE_VARIANT, "transparent", Colors.ON_SURFACE)
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
            QCoreApplication.translate(
                "BrowserView",
                "Esta instalación de PySide6 no trae QtWebEngine.\nInstala "
                "«PySide6-Addons» para ver la página aquí dentro.",
            )
        )
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setFont(theme.font(Fonts.SIZE_SM))
        theme.HINT.on(self.pal).dress(text)

        opener = QPushButton(
            QCoreApplication.translate("BrowserView", "Abrir en el navegador del sistema")
        )
        opener.setCursor(Qt.CursorShape.PointingHandCursor)
        opener.setFont(theme.font(Fonts.SIZE_SM))
        opener.setMinimumHeight(Metrics.FIELD + Spacing.SM)
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

    @Slot()
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

    @Slot()
    def _go_back(self) -> None:
        if self.page is not None:
            self.page.back()

    @Slot()
    def _go_forward(self) -> None:
        if self.page is not None:
            self.page.forward()

    @Slot(QUrl)
    def _on_url_changed(self, url: QUrl) -> None:
        """Change the label when navigating inside the app.

        `_url` stays the root the task published: it is what ↗ opens and
        what reloads when the dev server restarts.
        """
        self.url_label.setText(url.toString())
