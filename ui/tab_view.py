from __future__ import annotations
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from core import db_explorer, session
from core.envfile import Config
from core.projects import Project
from core.registry import Capability
from ui.browser_view import BrowserView, open_external
from ui.console_view import ConsoleView
from ui.theme import Colors, Fonts
from ui.palettes import Palette, NEUTRAL
from ui.widgets.led import LedIndicator

"""
El contenido de una pestana de accion.

Hasta ahora una pestana era una consola y nada mas. Un launcher no entrega un
log, entrega una URL: la consola pasa a ser la primera de dos vistas, y la
segunda —el navegador— es la que hace falta cuando lo que se levanto es un dev
server (ADR-0008).

La misma caja sirve para «Explorar base» (ADR-0015): arbol y
grilla en lugar de texto, compartiendo el panel de parametros y el pie de la
pestana. Por eso el conmutador se llama "vista" y no "navegador".
"""

def _chip_style(pal: Palette) -> str:
    return f"""
        QPushButton {{
            background: {pal.surface_alt}; color: {Colors.TEXT_DIM};
            border: none; border-radius: 5px; padding: 0 10px;
            font-size: {Fonts.SIZE_XS}px;
        }}
        QPushButton:hover {{ color: {Colors.TEXT}; }}
        QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; background: transparent; }}
    """


CONSOLA = 'Consola'
# El rotulo del chip que lleva a la segunda vista, segun `Capability.view`.
VIEW_NAMES = {'web': 'Navegador', 'db': 'Explorador'}


