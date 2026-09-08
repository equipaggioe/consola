from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QPushButton, QSizePolicy, QSplitter, QInputDialog, QLineEdit, QMessageBox,
    QFrame
)
from PySide6.QtCore import Qt, Signal, QRectF, QTimer, QEvent
from PySide6.QtGui import QPainter, QColor, QFont, QPainterPath, QPen

from ui.theme import Colors, Fonts
from core import toolstatus
from core.catalog import forget_machine_cache
from core import protection
from core.registry import Capability, registry
from core.projects import Project
from ui.console_view import ConsoleView
from ui.tab_view import TabView
from ui.params_panel import ParamsPanel
from ui.command_info_panel import CommandInfoPanel
from ui.env_panel import EnvPanel
from ui.security_panel import SecurityPanel
from ui.widgets.led import LedIndicator
from ui.widgets import (ReorderableTab, ReorderableBar,
                        AccordionSection, SectionResizeGrip)
from ui.guard_dialog import BlockedDialog, ReminderDialog
from ui import params_store
from ui.task_runner import TaskRunner


class SubTabButton(ReorderableTab, QWidget):
    """Pestana de segundo nivel: una ejecucion dentro del repo activo.

    Subordinada visualmente al nivel superior: mas baja, tipografia menor
    y subrayado (no barra superior) en el color del repo.
    """
    clicked = Signal()
    close_requested = Signal()

    HEIGHT = 34

    def __init__(self, title: str, icon: str, accent: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.accent = accent
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

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.update()

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._sync_text()
        self.update()

    def _sync_text(self) -> None:
        f = QFont(self.title_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        f.setBold(self.is_active)
        self.title_label.setFont(f)
        color = Colors.TEXT if self.is_active else (Colors.TEXT_DIM if self._hovered else Colors.TEXT_MUTED)
        self.title_label.setStyleSheet(f"background: transparent; color: {color};")

    def enterEvent(self, event):
        self._hovered = True
        self._sync_text()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.close_requested.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._reorder_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._reorder_release(event)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        accent = QColor(self.accent)

        if self.is_active:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(accent.red(), accent.green(), accent.blue(), 34))
            underline = QPainterPath()
            underline.addRoundedRect(QRectF(r.left() + 8, r.bottom() - 3, r.width() - 16, 2.5), 1.2, 1.2)
            p.fillPath(underline, accent)
        elif self._hovered or self.is_dragging:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(2, 4, -2, -3), 7, 7)
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))

        if self.is_dragging:
            pen = QPen(accent)
            pen.setWidthF(1.2)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(2.5, 4.5, -2.5, -3.5), 7, 7)
        p.end()


