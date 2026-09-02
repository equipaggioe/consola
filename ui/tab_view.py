from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from core import session
from core.registry import Capability
from ui.browser_view import BrowserView, open_external
from ui.console_view import ConsoleView
from ui.theme import Colors, Fonts
from ui.widgets.led import LedIndicator

"""
El contenido de una pestana de accion.

Hasta ahora una pestana era una consola y nada mas. Un launcher no entrega un
log, entrega una URL: la consola pasa a ser la primera de dos vistas, y la
segunda —el navegador— es la que hace falta cuando lo que se levanto es un dev
server (docs/launchers.md 2.3).

La misma caja sirve para la pestana de Base de datos de PLAN.md 6, que ya
pedia exactamente esto: arbol y grilla en lugar de texto, compartiendo el panel
de parametros y el pie de la pestana. Por eso el conmutador se llama "vista" y
no "navegador".
"""

CONSOLA = 'Consola'


class TabView(QWidget):
    """Barra de endpoint + conmutador de vistas + (consola | navegador)."""

    def __init__(self, capability: Capability, parent=None):
        super().__init__(parent)
        self.capability = capability
        self._url = ''
        self._web = False
        self._browser: BrowserView | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.endpoint_bar = self._build_endpoint_bar()
        self.endpoint_bar.setVisible(False)

        self.console = ConsoleView(self)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.console)

        root.addWidget(self.endpoint_bar)
        root.addWidget(self.stack, 1)

    # --- construccion --------------------------------------------------
    def _build_endpoint_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 10, 0)
        lay.setSpacing(8)

        self.led = LedIndicator(bar, size=9)
        self.state_label = QLabel('')
        self.state_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;")

        self.url_label = QLabel('')
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.url_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-family: {Fonts.MONO}; font-size: {Fonts.SIZE_XS}px;")

        self.copy_btn = self._chip('Copiar', 'Copiar la URL al portapapeles',
                                   self._copy_url)
        self.external_btn = self._chip('Abrir ↗', 'Abrir en el navegador del sistema',
                                       lambda: open_external(self._url))
        self.view_btn = self._chip('Navegador', 'Ver la página en esta pestaña',
                                   self._toggle_view)
        self.view_btn.setVisible(False)

        lay.addWidget(self.led)
        lay.addWidget(self.state_label)
        lay.addWidget(self.url_label)
        lay.addStretch()
        lay.addWidget(self.copy_btn)
        lay.addWidget(self.external_btn)
        lay.addWidget(self.view_btn)
        return bar

    def _chip(self, text: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(22)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT_DIM};
                border: none; border-radius: 5px; padding: 0 10px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ color: {Colors.TEXT}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; background: transparent; }}
        """)
        btn.clicked.connect(slot)
        return btn

    # --- endpoint ------------------------------------------------------
    def set_endpoint(self, url: str, label: str, web: bool, state: str) -> None:
        """Lo que la tarea publico con `ctx.serve()`, con su estado.

        Llega dos veces por endpoint: al anunciarlo (`starting`) y cuando el
        puerto contesta de verdad (`ready`) o se da por perdido (`down`).
        """
        self._url = url
        self._web = web and self.capability.has_web_view
        self.endpoint_bar.setVisible(True)
        self.url_label.setText(url)
        self.view_btn.setVisible(self._web)
        self._set_state(state, label)

        if state == session.READY:
            # Lo que se pidio fue levantar una pagina: mostrarla es terminar el
            # trabajo, no una sorpresa. La consola queda a un clic, y si el
            # proceso se cae se vuelve sola (`endpoint_down`).
            if self._web:
                self.show_browser()
            elif self._browser is not None:
                self._browser.load(url)

    def endpoint_down(self) -> None:
        """La tarea termino o se cayo: la URL deja de ofrecerse como viva."""
        if not self._url:
            return
        self._set_state(session.DOWN, self.state_label.property('label') or '')
        self.show_console()

    def _set_state(self, state: str, label: str = '') -> None:
        textos = {
            session.STARTING: ('amber', 'arrancando'),
            session.READY: ('green', 'listo'),
            session.DOWN: ('red', 'caído'),
        }
        led, texto = textos.get(state, ('off', state))
        self.led.set_state(led)
        self.state_label.setProperty('label', label)
        self.state_label.setText(f'{label} · {texto}' if label else texto)
        vivo = state != session.DOWN
        self.copy_btn.setEnabled(vivo)
        self.external_btn.setEnabled(vivo)

    def _copy_url(self) -> None:
        QGuiApplication.clipboard().setText(self._url)
        self.console.append_log(f'URL copiada: {self._url}', 'ok')

    # --- vistas --------------------------------------------------------
    def _toggle_view(self) -> None:
        if self.stack.currentWidget() is self.console:
            self.show_browser()
        else:
            self.show_console()

    def show_console(self) -> None:
        self.stack.setCurrentWidget(self.console)
        self.view_btn.setText('Navegador')

    def show_browser(self) -> None:
        """Crea el navegador la primera vez que hace falta.

        Perezoso a proposito: un QWebEngineView es un proceso aparte, y abrir
        tres SPA no debe arrancar tres motores hasta que alguien mire alguna.
        """
        if self._browser is None:
            self._browser = BrowserView(self._url, self)
            self.stack.addWidget(self._browser)
        elif self._browser.url != self._url:
            self._browser.load(self._url)
        self.stack.setCurrentWidget(self._browser)
        self.view_btn.setText('Consola')

    # --- consola (delegacion) ------------------------------------------
    def append_log(self, text: str, level: str = 'info') -> None:
        self.console.append_log(text, level)