class TabView(QWidget):
    """Barra de herramientas + conmutador de vistas + (consola | segunda vista)."""
    cleared = Signal()   # Limpiar: la pestana decide si ademas detiene su tarea

    def __init__(self, capability: Capability, project: Project | None = None, parent=None):
        super().__init__(parent)
        self.capability = capability
        self.project = project
        self._url = ''
        self._web = False
        self._browser: BrowserView | None = None
        self._explorer = None   # DbExplorerView, importada al primer uso
        self.pal = NEUTRAL
        self._chips: list[QPushButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tool_bar = self._build_tool_bar()
        self._restyle()

        self.console = ConsoleView(self)
        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.console)

        root.addWidget(self.tool_bar)
        root.addWidget(self.stack, 1)
        # Solo los launchers publican un endpoint que mostrar; «Explorar base»
        # tambien, porque su boton es el unico camino de vuelta a la consola.
        # Limpiar no vive aca: esta en el pie, junto a Ejecutar.
        self.tool_bar.setVisible(capability.group == 'Launchers' or bool(capability.view))

    # --- construccion --------------------------------------------------
    def _build_tool_bar(self) -> QWidget:
        """La franja de arriba de la pestana: el endpoint que publico la
        tarea, que aparece y desaparece con la URL."""
        bar = QWidget()
        bar.setFixedHeight(36)
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
        second = VIEW_NAMES.get(self.capability.view, '')
        self.view_btn = self._chip(second, f'Ver {second.lower()} en esta pestaña',
                                   self._toggle_view)
        self.view_btn.setVisible(False)

        # Todo lo del endpoint se muestra y se esconde junto.
        self._endpoint_widgets = [self.led, self.state_label, self.url_label,
                                  self.copy_btn, self.external_btn, self.view_btn]

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
                # Tiene su propia regla: solo con una segunda vista que mostrar.
                # La decide `set_endpoint`.
                w.setVisible(visible and (self._web or (db and self._explorer is not None)))
            elif w in (self.copy_btn, self.external_btn):
                # La URL de una base va enmascarada: copiarla o «abrirla» en el
                # navegador no sirve para nada.
                w.setVisible(visible and not db)
            else:
                w.setVisible(visible)

    def clear_console(self) -> None:
        """Vacia el log y vuelve a poner la cabecera de la accion.

        Vaciar del todo dejaria una pestana sin nombre, indistinguible de otra
        recien abierta; estas tres lineas son las mismas con las que nacio.
        """
        self.console.clear_console()
        self.console.append_log(f'─── {self.capability.name} ───', 'info')
        if self.capability.description:
            self.console.append_log(self.capability.description, 'info')
        self.cleared.emit()

    def _chip(self, text: str, tip: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(22)
        btn.setStyleSheet(_chip_style(self.pal))
        self._chips.append(btn)
        btn.clicked.connect(slot)
        return btn

    # --- color del repo -------------------------------------------------
    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._restyle()
        self.console.set_palette(pal)
        if self._browser is not None:
            self._browser.set_palette(pal)
        if self._explorer is not None:
            self._explorer.set_palette(pal)

    def _restyle(self) -> None:
        self.tool_bar.setStyleSheet(
            f"background: {self.pal.surface}; border-bottom: 1px solid {self.pal.border};")
        for chip in self._chips:
            chip.setStyleSheet(_chip_style(self.pal))

    # --- endpoint ------------------------------------------------------
    def set_endpoint(self, url: str, label: str, web: bool, state: str) -> None:
        """Lo que la tarea publico con `ctx.serve()`, con su estado.

        Llega dos veces por endpoint: al anunciarlo (`starting`) y cuando el
        puerto contesta de verdad (`ready`) o se da por perdido (`down`).
        """
        self._url = url
        self._web = web and self.capability.has_web_view
        self.url_label.setText(url)
        self._set_state(state, label)

        if state == session.READY:
            # Lo que se pidio fue levantar una pagina o conectar una base:
            # mostrarla es terminar el trabajo, no una sorpresa. La consola
            # queda a un clic, y si el proceso se cae se vuelve sola
            # (`endpoint_down`).
            if self.capability.has_db_view:
                self._start_explorer(url)
            elif self._web:
                self.show_browser()
            elif self._browser is not None:
                self._browser.load(url)
        self._show_endpoint(True)

    def endpoint_down(self) -> None:
        """La tarea termino o se cayo: la URL deja de ofrecerse como viva."""
        if not self._url:
            return
        self._set_state(session.DOWN, self.state_label.property('label') or '')
        self.show_console()
        self._stop_explorer()
        self._show_endpoint(True)

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
            if self.capability.has_db_view:
                self.show_explorer()
            else:
                self.show_browser()
        else:
            self.show_console()

    def show_console(self) -> None:
        self.stack.setCurrentWidget(self.console)
        self.view_btn.setText(VIEW_NAMES.get(self.capability.view, ''))

    def show_browser(self) -> None:
        """Crea el navegador la primera vez que hace falta.

        Perezoso a proposito: un QWebEngineView es un proceso aparte, y abrir
        tres SPA no debe arrancar tres motores hasta que alguien mire alguna.
        """
        if self._browser is None:
            self._browser = BrowserView(self._url, self)
            self._browser.set_palette(self.pal)
            self.stack.addWidget(self._browser)
        elif self._browser.url != self._url:
            self._browser.load(self._url)
        self.stack.setCurrentWidget(self._browser)
        self.view_btn.setText(CONSOLA)

    def show_explorer(self) -> None:
        if self._explorer is None:
            return
        self.stack.setCurrentWidget(self._explorer)
        self.view_btn.setText(CONSOLA)

    # --- explorador de base ----------------------------------------------
    def _start_explorer(self, safe_url: str) -> None:
        """La conexion que publico `explore_db`, con su contrasena, sale de la
        sesion y no de la barra: ahi solo viaja la URL enmascarada."""
        if self._explorer is not None or self.project is None:
            self.show_explorer()
            return
        url = session.read(self.project.name, db_explorer.session_key(safe_url))
        if not url:
            self.console.append_log('La tarea no publicó la conexión.', 'error')
            return
        from ui.db_explorer_view import DbExplorerView
        server_root = Path(self.project.path) /             Config.for_project(self.project.path).get('SERVER_DIR', 'server')
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
        """La pestana volvio a primer plano: lo consultado se relee al mostrarse,
        no con un boton de recargar."""
        if self._explorer is not None:
            self._explorer.refresh()

    def shutdown(self) -> None:
        """La pestana se cierra: suelta lo que tenga hilos propios."""
        self._stop_explorer()

    # --- consola (delegacion) ------------------------------------------
    def append_log(self, text: str, level: str = 'info') -> None:
        self.console.append_log(text, level)
