from __future__ import annotations
import webbrowser

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)

from ui.theme import Colors, Fonts

"""
El navegador embebido de una pestana de launcher.

Un dev server de Vite entrega una URL, no un log: la consola es el subproducto
(docs/launchers.md 2.3). Esta vista es la otra mitad de esa pestana — no un
boton del rail, porque abrir una URL no ejecuta nada, no registra nada y no
tiene parametros.

QtWebEngine viaja en PySide6-Addons y el metapaquete `PySide6` lo trae, pero una
instalacion `PySide6-Essentials` no: el import va protegido y, si falta, la
vista se degrada a un cartel con un boton que abre el navegador del sistema. La
pestana sigue funcionando; lo unico que se pierde es verlo aca adentro.
"""

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE = True
except ImportError:                                    # pragma: no cover
    QWebEngineView = None
    WEBENGINE = False


def open_external(url: str) -> None:
    """Abre la URL en el navegador del sistema."""
    if url:
        webbrowser.open(url)


class BrowserView(QWidget):
    """Barra minima (atras / adelante / recargar / abrir afuera) + la pagina."""

    closed = Signal()

    def __init__(self, url: str = '', parent=None):
        super().__init__(parent)
        self._url = url

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_bar())

        if WEBENGINE:
            self.page = QWebEngineView(self)
            self.page.urlChanged.connect(self._on_url_changed)
            root.addWidget(self.page, 1)
        else:
            self.page = None
            root.addWidget(self._build_fallback(), 1)

        if url:
            self.load(url)

    # --- construccion --------------------------------------------------
    def _build_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(34)
        bar.setStyleSheet(
            f"background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(4)

        self.back_btn = self._tool('‹', 'Atrás', self._go_back)
        self.fwd_btn = self._tool('›', 'Adelante', self._go_forward)
        self.reload_btn = self._tool('↻', 'Recargar', self.reload)

        self.url_label = QLabel(self._url)
        self.url_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-family: {Fonts.MONO}; font-size: {Fonts.SIZE_XS}px;")

        self.external_btn = self._tool('↗', 'Abrir en el navegador del sistema',
                                       lambda: open_external(self._url))

        lay.addWidget(self.back_btn)
        lay.addWidget(self.fwd_btn)
        lay.addWidget(self.reload_btn)
        lay.addSpacing(6)
        lay.addWidget(self.url_label, 1)
        lay.addWidget(self.external_btn)
        return bar

    def _tool(self, glyph: str, tip: str, slot) -> QPushButton:
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
        """Sin QtWebEngine: se dice por que y se ofrece la salida de siempre."""
        box = QWidget()
        box.setStyleSheet(f"background: {Colors.BG};")
        lay = QVBoxLayout(box)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)

        texto = QLabel('Esta instalación de PySide6 no trae QtWebEngine.\n'
                       'Instala «PySide6-Addons» para ver la página aquí dentro.')
        texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        texto.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;")

        abrir = QPushButton('Abrir en el navegador del sistema')
        abrir.setCursor(Qt.CursorShape.PointingHandCursor)
        abrir.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT};
                border: none; border-radius: 6px; padding: 8px 16px;
                font-size: {Fonts.SIZE_SM}px;
            }}
        """)
        abrir.clicked.connect(lambda: open_external(self._url))

        lay.addWidget(texto)
        lay.addWidget(abrir, 0, Qt.AlignmentFlag.AlignHCenter)
        return box

    # --- API -----------------------------------------------------------
    @property
    def url(self) -> str:
        return self._url

    def load(self, url: str) -> None:
        self._url = url
        self.url_label.setText(url)
        if self.page is not None and url:
            self.page.setUrl(QUrl(url))

    def reload(self) -> None:
        """Recarga. Sin pagina cargada todavia, carga la URL del endpoint.

        Es el caso normal cuando el dev server tardo mas que el timeout: la
        pestana quedo con la URL anunciada y sin cargar, y ↻ es lo que uno
        aprieta.
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
        """Navegar dentro de la app cambia la etiqueta, no el endpoint.

        `_url` sigue siendo la raiz que publico la tarea: es la que abre el ↗ y
        la que se recarga cuando el dev server se reinicia.
        """
        self.url_label.setText(url.toString())