class PadlockChip(QLabel):
    """Un objetivo de proteccion en la barra de estado: su nombre corto con un
    candado cerrado (protegido) o abierto (sin proteger). Clic -> salta a la
    seccion Seguridad."""
    clicked = Signal()

    def __init__(self, chip: str, label: str, protected: bool, parent=None):
        super().__init__(f"{'🔒' if protected else '🔓'} {chip}", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Cerrado = a salvo (azul); abierto = expuesto a un destructivo sin red
        # (rojo de alerta).
        color = Colors.ACCENT if protected else Colors.ERROR
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;")
        self.setToolTip(
            f"{label}: {'protegido' if protected else 'sin proteger'}. "
            "Clic para administrar en Configuración → Seguridad.")

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class WorkspaceStatusBar(QWidget):
    """Barra inferior del espacio de trabajo: repo activo, servicios y estado.

    Antes eran dos barras apiladas (un selector de vistas que no cambiaba
    ninguna vista, y una barra de estado global repitiendo el mismo reloj).
    Se fusionaron en una sola.
    """
    security_clicked = Signal()  # clic en el indicador de seguros del repo activo

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.setFixedHeight(34)
        # Sin esto un QWidget derivado no pinta ni el fondo ni el borde de su
        # hoja de estilo: la linea de arriba que la separa del contenido no se
        # veia (mismo motivo que en `ui/widgets/accordion.py`).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.project_label = QLabel("")
        layout.addWidget(self.project_label)

        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(10)
        layout.addLayout(self.services_layout)

        layout.addStretch()

        # De aca a la derecha, cada seccion va separada de la anterior por una
        # linea fina: entorno · seguros · estado se leen como bloques distintos.
        self._sep_tools = self._divider()
        layout.addWidget(self._sep_tools)

        # Estado del entorno: se chequea solo, no con un boton. Va antes del
        # reloj porque es informacion de la maquina, no de esta corrida.
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setSpacing(10)
        layout.addLayout(self.tools_layout)
        self._tools: dict[str, tuple[LedIndicator, QLabel]] = {}
        self.refresh_tools()

        self._sep_security = self._divider()
        layout.addWidget(self._sep_security)

        # Los objetivos de proteccion del repo activo (`core/protection.py`),
        # cada uno con su candado abierto o cerrado, siempre a la vista sin
        # importar que accion este abierta arriba (`docs/seguro-destructivos.md`
        # §4). El clic en cualquiera salta a la seccion Seguridad.
        self.security_box = QWidget()
        self.security_box.setStyleSheet("background: transparent;")
        self._security_row = QHBoxLayout(self.security_box)
        self._security_row.setContentsMargins(0, 0, 0, 0)
        self._security_row.setSpacing(9)
        layout.addWidget(self.security_box)

        self._sep_status = self._divider()
        layout.addWidget(self._sep_status)

        self.status_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.status_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")
        layout.addWidget(self.status_label)

        self._restyle()

    def _divider(self) -> QFrame:
        """Linea vertical fina entre dos secciones de la barra."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {Colors.BORDER}; border: none;")
        line.setFixedHeight(16)
        return line

    def set_project(self, name: str, icon: str = "") -> None:
        self.project_label.setText(f"{icon or '◇'} {name}")

    def refresh_tools(self) -> None:
        """Vuelve a mirar el disco y repinta los indicadores del entorno.

        Se llama al construir la barra y despues de cada accion de maquina
        (instalar un SDK): como la instalacion deja las variables en el
        `os.environ` del proceso, el LED se pone en verde sin reiniciar nada.
        """
        for tool in toolstatus.detect():
            if tool.key not in self._tools:
                self._tools[tool.key] = self._build_tool(tool)
            led, label = self._tools[tool.key]
            # 'on', no 'green': el verde que late dice "esto esta corriendo",
            # y una herramienta instalada es un hecho quieto.
            led.set_state('on' if tool.found else 'off')
            tip = f"{tool.label}: {tool.detail}"
            led.setToolTip(tip)
            label.setToolTip(tip)
            label.setStyleSheet(
                f"color: {Colors.TEXT_DIM if tool.found else Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )

    def _build_tool(self, tool) -> tuple[LedIndicator, QLabel]:
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
        container = QWidget()
        container.setObjectName(f"service_{name}")
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=9)
        led.set_state('green')
        clayout.addWidget(led)

        label = QLabel(name)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")
        clayout.addWidget(label)

        self.services_layout.addWidget(container)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def clear(self) -> None:
        """Sin ningun repositorio abierto: nada que decir sobre repo, seguros
        ni tareas activas (`ui/main_window.py::_show_empty_state`)."""
        self.project_label.setText("")
        self.security_box.setVisible(False)
        # Sin seguros que mostrar, la division que los precede sobra.
        self._sep_security.setVisible(False)
        self.set_status("")

    def set_protection(self, state: dict) -> None:
        """Refresca los candados con el estado de CADA objetivo de proteccion
        (`core/protection.TARGETS`), no solo los protegidos: un objetivo sin
        seguro tambien es un dato, y con su candado abierto se ve de un
        vistazo. `state` es `{target_id: bool}` (`ui/security_panel.py`). Se
        llama al cambiar de repo y cada vez que se toca un interruptor."""
        while self._security_row.count():
            item = self._security_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.security_box.setVisible(True)
        self._sep_security.setVisible(True)
        for target in protection.TARGETS:
            protegido = protection.is_protected(state, target)
            chip = PadlockChip(target.chip, target.label, protegido)
            chip.clicked.connect(self.security_clicked.emit)
            self._security_row.addWidget(chip)
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(f"""
            WorkspaceStatusBar {{
                background: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        self.project_label.setStyleSheet(
            f"color: {self.accent}; font-size: {Fonts.SIZE_SM}px; font-weight: 600;"
        )


class TabPanel(ReorderableBar, QWidget):
    """Espacio de trabajo de UN repositorio.

    Contiene el segundo nivel de pestanas (las ejecuciones de ese repo),
    el area de consola y la barra de vistas. Cada repo tiene su propia
    instancia, asi que las sub-pestanas nunca se mezclan entre repos.
    """
    params_changed = Signal()   # algun panel guardo parametros nuevos
    machine_changed = Signal()  # una tarea de maquina cambio el entorno (SDK instalado, AVD creado)

    # Piso del cuerpo de una seccion del acordeon al arrastrarla a mano.
    MIN_BODY = 48

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.accent = project.color

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # --- barra de sub-pestanas -----------------------------------
        self.sub_bar = QWidget()
        self.sub_bar.setObjectName("subBar")
        self.sub_bar.setFixedHeight(SubTabButton.HEIGHT + 4)
        self.sub_bar.setStyleSheet(f"""
            QWidget#subBar {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)
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

        # --- area de contenido ---------------------------------------
        self.content_area = QStackedWidget()
        self.content_area.setStyleSheet(f"background: {Colors.BG};")

        self.welcome_widget = self._build_welcome()
        self.content_area.addWidget(self.welcome_widget)

        # --- columna derecha: cabecera unica + acordeon de tres secciones ---
        # Acordeon y no pestanas porque las tres se leen juntas: un bloqueo de
        # `ParamsPanel` puede decir "faltan claves de configuracion: VPS_IP" y
        # esa clave esta en la seccion de abajo. Con pestanas, el mensaje
        # apuntaria a algo que no se ve. Ver `ui/widgets/accordion.py`.
        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_params_placeholder())

        self.env_panel = EnvPanel(project)
        self.env_panel.values_changed.connect(self._on_env_changed)

        # Los seguros no salen de `config.env`: viven en `.consola/params.json`
        # y se guardan al tocarlos, sin pasar por el boton Guardar de
        # Configuracion (`ui/security_panel.py`).
        self.security_panel = SecurityPanel(project)
        self.security_panel.changed.connect(self._refresh_security_summary)

        # Seccion de arriba: la descripcion larga de la accion abierta y sus
        # pasos. Su cabecera siempre dice «Acción»; plegada, eso es todo lo que
        # se ve.
        self.info_panel = CommandInfoPanel()
        self.info_section = AccordionSection('Acción', self.info_panel, expanded=False)
        # Plegada de entrada: su cabecera ya resume cuantos objetivos estan
        # protegidos (`_refresh_security_summary`), asi que abrirla es solo para
        # tocar los seguros, no para enterarse.
        self.security_section = AccordionSection('Seguridad', self.security_panel,
                                                 expanded=False)
        # Desplegada de entrada y sin plegarse sola: es la seccion que se usa en
        # cada corrida, y abrir una accion para tener que abrirla ademas es un
        # clic de mas. `_relayout_right` le da su alto natural completo.
        self.params_section = AccordionSection('Parámetros', self.params_stack,
                                               expanded=True)
        self.config_section = AccordionSection('Configuración del repo', self.env_panel)
        # El estado de config.env va en el rotulo de la seccion, no en un
        # renglon aparte de su pie.
        self.env_panel.file_status_changed.connect(self.config_section.set_summary)
        self.config_section.set_summary(self.env_panel.file_status)

        # Un layout y no un `QSplitter`: plegar es ponerle un tope de alto a la
        # seccion, y un splitter guarda sus propios tamanos aparte — los dos
        # mandos peleaban y el reparto solo cuajaba un turno despues.
        #
        # Quien reparte es `_relayout_right`, que le calcula el tope a cada una;
        # el layout solo lo obedece. Dejarselo a los factores de estiramiento no
        # alcanzaba: `params_stack` y `env_panel` piden alturas que no tienen
        # nada que ver con lo que la columna puede dar, y negociando entre ellos
        # una seccion terminaba con el alto de otra.
        # Alto de cuerpo (sin cabecera) elegido a mano arrastrando la barra de
        # abajo. `None` = seguir el reparto automatico de `_relayout_right`. Se
        # limpia sola al plegar la seccion: reabrirla vuelve a autoajustarse.
        self._manual: dict[AccordionSection, int | None] = {}
        self._grips: dict[AccordionSection, SectionResizeGrip] = {}
        self._sections = (self.info_section, self.security_section,
                          self.params_section, self.config_section)

        self.right_column = QWidget()
        self._column = QVBoxLayout(self.right_column)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)
        for section in self._sections:
            # Quien estira lo decide `_relayout_right` con `setStretchFactor`:
            # tiene que ser la ultima seccion abierta que no este fijada a mano,
            # que no siempre es Configuracion. Sin eso, con Configuracion plegada
            # el sobrante caia en el resorte del final y quedaba un hueco muerto.
            self._column.addWidget(section, 0)
            section.toggled.connect(self._on_section_toggled)
            # Configuracion es la ultima: no tiene con quien negociar hacia abajo.
            if section is not self.config_section:
                self._manual[section] = None
                grip = SectionResizeGrip()
                grip.pressed.connect(lambda s=section: self._begin_resize(s))
                grip.dragged.connect(
                    lambda d, s=section: self._resize_section(s, d))
                grip.reset.connect(lambda s=section: self._resize_section(s, None))
                self._column.addWidget(grip)
                self._grips[section] = grip
        # Con TODO plegado no queda quien estire: este resorte se come el
        # sobrante para que las cabeceras se apilen arriba.
        self._column.addStretch(0)
        # Recien ahora: el filtro dispara `_relayout_right`, que necesita las
        # secciones y las barras ya armadas.
        self.right_column.installEventFilter(self)   # ver `eventFilter`

        self.right_header = self._build_right_header()

        # Pie fijo con Ejecutar / Simulacro: fuera del acordeon, para que el
        # boton no se pliegue con la seccion de Parametros ni haya que
        # scrollear hasta el. Una pila con un pie por accion abierta
        # (`ParamsPanel.footer`), mas un placeholder deshabilitado para cuando
        # no hay ninguna.
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

        # La barra de estado ya no vive aca: es una sola, a lo ancho de toda la
        # ventana, y la arma `MainWindow` debajo del rail y el espacio de trabajo
        # (`ui/main_window.py`). Este panel solo le avisa, con `machine_changed`,
        # cuando una tarea de maquina toca el entorno.

        self.layout.addWidget(self.sub_bar)
        self.layout.addWidget(self.splitter, 1)

        self.tabs: list[SubTabButton] = []
        # La pestana ya no es una consola suelta: es una caja con la consola y,
        # cuando la accion publica un endpoint, un navegador al lado
        # (`ui/tab_view.py`, docs/launchers.md 2.3). `_consoles` sigue existiendo
        # porque casi todo el archivo habla con la consola y no con la caja.
        self._views: dict[SubTabButton, TabView] = {}
        self._consoles: dict[SubTabButton, ConsoleView] = {}
        self._params: dict[SubTabButton, ParamsPanel] = {}
        self._runners: set[TaskRunner] = set()  # referencias vivas: sin esto Qt las recolecta a mitad de hilo
        self._busy: dict[SubTabButton, TaskRunner] = {}  # que pestana tiene tarea corriendo
        # Mientras se reabren las pestanas guardadas no hay que volver a
        # guardarlas paso a paso: se guarda una vez al terminar el bucle.
        self._restoring = False

        self._refresh_security_summary(self.security_panel.state())
        self._restore_tabs()
        QTimer.singleShot(0, self._relayout_right)

    def _restore_tabs(self) -> None:
        """Reabre las pestanas de accion que quedaron abiertas la vez anterior
        (`ui/params_store.py`), en su orden. Ninguna corre nada: abrir una
        pestana es solo eso."""
        self._restoring = True
        try:
            for cap_id in params_store.load_tabs(self.project.path):
                capability = registry.get_capability(cap_id)
                if capability is not None:
                    self.open_tab(capability)
        finally:
            self._restoring = False
        # Reescribe la lista ya limpia: si el catalogo perdio un boton, su id
        # guardado no vuelve a arrastrarse.
        self._persist_tabs()

    def _persist_tabs(self) -> None:
        """Anota que pestanas quedan abiertas, en orden, para el proximo
        arranque. Una pestana sin panel (a medio cerrar) se salta."""
        if self._restoring:
            return
        ids = [self._params[t].capability.id
               for t in self.tabs if t in self._params]
        params_store.save_tabs(self.project.path, ids)

    def tabs_reordered(self) -> None:
        self._persist_tabs()

    # --- construccion ------------------------------------------------
    def _build_right_header(self) -> QWidget:
        """Cabecera unica de la columna derecha: reemplaza el rotulo fijo
        'Configuracion del repo' — muestra el repo activo sin pestana
        abierta, y el nombre de la accion en curso cuando hay una."""
        head = QWidget()
        head.setStyleSheet(f"background: {Colors.SURFACE};")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        self.right_header_icon = QLabel(self.project.icon or "◇")
        self.right_header_icon.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_LG}px;")

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(1)
        self.right_header_name = QLabel(self.project.name)
        self.right_header_name.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;"
        )
        # La descripcion de la accion vive ahora en la seccion «Acción» del
        # acordeon, que la muestra entera con sus pasos. Aca solo el nombre.
        titles.addWidget(self.right_header_name)

        lay.addWidget(self.right_header_icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(titles, 1)
        return head

    def _set_right_header(self, icon: str, name: str,
                          capability: Capability | None = None) -> None:
        # `capability` se sigue recibiendo por compatibilidad con quien llama;
        # el nivel (atómica/compuesta) ya no se muestra aquí — vive en el
        # tooltip de la fila del rail y en la sección «Acción».
        self.right_header_icon.setText(icon or "◇")
        self.right_header_name.setText(name)

    def _build_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)

        self.diamond_label = QLabel(self.project.icon or "◇")
        self.diamond_label.setStyleSheet(f"color: {self.accent}; font-size: 54px;")
        self.diamond_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.welcome_title = QLabel(self.project.name.upper())
        self.welcome_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: {Fonts.SIZE_XXL}px; font-weight: 300; letter-spacing: 8px;"
        )
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Selecciona una accion del panel izquierdo")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_BASE}px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.path_label = QLabel(self.project.path)
        self.path_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(self.diamond_label, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.welcome_title, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(18)
        lay.addWidget(self.path_label, 0, Qt.AlignmentFlag.AlignHCenter)
        return w

    def _build_params_placeholder(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background: {Colors.SURFACE};")
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
        """Pie sin accion abierta: Ejecutar visible pero deshabilitado, para
        que la barra no cambie de alto al abrir la primera accion."""
        foot = QWidget()
        foot.setStyleSheet(f"background: {Colors.SURFACE}; border-top: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)
        lay.addStretch()
        btn = QPushButton("▶  Ejecutar")
        btn.setFixedHeight(34)
        btn.setEnabled(False)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT_MUTED};
                border: none; border-radius: 6px; padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
        """)
        lay.addWidget(btn)
        return foot

    # --- reordenar arrastrando ---------------------------------------
    def _tab_layout(self):
        return self.tabs_layout

    # --- API ---------------------------------------------------------
    def quick_run(self, capability: Capability) -> None:
        """Boton de 'correr' del rail: abre (o reusa) la pestana y la
        ejecuta de una, con los parametros de esa pestana — que al abrirse
        son los guardados para este boton en este repo (`ui/params_store`),
        y los por defecto solo si nunca se tocaron."""
        console = self.open_tab(capability)
        panel = self.current_params()
        if panel is None:
            return
        if not panel.try_run():
            # El rail creyo que podia correr: decir por que no, en la misma
            # consola donde habria salido el resultado.
            for reason in panel.blockers():
                console.append_log(f"no se puede correr: {reason}", "warn")

    def open_tab(self, capability: Capability, axis_value: str = '') -> ConsoleView:
        """Abre (o enfoca) la pestana de una accion. **No ejecuta nada**:
        ejecutar es apretar Ejecutar en el panel de parametros."""
        return self._open(capability, axis_value)[1].console

    def _open(self, capability: Capability,
              axis_value: str = '') -> tuple[SubTabButton, TabView]:
        """Lo mismo que `open_tab`, devolviendo tambien la pestana.

        El reparto en pestanas de un eje `fanout` (docs/launchers.md 2.1)
        necesita correr una tarea *en* la pestana que acaba de abrir, y para eso
        hace falta el boton, no solo su consola.
        """
        title = f"{capability.name} {axis_value}".strip()

        for tab in self.tabs:
            if tab.title != title:
                continue
            # Una pestana ocupada por algo que corre en vivo no se reusa: se
            # abre otra. Es lo que permite tener dos emuladores a la vez sin
            # tener que esperar a que se cierre el primero.
            if capability.kind == 'live' and tab in self._busy:
                title = self._next_title(title)
                break
            self._activate(tab)
            return tab, self._views[tab]

        tab = SubTabButton(title, capability.icon, self.accent)
        tab.setToolTip(capability.description)
        self.tabs_layout.addWidget(tab)
        self.tabs.append(tab)

        view = TabView(capability, self.content_area)
        console = view.console
        console.append_log(f"─── {capability.name} ───", "info")
        if capability.description:
            console.append_log(capability.description, "info")
        console.append_log("Ajusta los parámetros a la derecha y pulsa Ejecutar.", "info")
        self.content_area.addWidget(view)
        self._views[tab] = view
        self._consoles[tab] = console

        panel = ParamsPanel(capability, self.project, self.env_panel)
        panel.set_env(self.env_panel.values())
        panel.execute_requested.connect(lambda payload, t=tab: self._run(t, payload))
        panel.params_changed.connect(self.params_changed.emit)
        panel.stop_requested.connect(lambda serial, t=tab: self._stop_live(t, serial))
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
        """Renombra una pestana ya abierta.

        Lo usa el reparto de `fanout`: la pestana generica «Servir SPA Vite»
        pasa a llamarse «Servir SPA Vite panel» cuando se sabe cual arranco. Una
        pestana por proceso vivo, y el nombre dice cual (docs/launchers.md 2.1).
        """
        usados = {t.title for t in self.tabs if t is not tab}
        if title in usados:
            title = self._next_title(title)
        tab.title = title
        tab.title_label.setText(title)
        tab._sync_text()

    def _next_title(self, title: str) -> str:
        """`Emulador`, `Emulador 2`, `Emulador 3`... el primero que este libre."""
        usados = {t.title for t in self.tabs}
        n = 2
        while f'{title} {n}' in usados:
            n += 1
        return f'{title} {n}'

    def _stop_live(self, tab: SubTabButton, serial: str) -> None:
        """El ✕ de la cabecera de estado: apaga algo que quedo corriendo.

        Corre la capacidad oculta `stop_emulator` como cualquier otra tarea —
        misma consola, mismo log — en vez de tocar adb desde la interfaz.
        """
        capability = registry.get_capability('stop_emulator')
        console = self._consoles.get(tab)
        if capability is None or capability.func is None or console is None:
            return
        self._run_real(tab, console, capability, {'serial': serial}, track=False)

    def close_tab(self, tab: SubTabButton) -> None:
        if tab not in self.tabs:
            return
        # Cerrar la pestana detiene lo que estaba corriendo en ella: para el
        # emulador, eso es `adb emu kill` y no matarle el proceso
        # (`core/tasks/emulators.py`). Las senales se cortan primero porque la
        # consola se destruye en este mismo metodo y la tarea sigue viva unos
        # instantes mas.
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
            self._set_right_header(self.project.icon, self.project.name)
            self.info_panel.set_capability(None)
            self.info_section.set_expanded(False, announce=False)
            # Parametros se queda desplegada: es su estado por defecto (aunque
            # ahora solo muestre el placeholder).
            self._relayout_right()

    def current_console(self) -> ConsoleView | None:
        """La consola de la pestana activa.

        Se resuelve por la pestana y no por el widget visible: con el navegador
        arriba, el widget visible no es la consola — pero la consola sigue
        siendo la de esa pestana, y ahi es donde tiene que escribirse.
        """
        for tab in self.tabs:
            if tab.is_active:
                return self._consoles.get(tab)
        return None

    def current_view(self) -> TabView | None:
        w = self.content_area.currentWidget()
        return w if isinstance(w, TabView) else None

    def current_params(self) -> ParamsPanel | None:
        w = self.params_stack.currentWidget()
        return w if isinstance(w, ParamsPanel) else None

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.diamond_label.setStyleSheet(f"color: {accent}; font-size: 54px;")
        for tab in self.tabs:
            tab.set_accent(accent)
        for panel in self._params.values():
            panel.set_accent(accent)
        self.env_panel.set_accent(accent)

    def reveal_security(self) -> None:
        """Despliega la seccion Seguridad de este repo. La llama el indicador
        de la barra de estado (`ui/main_window.py`)."""
        self.security_section.set_expanded(True)

    # --- interno ------------------------------------------------------
    def _activate(self, tab: SubTabButton) -> None:
        for t in self.tabs:
            t.set_active(t is tab)
        view = self._views.get(tab)
        if view is not None:
            self.content_area.setCurrentWidget(view)
        panel = self._params.get(tab)
        if panel is not None:
            self.params_stack.setCurrentWidget(panel)
            self.run_footer.setCurrentWidget(panel.footer)
            self.env_panel.filter_for(panel.relevant_keys())
            self._set_right_header(panel.capability.icon, panel.capability.name,
                                   panel.capability)
            self.info_panel.set_capability(panel.capability)
            # Abrir una accion despliega sus parametros; si la habias plegado
            # a mano, vuelve a abrirse — es lo que fuiste a buscar al clic.
            self.params_section.set_expanded(True, announce=False)
            QTimer.singleShot(0, self._relayout_right)

    def eventFilter(self, obj, event):
        """La columna derecha cambio de alto (ventana redimensionada, o la
        cabecera crecio con la descripcion de la accion): hay que repartir de
        nuevo, porque el alto de Configuracion es «lo que sobre»."""
        if obj is self.right_column and event.type() == QEvent.Type.Resize:
            self._relayout_right()
        return super().eventFilter(obj, event)

    def _relayout_right(self, *_args) -> None:
        """Le calcula el alto a cada una de las cuatro secciones.

        Plegada, una seccion es solo su cabecera. Abiertas, Seguridad se queda
        con lo que sus casillas necesitan y Parametros con lo que pida su
        accion —hasta la mitad larga de la columna, para que una accion con
        muchas opciones no deje al resto en un hilo—; Configuracion recibe lo
        que sobre, que para eso es la unica con scroll largo. Una seccion
        arrastrada a mano (`_manual`) manda sobre todo eso.

        Reparte CUERPOS, no secciones enteras: `alto` arranca en la cabecera y
        lo que se suma es el cuerpo. Mezclar las dos unidades hacia que la
        primera arrastrada saltara el alto de su cabecera de golpe.
        """
        total = self.right_column.height()
        if total <= 0:
            return
        secciones = self._sections
        self._sync_grips()
        # Las barras de arrastre tambien ocupan alto. Sin descontarlas se
        # repartian mas pixeles de los que hay y el layout tenia que apretar
        # algun cuerpo por debajo de su minimo para que entrara todo.
        gastado = sum(s.header_height() for s in secciones) + sum(
            SectionResizeGrip.HEIGHT for s in secciones[:-1] if self._grip_visible(s))
        alto = {s: s.header_height() for s in secciones}
        libre = max(0, total - gastado)

        # El sobrante va a la ultima seccion abierta — normalmente Configuracion,
        # pero si esta plegada lo absorbe Parametros, y asi hacia arriba. Antes
        # iba siempre a Configuracion: con ella plegada el resto caia en el
        # resorte del final y la ultima cabecera se despegaba del borde de abajo
        # dejando un hueco muerto.
        absorbente = next((s for s in reversed(secciones) if s.is_expanded()), None)
        # La ultima abierta no tiene barra propia (no hay con quien negociar
        # debajo), asi que un alto a mano suyo es de un estado anterior: se cae.
        # Si no, ese valor viejo se quedaba corto y volvia el hueco.
        if absorbente in self._manual:
            self._manual[absorbente] = None

        for i, section in enumerate(secciones[:-1]):
            if not section.is_expanded():
                continue
            # Le guardamos el piso a cada seccion abierta que quede debajo: una
            # seccion desplegada que muestra cero cuerpo se lee como rota. Es lo
            # que hace que la barra tope al arrastrar en vez de borrar lo de
            # abajo. Configuracion, ademas, tiene un minimo mas generoso.
            reserva = self.MIN_BODY * sum(1 for s in secciones[i + 1:] if s.is_expanded())
            if (self._manual[section] is None and section is self.params_section
                    and self.config_section.is_expanded()):
                reserva = max(reserva, 120)
            # Pero la reserva no puede comerse el piso de esta misma seccion.
            reserva = min(reserva, max(0, libre - self.MIN_BODY))
            dar = max(0, min(self._section_wanted(section), libre - reserva))
            alto[section] += dar
            libre -= dar

        if absorbente is not None:
            alto[absorbente] += libre

        for section, valor in alto.items():
            # Tope y no alto fijo: con las tres clavadas, la columna imponia su
            # suma como alto minimo y la ventana ya no se podia achicar. El
            # piso queda en la cabecera, que es lo unico irrenunciable.
            section.setMaximumHeight(valor)
            section.setMinimumHeight(section.header_height())
            # Y ademas el hint, que es por donde el layout reparte de verdad
            # (ver `AccordionSection.set_allotted`).
            section.set_allotted(valor)
            # Si igual sobrara un pixel por redondeo, que se lo quede la
            # absorbente y no el resorte del final.
            self._column.setStretchFactor(section, 1 if section is absorbente else 0)

    def _on_section_toggled(self, *_args) -> None:
        # Plegar una seccion descarta su alto manual: al reabrirla se espera el
        # tamano que le calcula el contenido, no el que tenia hace tres clics.
        for section in self._manual:
            if not section.is_expanded():
                self._manual[section] = None
        self._relayout_right()

    def _begin_resize(self, section: AccordionSection) -> None:
        """Arranca un arrastre desde el alto que la seccion tiene EN PANTALLA.

        Sin esto el arrastre seguia contando desde el valor guardado, que el
        reparto pudo haber recortado (no habia lugar): quedaba una zona muerta
        en la que mover el mouse no movia nada hasta recuperar la diferencia.
        """
        if section in self._manual:
            self._manual[section] = max(0, section.height() - section.header_height())

    def _resize_section(self, section: AccordionSection, delta: int | None) -> None:
        """Fija (o suelta, con `delta=None`) el alto del cuerpo de una seccion.
        El resto se reparte lo que quede en `_relayout_right`."""
        if delta is None:
            self._manual[section] = None
        else:
            base = self._manual[section]
            if base is None:
                base = max(0, section.height() - section.header_height())
            # Piso: por debajo el scroll del cuerpo queda mas chico que su propia
            # barra y no se puede ni scrollear. Para achicar mas esta el chevron.
            self._manual[section] = max(self.MIN_BODY, base + delta)
        self._relayout_right()

    def _grip_visible(self, section: AccordionSection) -> bool:
        """Hay algo que negociar: la seccion esta abierta y hay alguna abierta
        debajo con la que intercambiar alto."""
        i = self._sections.index(section)
        return section.is_expanded() and any(
            s.is_expanded() for s in self._sections[i + 1:])

    def _sync_grips(self) -> None:
        for section, grip in self._grips.items():
            grip.setVisible(self._grip_visible(section))

    def _section_wanted(self, section: AccordionSection) -> int:
        """Alto de cuerpo que pide una seccion abierta."""
        manual = self._manual.get(section)
        if manual is not None:
            return manual
        if section is self.info_section:
            return self._info_wanted()
        if section is self.security_section:
            return self._security_wanted()
        # Parametros pide su alto natural entero: la idea es ver todas las
        # opciones de la accion sin scroll. Que Configuracion no se quede sin
        # nada lo cubre la reserva de `_relayout_right`, no un tope aca.
        return self._params_wanted()

    def _params_wanted(self) -> int:
        panel = self.current_params()
        if panel is None:
            return self.params_stack.sizeHint().height()
        return max(160, panel.natural_height())

    def _security_wanted(self) -> int:
        # Al contenido, no al scroll que lo envuelve: un `QScrollArea` no tiene
        # alto propio y contestaria un `sizeHint` generico.
        return self.security_panel.content_height()

    def _info_wanted(self) -> int:
        return self.info_panel.content_height() + 28

    def _refresh_security_summary(self, state: dict) -> None:
        """Cuantos objetivos estan protegidos, en la cabecera de la seccion.

        Es lo que hace que cerrarla no cueste informacion: plegada sigue
        diciendo el unico dato por el que se abre."""
        protegidos = len(protection.repo_protections(state))
        total = len(protection.TARGETS)
        self.security_section.set_summary(
            f'{protegidos} de {total} protegidos' if protegidos else 'sin seguros')

    def _on_env_changed(self, values: dict) -> None:
        for panel in self._params.values():
            panel.set_env(values)

    def _run(self, tab: SubTabButton, payload: dict) -> None:
        """Punto unico de 'Ejecutar': corre de verdad lo que ya tiene cuerpo
        (`func`); lo que todavia no lo tiene sigue simulado, para que el rail y
        el panel funcionen igual mientras se escribe (PLAN.md §10).

        Tener cuerpo es la unica condicion. Antes hacian falta dos —cuerpo y una
        entrada en `ADAPTERS`— y ese diccionario terminaba siendo una compuerta:
        veinte capacidades escritas y probadas se simulaban porque les faltaba
        una linea ahi (docs/contrato-de-nombres.md §1). Los kwargs los arma
        ahora la propia capacidad desde su declaracion."""
        console = self._consoles.get(tab)
        if console is None:
            return

        capability = registry.get_capability(payload['capability_id'])
        if capability is None:
            self._run_stub(console, payload)
            return

        # El seguro va aca y no en el panel de parametros porque este es el
        # unico punto por el que pasan LAS DOS formas de ejecutar: el boton
        # Ejecutar y el boton de correr del rail (`quick_run`). Ponerlo en el
        # panel dejaria el segundo camino sin red.
        if not self._guard_ok(capability, payload, console):
            return

        # Una compuesta concurrente no corre nada por si misma: reparte sus
        # pasos, que son capacidades, una por pestana (docs/launchers.md 2.5).
        if capability.concurrent:
            self._run_concurrent(tab, capability, payload)
            return

        if capability.func is None:
            self._run_stub(console, payload)
            return

        valores = self._fanout_values(capability, payload)
        if valores:
            self._run_fanout(tab, capability, payload, valores)
        else:
            self._run_real(tab, console, capability, capability.kwargs_from(payload))

    # --- seguro por tipo de objetivo ----------------------------------
    def _guard_ok(self, capability: Capability, payload: dict,
                  console: ConsoleView) -> bool:
        """Deja pasar, avisa, o bloquea — segun `core/protection.decide`.

        Lo que decide no es "es destructivo" sino "que rompe, con ESTOS
        parametros, y esta protegido en ESTE repo": un simulacro de
        `clean_artifacts` no pregunta nada, `teardown_db` contra `local` no
        decide lo mismo que contra `remoto`, y un objetivo protegido no abre una
        puerta para saltarse el seguro — la cierra.
        """
        decision, targets = protection.decide(self.security_panel.state(),
                                              capability.id, payload)
        if decision == protection.Decision.ALLOW:
            return True

        if decision == protection.Decision.BLOCK:
            BlockedDialog(self.project, capability.name, targets, self).exec()
            cuales = ', '.join(t.label for t in targets)
            console.append_log(
                f'Bloqueado: {capability.name} toca {cuales} y este repo lo '
                f'tiene protegido. El seguro se quita en Configuracion, '
                f'seccion Seguridad.', 'error')
            return False

        dialog = ReminderDialog(self.project, capability.name, targets, self)
        if dialog.exec() == ReminderDialog.DialogCode.Accepted:
            return True
        console.append_log(
            f'Cancelado: {capability.name} no llego a correr sobre '
            f'{self.project.name}.', 'warn')
        return False

    # --- reparto en pestanas ------------------------------------------
    def _fanout_values(self, capability: Capability, payload: dict) -> list[str]:
        """Los valores del eje que se reparte en pestanas, si lo hay.

        Solo para lo que corre en vivo: un eje `many` de una capacidad que
        termina (`build_vite`) se recorre en un bucle dentro de su propia
        consola, porque ver los builds en fila es lo correcto. Tres dev servers
        en una sola consola, no (docs/launchers.md 2.1).
        """
        if capability.kind != 'live' or not capability.fanout:
            return []
        return list((payload.get('variants') or {}).get(capability.fanout) or [])

    def _run_fanout(self, tab: SubTabButton, capability: Capability,
                    payload: dict, valores: list[str]) -> None:
        """Una pestana por valor marcado, cada una con su proceso vivo.

        El primero se queda en la pestana desde la que se apreto Ejecutar (solo
        cambia de nombre): asi el caso normal —un repo con una sola SPA— se ve
        exactamente igual que antes, sin una pestana de mas.
        """
        def _para(valor: str) -> dict:
            variantes = dict(payload.get('variants') or {})
            variantes[capability.fanout] = [valor]
            return {**payload, 'variants': variantes}

        primero, resto = valores[0], valores[1:]
        self._retitle(tab, f'{capability.name} {primero}')
        if resto:
            self._consoles[tab].append_log(
                f'{len(valores)} apps marcadas: una pestaña por cada una '
                f'({", ".join(valores)}).', 'info')
        self._run_real(tab, self._consoles[tab], capability,
                       capability.kwargs_from(_para(primero)))

        for valor in resto:
            otro, vista = self._open(capability, valor)
            self._run_real(otro, vista.console, capability,
                           capability.kwargs_from(_para(valor)))
        self._activate(tab)

    def _run_concurrent(self, tab: SubTabButton, capability: Capability,
                        payload: dict) -> None:
        """Compuesta concurrente: lanza cada paso en su propia pestana.

        No hay `func` que llamar. Sus pasos son capacidades con boton propio, y
        cada una arranca con los parametros que ya tiene guardados para este
        repo — es exactamente lo que hace el boton de correr del rail, asi que
        se reusa `quick_run` en vez de rearmar un payload a mano.

        El orden de la lista es el de despacho y el unico que importa es que el
        backend salga primero: los demas esperan su endpoint desde adentro
        (`launchers.backend_url(wait=...)`), no por un `sleep` de la interfaz.
        """
        console = self._consoles[tab]
        console.append_log(f'{capability.name}: cada paso va a su propia pestaña.', 'info')
        lanzados = []
        for step_id in payload.get('steps') or []:
            sub_cap = registry.get_capability(step_id)
            if sub_cap is None:
                console.append_log(f'paso desconocido: {step_id}', 'warn')
                continue
            console.append_log(f'→ {sub_cap.name}', 'info')
            self.quick_run(sub_cap)
            lanzados.append(sub_cap.name)
        self._activate(tab)
        if lanzados:
            console.append_log(f'Lanzados: {", ".join(lanzados)}.', 'ok')
        else:
            console.append_log('Ningún paso marcado.', 'warn')

    def _run_real(self, tab: SubTabButton, console: ConsoleView,
                  capability: Capability, kwargs: dict, track: bool = True) -> None:
        """`track=False` para lo que corre *dentro* de una pestana ajena — el ✕
        que apaga un emulador huerfano no debe pasar por dueno de la pestana:
        si lo hiciera, cerrarla detendria el apagado y no el emulador que esa
        pestana lanzo."""
        console.append_log("─" * 46, "info")
        panel = self._params.get(tab)
        if panel is not None:
            panel.run_btn.setEnabled(False)
            if panel.dry_btn is not None:
                panel.dry_btn.setEnabled(False)

        runner = TaskRunner(capability.id, self.project, capability.func, kwargs)
        if track:
            self._busy[tab] = runner
        runner.logged.connect(console.append_log)
        # Lo que la tarea publica con `ctx.serve()`: la barra con la URL y, si
        # la capacidad declara `view='web'`, el navegador de esta misma pestana.
        view = self._views.get(tab)
        if view is not None:
            runner.serve_requested.connect(view.set_endpoint)
        # La bitacora todavia no existe (`core/store.py`, PLAN.md §8): hasta que
        # exista, una nota no se pierde — se deja marcada en la consola.
        runner.noted.connect(lambda entry: console.append_log(f'✱ {entry}', 'ok'))
        runner.ask_requested.connect(
            lambda q, danger, secret, expect: self._answer_task(runner, q, danger, secret, expect)
        )

        def _on_done(ok: bool) -> None:
            console.append_log("Hecho" if ok else "Terminó con errores", "ok" if ok else "error")
            # El proceso murio: la URL deja de ofrecerse como viva y la pestana
            # vuelve a la consola, que es donde esta el motivo.
            if view is not None:
                view.endpoint_down()
            self._runners.discard(runner)
            if self._busy.get(tab) is runner:
                self._busy.pop(tab, None)
            if panel is not None:
                panel.refresh_run_state()
            if capability.is_machine_wide:
                # Instalar una imagen, crear un AVD o apagar un emulador cambia
                # justo lo que los paneles de este grupo listan. Se olvida lo
                # cacheado y se releen: si no, el AVD recien creado no aparece
                # hasta reabrir la pestana.
                forget_machine_cache()
                for otro in self._params.values():
                    if otro.capability.group == capability.group:
                        otro.refresh_machine()
                # Instalar un SDK cambia el entorno de la maquina: los
                # indicadores de la barra tienen que reflejarlo ya, no al
                # proximo arranque.
                self.machine_changed.emit()

        runner.finished_ok.connect(_on_done)
        self._runners.add(runner)  # referencia viva mientras el hilo corre
        runner.start()

    def _answer_task(self, runner: TaskRunner, question: str, danger: bool,
                     secret: bool, expect: str) -> None:
        """Contesta una pregunta de la tarea. Corre en el hilo de la interfaz.

        Tres dialogos, elegidos por lo que la tarea espera de vuelta y no por
        como se ve la pregunta:

        - `expect` — hay que escribir un texto exacto (borrar una base, pisar
          una carpeta). Campo de texto: la friccion es el punto.
        - `secret` — un dato que no se debe ver mientras se escribe.
        - el resto — si/no, con el boton peligroso sin ser el predeterminado,
          para que un Enter de mas no descarte nada.

        Siempre llama a `provide_answer`, tambien cuando se cierra el dialogo
        con la X: sin eso la tarea se queda esperando una respuesta que no
        llega. Una respuesta vacia es un "no" para `confirm`.
        """
        if expect:
            answer, ok = QInputDialog.getText(
                self, 'Confirmar', question, QLineEdit.EchoMode.Normal)
            runner.provide_answer(answer if ok else '')
            return

        if secret:
            answer, ok = QInputDialog.getText(
                self, 'Dato requerido', question, QLineEdit.EchoMode.Password)
            runner.provide_answer(answer if ok else '')
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
        box.setWindowTitle('Confirmar' if danger else 'Pregunta')
        box.setText(question)
        box.addButton('Sí', QMessageBox.ButtonRole.YesRole)
        no = box.addButton('No', QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(no)
        box.exec()
        runner.provide_answer('no' if box.clickedButton() is no else 'si')

    def _run_stub(self, console: ConsoleView, payload: dict) -> None:
        """Ejecucion simulada: reporta exactamente lo que correria (stub, PLAN.md §10)."""
        console.append_log("─" * 46, "info")

        variants = {k: v for k, v in payload['variants'].items() if v}
        for name, values in variants.items():
            console.append_log(f"{name}: {', '.join(values)}", "info")
        for name, value in payload['options'].items():
            console.append_log(f"{name}: {value}", "info")

        combos = 1
        for values in variants.values():
            combos *= max(1, len(values))
        steps = payload['steps']
        console.append_log(f"{len(steps)} paso(s) × {combos} variante(s)", "info")

        for step_id in steps:
            for _ in range(combos):
                pass
            console.append_log(f"paso «{step_id}» — no implementado (stub)", "warn")

        if payload['missing_env']:
            console.append_log(
                f"faltan claves: {', '.join(payload['missing_env'])}", "error"
            )
        else:
            console.append_log("Simulación completada", "ok")
