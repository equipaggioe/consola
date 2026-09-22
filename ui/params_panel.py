from __future__ import annotations
from dataclasses import replace

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QScrollArea, QFrame, QButtonGroup, QLineEdit, QPlainTextEdit, QComboBox,
    QCompleter, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QIntValidator

from ui.theme import Colors, Fonts
from ui.palettes import Palette
from core import envfile
from core.catalog import for_project, queried_values
from core.registry import Capability, AxisDef, Step, registry
from core.projects import Project
from core.settings import relevant_keys_for, required_keys_for
from ui import params_store, palettes


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )


class AxesLoader(QThread):
    """Lee en segundo plano los catalogos que pide una capacidad.

    Preguntarle al SDK que dispositivos y que system images existen tarda de
    segundos a un minuto la primera vez (despues queda cacheado en
    `core/cache.py`). Hacerlo en el hilo de la interfaz congelaria la ventana
    cada vez que se abre la pestana del emulador, asi que el panel se dibuja
    con las listas vacias y se completa solo cuando esto termina.

    Lo mismo vale, y mas todavia, para el VPS del repo: preguntarle que
    servicios tiene es una vuelta de SSH contra una maquina que puede estar
    apagada. Por eso el loader recibe la config del proyecto — es lo que dice a
    que VPS preguntarle — y no solo la capacidad.
    """
    ready = Signal(dict)

    def __init__(self, capability: Capability, config, refresh: bool = False, parent=None):
        super().__init__(parent)
        self._capability = capability
        self._config = config
        self._refresh = refresh

    def run(self) -> None:
        resuelto = {}
        for axis in self._capability.axes:
            if axis.is_queried:
                resuelto[axis.name] = queried_values(axis.source, refresh=self._refresh,
                                                     config=self._config)
        if self._capability.live_state:
            resuelto[_LIVE] = queried_values(self._capability.live_state, config=self._config)
        self.ready.emit(resuelto)


# Clave con la que viaja el inventario de "lo que esta corriendo" dentro del
# resultado del loader. No es un eje: no se elige, se mira y se apaga.
_LIVE = '@live'

# Ancho de la etiqueta de cada caracteristica de un eje `pick` con `facets`.
# Fijo y compartido para que las listas queden alineadas en columna: tres combos
# empezando cada uno donde termina su palabra se leen como tres controles
# sueltos y no como las tres partes de una misma eleccion.
_FACET_LABEL_WIDTH = 86

# Ancho minimo de una lista cerrada, en caracteres. No es el ancho real: es lo
# unico que el combo exige, para que despues se estire con la fila en vez de
# empujarla (`_pick_combo`).
_COMBO_MIN_CHARS = 8

# Tope de lo que puede ensancharse una lista desplegada. Sin el, el catalogo de
# system images abriria un desplegable mas ancho que la ventana.
_POPUP_MAX_WIDTH = 460


class ParamsPanel(QWidget):
    """Parametros de UNA ejecucion: variantes, pasos y opciones.

    Vive dentro de la pestana de la accion, asi que su estado sobrevive a
    cambiar de pestana y volver — y desde ahi se puede volver a correr.
    """
    execute_requested = Signal(dict)
    params_changed = Signal()   # lo guardado cambio: se revisa que puede correr de una
    stop_requested = Signal(str)  # apagar algo que esta corriendo (un serial de emulador)
    clear_requested = Signal()    # Limpiar del pie: vaciar el log de la pestana

    def __init__(self, capability: Capability, project: Project, env_panel, parent=None):
        super().__init__(parent)
        # Los ejes descubiertos se resuelven contra ESTE repo, no contra el
        # catalogo: la lista de apps sale de mirar las carpetas (ADR-0006).
        # Copia propia de los ejes: los descubiertos y los de maquina se
        # rellenan sobre esta capacidad, y el catalogo global no se toca.
        base = for_project(capability, project.path)
        self.capability = replace(base, axes=[replace(a) for a in base.axes])
        self.project = project
        self.pal = palettes.get(project.theme)
        self.env_panel = env_panel
        # Sobre la copia resuelta para ESTE repo, no sobre la del catalogo: es
        # la que ya se quedo sin los pasos que aca no existen (las migraciones
        # en un repo que no las lleva).
        self.steps: list[Step] = registry.resolve_steps(self.capability)
        self._env: dict[str, str] = {}

        self._checks: dict[str, dict[str, QCheckBox]] = {}   # axis -> value -> check
        self._options: dict[str, dict[str, QCheckBox]] = {}  # axis -> value -> check (exclusivo)
        self._fields: dict[str, QLineEdit | QPlainTextEdit] = {}  # axis -> valor escrito
        self._picks: dict[str, QComboBox] = {}   # axis -> lista larga con busqueda
        # axis -> caracteristica -> su lista corta. Es el mismo eje `pick` que
        # arriba, dibujado en varias listas que se recortan entre si
        # (`core/registry.py::Facet`); su valor sigue siendo el id entero, asi
        # que viaja en el mismo balde `picks` del payload.
        self._facets: dict[str, dict[str, QComboBox]] = {}
        self._multi_layouts: dict[str, QVBoxLayout] = {}  # axis -> donde van sus casillas
        self._option_layouts: dict[str, QVBoxLayout] = {}  # axis -> donde van sus excluyentes
        self._empty_notes: dict[str, QLabel] = {}  # axis -> rotulo de "no hay ninguno aca"
        self._loader: AxesLoader | None = None
        self._loading = any(a.is_queried for a in self.capability.axes)
        self._option_groups: dict[str, QButtonGroup] = {}  # axis -> su grupo excluyente
                               # vivo. Es dict y no lista porque un eje consultado se
                               # rellena de nuevo cada vez que se muestra la pestana, y
                               # hay que soltar el grupo que reemplaza.
        self._step_checks: dict[str, QCheckBox] = {}
        self._restoring = True   # mientras se arma, ningun cambio se guarda
        # Sin esto, un QWidget derivado ignora el fondo de su propia hoja y
        # deja ver el gris de la hoja global (`ui/theme.py`): el cuerpo de la
        # seccion no se teñia del color del repo.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._body_widget = self._build_body()
        # El pie con Ejecutar / Simulacro no vive dentro del panel: `TabPanel`
        # lo saca a una barra fija al fondo de la columna, para que el boton no
        # se pliegue con la seccion de parametros ni haya que scrollear hasta
        # el. Se construye igual aca (toda la logica de bloqueos es de esta
        # clase) y el contenedor lo reparenta.
        self.footer = self._build_footer()
        self._restyle()

        root.addWidget(self._body_widget, 1)

        # Lo elegido la ultima vez para este boton EN ESTE repo manda sobre
        # los valores por defecto; sin nada guardado, quedan los de arriba.
        self.apply_state(params_store.load(self.project.path, self.capability.id))
        self._restoring = False
        self._refresh_summary()
        if any(a.is_queried for a in self.capability.axes) or self.capability.live_state:
            self._load_machine()

    # --- catalogos consultados ----------------------------------------
    def _load_machine(self, refresh: bool = False) -> None:
        """Pide los catalogos del SDK y del VPS sin bloquear la ventana."""
        if self._loader is not None and self._loader.isRunning():
            return
        self._loading = any(a.is_queried for a in self.capability.axes)
        self._refresh_summary()
        self._loader = AxesLoader(self.capability, envfile.Config.for_project(self.project.path),
                                  refresh, self)
        self._loader.ready.connect(self._on_machine_ready)
        self._loader.start()

    def _on_machine_ready(self, resuelto: dict) -> None:
        """Llena las listas que dependian de la consulta y repone lo elegido."""
        guardado = params_store.load(self.project.path, self.capability.id)
        self._restoring = True
        try:
            for axis in self.capability.axes:
                if axis.name not in resuelto:
                    continue
                axis.values, axis.labels = resuelto[axis.name]
                if axis.name in self._facets:
                    self._fill_facets(axis)
                elif axis.name in self._picks:
                    self._fill_pick(axis)
                elif axis.name in self._multi_layouts:
                    self._fill_multi(axis)
                elif axis.name in self._option_layouts:
                    self._fill_options(axis)
            self._fill_live(resuelto.get(_LIVE, ([], {})))
        finally:
            self._restoring = False
        self._loading = False
        self.apply_state(guardado)
        self._refresh_summary()

    def refresh_machine(self) -> None:
        """Vuelve a preguntar salteando la cache.

        Es el camino forzado: lo usa el boton Recargar de Configuracion (que
        ademas de releer `config.env` puede haber cambiado A QUE VPS se
        pregunta) y el final de una tarea que acaba de tocar la maquina.
        """
        self._load_machine(refresh=True)

    def reload_catalogs(self) -> None:
        """Releer lo consultado al mostrar la pestana.

        Abrir la pestana es el momento en que se mira la lista, asi que es
        cuando tiene que estar al dia — pedir ademas un clic en un boton de
        recargar es pedir dos veces lo mismo. Respeta la cache a proposito:
        lo que caduca en un minuto (los AVD, los servicios del VPS) se vuelve a
        preguntar de verdad, y los dos catalogos grandes del SDK —que solo
        cambian cuando se actualiza el SDK— no se releen en cada clic.
        """
        if any(a.is_queried for a in self.capability.axes) or self.capability.live_state:
            self._load_machine()

    # --- construccion -------------------------------------------------
    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll   # lo repinta `_restyle`

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Lo que ya esta corriendo va arriba de todo: es lo primero que hay
        # que saber antes de elegir nada (¿hace falta lanzar otro?), y es desde
        # donde se apaga un emulador huerfano.
        self._live_box = self._build_live()
        lay.addWidget(self._live_box)

        picks = self.capability.pick_axes
        if picks:
            lay.addWidget(self._build_picks(picks))

        fields = self.capability.field_axes
        if fields:
            lay.addWidget(self._build_fields(fields))

        for axis in self.capability.multi_axes:
            lay.addWidget(self._build_multi_axis(axis))

        if len(self.steps) > 1:
            lay.addWidget(self._build_steps())

        # Un eje de un solo valor tampoco se elige, pero se muestra igual:
        # marcado y deshabilitado, para que se vea CUAL es (que app móvil, que
        # target) sin dejar quitarlo. `_build_options` lo dibuja asi.
        #
        # Un eje CONSULTADO entra aunque este vacio: cuando se arma el panel
        # todavia no se le pregunto a nadie, y descartarlo aca lo dejaba sin
        # lugar donde aparecer cuando la respuesta llegaba.
        singles = [a for a in self.capability.single_axes if a.values or a.is_queried]
        if singles:
            lay.addWidget(self._build_options(singles))

        self._content = content
        scroll.setWidget(content)
        return scroll

    def _build_picks(self, axes: list[AxisDef]) -> QWidget:
        """Listas largas y cerradas: se escribe para filtrar y se elige.

        Es la cuarta forma del panel, y existe por los catalogos del SDK: cien
        dispositivos y varios cientos de system images no entran en casillas ni
        en un segmentado, pero tampoco son texto libre — los valores validos son
        exactamente esos. El valor guardado es el id (`pixel_4`,
        `system-images;android-36;google_apis;x86_64`) y lo que se lee es su
        etiqueta.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)

        for axis in axes:
            if axis.facets:
                lay.addWidget(self._build_facets(axis))
                continue
            row = QVBoxLayout()
            row.setSpacing(4)
            row.addWidget(self._pick_title(axis.display))
            combo = self._pick_combo(buscable=True)
            combo.currentIndexChanged.connect(self._refresh_summary)
            self._picks[axis.name] = combo
            self._fill_pick(axis)
            row.addWidget(combo)
            lay.addLayout(row)
        return box

    def _pick_title(self, texto: str) -> QLabel:
        label = QLabel(texto)
        # Con `wordWrap` el rotulo pide de minimo su palabra mas larga y no la
        # frase entera: "Maquina virtual (instaladas)" exigia 364px y era el
        # rotulo —no la lista— lo que no dejaba angostar la columna.
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;"
        )
        return label

    def _pick_combo(self, *, buscable: bool) -> QComboBox:
        """La lista cerrada del panel.

        `buscable` la hace editable, y editable es solo para poder escribir y
        filtrar: en un catalogo de cien dispositivos es la unica forma de
        llegar, y en una lista de seis variantes seria un cursor que invita a
        escribir algo que no se puede escribir.
        """
        combo = QComboBox()
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumHeight(30)
        combo.setMaxVisibleItems(18)
        # El ancho lo manda la columna, no el item mas largo. Por defecto un
        # QComboBox pide de minimo lo que mide su entrada mas larga —y aca las
        # hay de 50 caracteres ("Automotive (1408p landscape) with Google
        # Play")—, asi que el panel entero no podia angostarse por debajo de
        # eso y aparecian barras de desplazamiento en una columna que ya estaba
        # apretada. Con esto el combo se conforma con `_COMBO_MIN_CHARS` y
        # ocupa lo que la fila le de; lo largo se lee al desplegar, donde la
        # lista se ensancha sola (`_fit_popup`).
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(_COMBO_MIN_CHARS)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if buscable:
            combo.setEditable(True)
            completer = QCompleter(combo.model(), combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.setCompleter(completer)
        combo.setStyleSheet(self._combo_style())
        return combo

    def _scroll_style(self) -> str:
        """El scroll no tiene fondo propio: deja ver el del panel.

        El canal de la barra si lo necesita. Cae bajo el mismo
        `QScrollArea > QWidget > QWidget` que deja transparente al viewport
        —la barra es hija del viewport—, y transparente lo pintaba el gris de
        la paleta de Qt, no el fondo del panel: un filete gris al borde de una
        columna teñida. Se le da el color a mano y en esta misma hoja, que es
        la mas cercana y la que manda.
        """
        return (
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {self.pal.panel}; width: 8px; }}")

    def _combo_style(self) -> str:
        return f"""
            QComboBox {{
                background: {self.pal.surface_alt}; border: 1px solid {self.pal.border};
                border-radius: 5px; padding: 0 8px;
                color: {Colors.TEXT}; font-size: {Fonts.SIZE_SM}px;
            }}
            QComboBox:focus {{ border: 1px solid {self.pal.accent}; }}
            QComboBox QAbstractItemView {{
                background: {self.pal.surface_alt}; color: {Colors.TEXT};
                selection-background-color: {self.pal.accent};
                border: 1px solid {self.pal.border};
            }}
        """

    def _build_facets(self, axis: AxisDef) -> QWidget:
        """Un eje `pick` dibujado por caracteristica: una lista corta por cada
        parte del valor, y todas se recortan entre si.

        El catalogo de system images son varios cientos de paquetes que en el
        fondo son tres preguntas —que version de Android, que variante, que
        arquitectura— ya permutadas. En una sola lista hay que leer trescientas
        etiquetas casi iguales para encontrar la que cambia en un solo campo; y
        peor, no se ve que existe: que no haya Wear OS para la 36 solo se
        descubre no encontrandolo.

        Aca cada lista ofrece *solo lo que existe dado lo demas elegido*
        (`AxisDef.facet_values`), y cambiar una recompone las otras
        (`AxisDef.resolve_facets`). Lo que se guarda no cambia: sigue siendo el
        paquete entero que entiende sdkmanager.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._pick_title(axis.display))

        self._facets[axis.name] = {}
        for facet in axis.facets:
            fila = QHBoxLayout()
            fila.setSpacing(8)
            etiqueta = QLabel(facet.label)
            etiqueta.setFixedWidth(_FACET_LABEL_WIDTH)
            etiqueta.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )
            combo = self._pick_combo(buscable=False)
            combo.currentIndexChanged.connect(
                lambda _i, a=axis: self._on_facet_changed(a))
            self._facets[axis.name][facet.name] = combo
            fila.addWidget(etiqueta)
            fila.addWidget(combo, 1)
            lay.addLayout(fila)
        self._fill_facets(axis)
        return box

    def _on_facet_changed(self, axis: AxisDef) -> None:
        self._fill_facets(axis)
        self._refresh_summary()

    def _fill_facets(self, axis: AxisDef) -> None:
        """(Re)carga las listas de un eje por caracteristica.

        Se rehacen todas y no solo las de abajo: cuesta lo mismo y evita tener
        que llevar la cuenta de cual cambio. Lo que decide que se mueve y que
        no es la cascada (`AxisDef.resolve_facets`), no quien disparo.
        """
        combos = self._facets.get(axis.name) or {}
        if not combos:
            return
        actual = {nombre: (c.currentData() or '') for nombre, c in combos.items()}
        resuelto = axis.resolve_facets(actual)
        for facet in axis.facets:
            combo = combos[facet.name]
            combo.blockSignals(True)
            combo.clear()
            opciones = axis.facet_values(facet, resuelto)
            for value in opciones:
                combo.addItem(axis.text_of(value), value)
            if not opciones:
                combo.addItem('leyendo el catálogo…' if self._loading
                              else f'no hay ninguna {axis.query_place}', '')
            indice = combo.findData(resuelto.get(facet.name, ''))
            combo.setCurrentIndex(max(indice, 0))
            combo.blockSignals(False)
            self._fit_popup(combo)

    def _fit_popup(self, combo: QComboBox) -> None:
        """La lista desplegada se ensancha a lo que mide su entrada mas larga.

        Es la contraparte de `_pick_combo`: el control cerrado se angosta con
        la columna, y lo que se recorta ahi se recupera al abrirlo, que es
        cuando de verdad hay que comparar entradas. Sin esto, angostar el
        combo angostaba tambien el desplegable y las etiquetas quedaban
        cortadas justo donde se estaba eligiendo.
        """
        metrics = combo.fontMetrics()
        ancho = max((metrics.horizontalAdvance(combo.itemText(i))
                     for i in range(combo.count())), default=0)
        combo.view().setMinimumWidth(min(ancho + 28, _POPUP_MAX_WIDTH))

    def _fill_pick(self, axis: AxisDef) -> None:
        """(Re)carga las opciones de una lista larga, conservando lo elegido."""
        combo = self._picks.get(axis.name)
        if combo is None:
            return
        anterior = self.pick_value(axis.name)
        combo.blockSignals(True)
        combo.clear()
        if axis.allow_empty:
            # Primera entrada y valor vacio: "no elijo, que decida la funcion".
            # No es un valor mas del catalogo, asi que se pone aca y no en
            # `values` — el catalogo de la maquina lo pisa en cada refresco.
            combo.addItem(axis.text_of('') or 'automático', '')
        for value in axis.values:
            combo.addItem(axis.text_of(value), value)
        if not axis.values:
            combo.lineEdit().setPlaceholderText(
                'leyendo el catálogo…' if self._loading else f'no hay ninguno {axis.query_place}')
        indice = combo.findData(anterior)
        combo.setCurrentIndex(indice if indice >= 0 else 0)
        combo.blockSignals(False)
        self._fit_popup(combo)

    def _fill_multi(self, axis: AxisDef) -> None:
        """(Re)crea las casillas de un eje que se llenó desde la máquina."""
        lay = self._multi_layouts.get(axis.name)
        if lay is None:
            return
        for check in self._checks.get(axis.name, {}).values():
            lay.removeWidget(check)
            check.deleteLater()
        self._checks[axis.name] = {}
        for value in axis.values:
            check = QCheckBox(axis.text_of(value))
            check.setChecked(axis.starts_checked(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._checks[axis.name][value] = check
            lay.addWidget(check)

    def _build_live(self) -> QWidget:
        """Cabecera con lo que esta corriendo ahora, y su ✕ para apagarlo."""
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        lay.addWidget(SectionLabel('Corriendo ahora'))
        self._live_layout = lay
        box.setVisible(False)
        return box

    def _fill_live(self, inventario: tuple) -> None:
        """Rehace la lista de lo vivo. Vacia, la cabecera entera desaparece."""
        valores, etiquetas = inventario
        while self._live_layout.count() > 1:
            item = self._live_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        for value in valores:
            fila = QWidget()
            fila.setStyleSheet("background: transparent;")
            flay = QHBoxLayout(fila)
            flay.setContentsMargins(0, 0, 0, 0)
            flay.setSpacing(6)

            texto = QLabel(f'● {etiquetas.get(value, value)}')
            texto.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;")
            apagar = QPushButton('✕')
            apagar.setFixedSize(20, 20)
            apagar.setCursor(Qt.CursorShape.PointingHandCursor)
            apagar.setToolTip('Apagar')
            apagar.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none;
                               color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px; }}
                QPushButton:hover {{ color: {Colors.ERROR}; }}
            """)
            apagar.clicked.connect(lambda _=False, v=value: self.stop_requested.emit(v))

            flay.addWidget(texto)
            flay.addStretch()
            flay.addWidget(apagar)
            self._live_layout.addWidget(fila)

        self._live_box.setVisible(bool(valores))

    def _build_fields(self, axes: list[AxisDef]) -> QWidget:
        """Ejes que se escriben: un directorio de instalacion, un API level.

        Van arriba de todo porque son los que condicionan al resto: de nada
        sirve elegir componentes si el SDK va a caer en otro lado.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)

        for axis in axes:
            row = QVBoxLayout()
            row.setSpacing(4)
            label = QLabel(axis.display)
            label.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            # `values[0]` es el valor por defecto, y se escribe en el campo en
            # vez de dejarlo de marca de agua: asi se ve que se va a usar.
            default = axis.values[0] if axis.values else ''
            if axis.multiline:
                field = QPlainTextEdit(default)
                field.setFixedHeight(88)   # ~4 renglones: la lista tipica entra entera
                field.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                field.textChanged.connect(self._refresh_summary)
            else:
                field = QLineEdit(default)
                field.setFixedHeight(30)
                if axis.cast == 'int':
                    # Un eje que declara `cast='int'` no acepta que se escriba
                    # otra cosa: es mas barato no dejar teclear la letra que
                    # explicar despues por que el puerto volvio a 8000.
                    field.setValidator(QIntValidator(0, 2_147_483_647, field))
                field.textChanged.connect(self._refresh_summary)
            # La marca de agua repite el default y nada mas: si el campo se
            # vacia, lo que se ve es lo que va a correr. Un texto que explique
            # que va en el campo ocuparia este mismo lugar y se leeria como un
            # valor — eso va en la etiqueta, no aca.
            field.setPlaceholderText(default)
            field.setStyleSheet(self._field_style(axis.multiline))
            self._fields[axis.name] = field
            row.addWidget(field)
            lay.addLayout(row)
        return box

    def _build_multi_axis(self, axis: AxisDef) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)

        lay.addWidget(SectionLabel(axis.display))

        self._multi_layouts[axis.name] = lay
        self._checks[axis.name] = {}
        for value in axis.values:
            check = QCheckBox(axis.text_of(value))
            check.setChecked(axis.starts_checked(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._checks[axis.name][value] = check
            lay.addWidget(check)
        return box

    def _build_steps(self) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        lay.addWidget(SectionLabel("Pasos"))

        for step in self.steps:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(6)

            check = QCheckBox(step.label)
            check.setChecked(step.default or not step.optional)
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._step_checks[step.id] = check

            row_lay.addWidget(check)
            row_lay.addStretch()
            lay.addWidget(row)
        return box

    def _build_options(self, axes: list[AxisDef]) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)
        lay.addWidget(SectionLabel("Opciones"))

        for axis in axes:
            row = QVBoxLayout()
            row.setSpacing(4)
            label = QLabel(axis.display)
            label.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            # Las casillas no se cuelgan de `row` sino de un contenedor propio,
            # porque un eje consultado se dibuja DOS veces: vacio mientras se
            # pregunta, y otra vez con los valores que llegaron. Sin este
            # contenedor no habria donde volver a ponerlas — que es exactamente
            # por lo que el eje de servicios del VPS no aparecia nunca.
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            hlay = QVBoxLayout(holder)
            hlay.setContentsMargins(0, 0, 0, 0)
            hlay.setSpacing(4)
            self._option_layouts[axis.name] = hlay
            self._fill_options(axis)
            row.addWidget(holder)
            lay.addLayout(row)
        return box

    def _fill_options(self, axis: AxisDef) -> None:
        """(Re)crea las casillas excluyentes de un eje. Sirve para los dos
        casos: dibujarlo la primera vez, y rehacerlo cuando el catalogo que lo
        llena termino de contestar."""
        lay = self._option_layouts.get(axis.name)
        if lay is None:
            return
        for check in self._options.get(axis.name, {}).values():
            lay.removeWidget(check)
            check.deleteLater()
        nota = self._empty_notes.pop(axis.name, None)
        if nota is not None:
            lay.removeWidget(nota)
            nota.deleteLater()
        # El grupo anterior se va con sus botones: un eje consultado se rellena
        # cada vez que se muestra la pestana, y dejarlos apilados es un grupo
        # muerto por clic.
        previo = self._option_groups.pop(axis.name, None)
        if previo is not None:
            previo.deleteLater()

        group = QButtonGroup(self)
        group.setExclusive(True)
        self._option_groups[axis.name] = group
        self._options[axis.name] = {}
        # Un eje con un solo valor excluyente no se elige: se muestra fijo.
        locked = len(axis.exclusive_values) <= 1 and not axis.combine
        for value in axis.values:
            # `text_of` y no el valor pelado: un eje excluyente tambien
            # puede tener un valor que no se lee (`0.0.0.0`, el `''` de
            # "todas las prioridades"). La etiqueta es de la misma clase
            # que la de una lista larga, y se declara en el mismo lugar.
            check = QCheckBox(axis.text_of(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            if value in axis.danger:
                check.setStyleSheet(f"QCheckBox {{ color: {Colors.ERROR}; }}")
            if value in axis.combine:
                # Toggle independiente: fuera del grupo, arranca apagado.
                check.setChecked(False)
            else:
                group.addButton(check)
                check.setChecked(value == axis.initial)
                if locked:
                    # Única opción: se muestra marcada y con el color de
                    # seleccionada, pero no se puede desmarcar — el grupo
                    # exclusivo ya impide soltar el único botón, y no hay
                    # otro al que saltar. Queda habilitada (no en gris)
                    # para que se lea como una elección viva, no muerta.
                    check.setChecked(True)
                    check.setToolTip("Única opción disponible")
            check.toggled.connect(self._refresh_summary)
            self._options[axis.name][value] = check
            lay.addWidget(check)

        if not axis.values:
            # El mismo texto que la marca de agua de una lista larga vacia: el
            # hueco tiene que decir por que esta vacio, no quedarse mudo.
            nota = QLabel('leyendo el catálogo…' if self._loading
                          else f'no hay ninguno {axis.query_place}')
            nota.setStyleSheet(f"background: transparent; color: {Colors.TEXT_MUTED}; "
                               f"font-size: {Fonts.SIZE_XS}px;")
            self._empty_notes[axis.name] = nota
            lay.addWidget(nota)

    def _field_style(self, multiline: bool) -> str:
        return f"""
            QLineEdit, QPlainTextEdit {{
                background: {self.pal.surface_alt}; border: 1px solid {self.pal.border};
                border-radius: 5px; padding: {'5px 8px' if multiline else '0 8px'};
                color: {Colors.TEXT}; font-size: {Fonts.SIZE_SM}px;
            }}
            QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {self.pal.accent}; }}
        """

    @property
    def _dry_run_axis(self) -> AxisDef | None:
        """El eje excluyente que ofrece un simulacro (`clean_artifacts`,
        `sync_common_files`, borrar emuladores). Su presencia es lo que hace
        aparecer el boton Simulacro."""
        return next((a for a in self.capability.single_axes
                     if 'simulacro' in a.values), None)

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        # A la izquierda, lejos de Ejecutar: vaciar el log no es correr nada.
        clear_btn = QPushButton("Limpiar")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFixedHeight(34)
        clear_btn.setToolTip("Vaciar el log de esta pestaña y cerrar sus túneles SSH")
        clear_btn.clicked.connect(self.clear_requested.emit)
        self.clear_btn = clear_btn
        lay.addWidget(clear_btn)
        lay.addStretch()

        self.dry_btn: QPushButton | None = None
        if self._dry_run_axis is not None:
            self.dry_btn = QPushButton("Simulacro")
            self.dry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.dry_btn.setFixedHeight(34)
            self.dry_btn.setToolTip("Corre sin tocar nada: solo muestra qué haría")
            self.dry_btn.clicked.connect(lambda: self._emit_execute(dry_run=True))
            lay.addWidget(self.dry_btn)

        self.run_btn = QPushButton("▶  Ejecutar")
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setFixedHeight(34)
        self.run_btn.clicked.connect(self._emit_execute)

        lay.addWidget(self.run_btn)
        self._restyle_run()
        return foot

    # --- estado --------------------------------------------------------
    def selection(self, axis_name: str) -> list[str]:
        return [v for v, c in self._checks.get(axis_name, {}).items() if c.isChecked()]

    def active_steps(self) -> list[Step]:
        # Con un solo paso obligatorio no se dibuja la seccion: sin casilla,
        # el paso esta activo por definicion.
        return [s for s in self.steps
                if s.id not in self._step_checks or self._step_checks[s.id].isChecked()]

    def option_value(self, axis_name: str) -> str:
        for value, check in self._options.get(axis_name, {}).items():
            if check.isChecked():
                return value
        return ''

    def option_values(self, axis_name: str) -> list[str]:
        return [v for v, c in self._options.get(axis_name, {}).items() if c.isChecked()]

    def _axis(self, axis_name: str) -> AxisDef | None:
        return next((a for a in self.capability.axes if a.name == axis_name), None)

    def _option_payload(self, axis_name: str):
        """Un eje con `combine` puede tener dos marcas a la vez (p. ej.
        `patch` + `build`): viaja como lista. El resto, como un solo valor."""
        axis = self._axis(axis_name)
        if axis and axis.combine:
            return self.option_values(axis_name)
        return self.option_value(axis_name)

    def pick_value(self, axis_name: str) -> str:
        """El id elegido en una lista larga (no su etiqueta).

        Un eje por caracteristica no guarda el id en ningun combo: lo arma el
        catalogo con lo marcado en cada lista, porque el id sigue siendo lo
        unico que la herramienta entiende (`AxisDef.value_for`).
        """
        combos = self._facets.get(axis_name)
        if combos is not None:
            axis = self._axis(axis_name)
            if axis is None:
                return ''
            return axis.value_for({n: (c.currentData() or '') for n, c in combos.items()})
        combo = self._picks.get(axis_name)
        if combo is None:
            return ''
        value = combo.currentData()
        return value if isinstance(value, str) else ''

    def _pick_names(self) -> list[str]:
        """Los ejes que guardan un id suelto, se dibujen como una lista o como
        varias: los dos casos viajan en el mismo balde `picks`."""
        return [*self._picks, *self._facets]

    def field_value(self, axis_name: str) -> str:
        """El texto escrito, sea el campo de una linea o la caja de varias.

        Los dos widgets guardan lo mismo — texto — pero no lo piden con el mismo
        metodo, y quien lee el payload no tiene por que saber cual se dibujo.
        """
        field = self._fields.get(axis_name)
        if field is None:
            return ''
        leer = getattr(field, 'toPlainText', None) or field.text
        return leer().strip()

    def state(self) -> dict:
        """Lo que hay marcado ahora mismo, en forma serializable."""
        return {
            'variants': {name: self.selection(name) for name in self._checks},
            'steps': [s.id for s in self.active_steps()],
            'options': {name: self._option_payload(name) for name in self._options},
            'fields': {name: self.field_value(name) for name in self._fields},
            'picks': {name: self.pick_value(name) for name in self._pick_names()},
        }

    def apply_state(self, state: dict | None) -> None:
        """Vuelve a marcar lo guardado. Tolera un catalogo que cambio: los
        valores que ya no existen se ignoran y los ejes nuevos se quedan con
        su valor por defecto."""
        if not state:
            return
        previous, self._restoring = self._restoring, True
        try:
            variants = state.get('variants') or {}
            for axis_name, checks in self._checks.items():
                saved = variants.get(axis_name)
                if saved is None:
                    continue
                for value, check in checks.items():
                    check.setChecked(value in saved)

            steps = state.get('steps')
            if steps is not None:
                for step_id, check in self._step_checks.items():
                    check.setChecked(step_id in steps)

            options = state.get('options') or {}
            for axis_name, checks in self._options.items():
                saved = options.get(axis_name)
                if saved is None:
                    continue
                marcados = set(saved) if isinstance(saved, list) else {saved}
                axis = self._axis(axis_name)
                combine = axis.combine if axis else set()
                for value, check in checks.items():
                    if not check.isEnabled():
                        continue   # eje fijo: su marca no se toca
                    if value in combine:
                        # Un guardado sin este valor = toggle desmarcado.
                        check.setChecked(value in marcados)
                    elif value in marcados:
                        check.setChecked(True)   # el grupo excluyente desmarca al resto

            picks = state.get('picks') or {}
            for axis_name, combo in self._picks.items():
                elegido = picks.get(axis_name)
                if not elegido:
                    continue
                indice = combo.findData(elegido)
                # Un valor que ya no existe (un AVD borrado, una imagen
                # desinstalada) no se fuerza: se queda el primero de la lista.
                if indice >= 0:
                    combo.setCurrentIndex(indice)

            # Un eje por caracteristica guarda el id entero igual que los de
            # arriba: para reponerlo hay que descomponerlo y dejar cada lista
            # en su parte. `resolve_facets` descarta sola las que ya no existen.
            for axis_name, combos in self._facets.items():
                elegido = picks.get(axis_name)
                axis = self._axis(axis_name)
                if not elegido or axis is None:
                    continue
                for nombre, parte in axis.facets_of(elegido).items():
                    combo = combos.get(nombre)
                    if combo is None:
                        continue
                    indice = combo.findData(parte)
                    if indice < 0:
                        combo.blockSignals(True)
                        combo.addItem(axis.text_of(parte), parte)
                        indice = combo.count() - 1
                        combo.blockSignals(False)
                    combo.setCurrentIndex(indice)
                self._fill_facets(axis)

            fields = state.get('fields') or {}
            for axis_name, field in self._fields.items():
                saved = fields.get(axis_name)
                # Una cadena vacia guardada es una eleccion valida (vuelve al
                # valor por defecto de la funcion); un eje nuevo no lo es.
                if saved is not None:
                    escribir = getattr(field, 'setPlainText', None) or field.setText
                    escribir(saved)
        finally:
            self._restoring = previous

    def _persist(self) -> None:
        if self._restoring:
            return
        params_store.save(self.project.path, self.capability.id, self.state())
        self.params_changed.emit()

    def payload(self) -> dict:
        return {
            'capability_id': self.capability.id,
            'project': self.project.name,
            'variants': {name: self.selection(name) for name in self._checks},
            'steps': [s.id for s in self.active_steps()],
            'options': {name: self._option_payload(name) for name in self._options},
            'fields': {name: self.field_value(name) for name in self._fields},
            'picks': {name: self.pick_value(name) for name in self._pick_names()},
            'missing_env': self._missing_keys(),
        }

    def set_env(self, values: dict[str, str]) -> None:
        """El panel de configuracion de abajo alimenta la validacion previa."""
        self._env = values
        self._refresh_summary()

    def set_palette(self, pal: Palette) -> None:
        """Cambio de color del repo: se repinta el panel entero, no solo el
        boton Ejecutar. Los campos y las listas se quedaron con la hoja de
        estilo que se les dicto al construirlos, asi que hay que volver a
        dictarsela una por una."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        # El panel es el CUERPO de la seccion «Parametros»: `panel`, un
        # escalon por debajo de la cabecera que lo rotula.
        # La barra de scroll se pinta aparte: su canal no es un fondo de hoja
        # de estilo sino el color de la paleta de Qt, y se quedaba gris dentro
        # de un panel teñido.
        self.setStyleSheet(f"ParamsPanel {{ background: {self.pal.panel}; }}")
        self._scroll.setStyleSheet(self._scroll_style())
        self.footer.setStyleSheet(
            f"background: {self.pal.surface}; border-top: 1px solid {self.pal.border};")
        for boton in (self.clear_btn, self.dry_btn):
            if boton is not None:
                boton.setStyleSheet(self._secondary_style())
        for campo in self._fields.values():
            campo.setStyleSheet(self._field_style(isinstance(campo, QPlainTextEdit)))
        combos = list(self._picks.values())
        combos += [c for facetas in self._facets.values() for c in facetas.values()]
        for combo in combos:
            combo.setStyleSheet(self._combo_style())
        self._restyle_run()

    def _secondary_style(self) -> str:
        """Limpiar y Simulacro: contorno, no relleno. El unico boton lleno del
        pie es Ejecutar."""
        return f"""
            QPushButton {{
                background: transparent; border: 1px solid {self.pal.border};
                color: {Colors.TEXT_DIM}; border-radius: 6px;
                padding: 0 16px; font-size: {Fonts.SIZE_SM}px;
            }}
            QPushButton:hover {{ background: {self.pal.surface_hover}; color: {Colors.TEXT}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; }}
        """

    def refresh_run_state(self) -> None:
        """Repone el boton Ejecutar segun los blockers actuales.

        Publico para quien deshabilito el boton desde afuera mientras corria
        de verdad (`ui/tab_panel.py::_run_real`) y necesita devolverselo al
        estado que le corresponde, no simplemente a habilitado.
        """
        self._refresh_summary()

    def natural_height(self) -> int:
        """Alto que necesita para mostrar todo su contenido sin scroll, para
        que el panel de `.env` se quede con el resto del espacio vertical."""
        return self._content.sizeHint().height() + 4

    def relevant_keys(self) -> set[str]:
        """Claves de `.env` que esta accion puede llegar a necesitar CON LO QUE
        ESTA MARCADO AHORA — para filtrar el panel de configuracion.

        Sigue a la seleccion, no al catalogo entero, y la sigue igual en las
        tres fuentes: el eje, sus `uses_env` y los pasos. Antes mezclaba las dos
        cosas —`all_keys` (todos los valores del eje) y `self.steps` (todos los
        pasos) contra unos `uses_env` que si miraban lo marcado—, y el resultado
        era un formulario que pedia datos que la corrida jamas iba a leer: la IP
        y la llave del VPS con `Crear base desde cero` en `local`, el directorio de
        despliegue con 'Subir al VPS' desmarcado.

        Es exactamente el conjunto de `_missing_keys`, con `relevant` en lugar
        de `required` — esa es la unica diferencia que debe haber entre los dos:
        lo que se muestra y lo que bloquea salen de la misma seleccion.
        """
        needed = set(relevant_keys_for(self.capability.id))
        for axis in self.capability.axes:
            elegidos = self.selection(axis.name) + self.option_values(axis.name)
            needed |= axis.keys_for(elegidos)
            for valor in elegidos:
                needed |= axis.uses_env.get(valor, set())
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(relevant_keys_for(step.id))
        return needed

    # --- interno --------------------------------------------------------

    def _missing_keys(self) -> list[str]:
        """Claves sin las que la accion no puede correr — de verdad, no solo
        sin texto en el campo.

        Antes miraba el texto crudo del campo: una clave con default fijo
        (`ROOT_USER='root'`) o dinamico (`VPS_USER` -> nombre del repo, ya
        resuelto por `Config.get`) quedaba en ambar aunque la funcion real
        jamas la fuera a extranar. Envolver `self._env` en un `Config` hace
        la misma pregunta que se hace en tiempo de ejecucion.
        """
        needed = set(required_keys_for(self.capability.id))
        for axis in self.capability.axes:
            needed |= axis.keys_for(self.selection(axis.name) + self.option_values(axis.name))
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(required_keys_for(step.id))
        cfg = envfile.Config(self._env, repo_name=envfile.repo_name_of(self.project.path))
        return sorted(k for k in needed if not cfg.get(k))

    def blockers(self) -> list[str]:
        """Publico para `quick_run`: por que no se puede correr sin abrir la
        pestana (`ui/tab_panel.py::quick_run` lo reporta en la consola)."""
        return self._blockers()

    def _blockers(self) -> list[str]:
        """Razones por las que 'Ejecutar' no puede correr."""
        reasons = []
        # Un eje descubierto sin valores no es "olvidaste elegir": es que el
        # repo no tiene eso. Se dice asi, y no se pide ademas que elija de una
        # lista vacia.
        if self._loading:
            return ["leyendo el catálogo…"]
        vacios = {a.name for a in self.capability.axes if a.is_discovered and not a.values}
        for axis in self.capability.axes:
            if axis.name not in vacios:
                continue
            donde = axis.query_place if axis.is_queried else 'en este repo'
            # Un eje opcional que ademas admite estar vacio (las dos listas de
            # "Liberar disco") no bloquea: que no haya AVD creados no impide
            # borrar una imagen.
            if axis.allow_empty:
                continue
            reasons.append(f"no hay {axis.display.lower()} {donde}")
        for axis in self.capability.field_axes:
            if axis.required and not self.field_value(axis.name).strip():
                reasons.append(f"escribe {axis.display.lower()}")
        for axis in self.capability.pick_axes:
            if axis.values and not axis.allow_empty and not self.pick_value(axis.name):
                reasons.append(f"elige {axis.display.lower()}")
        for axis in self.capability.multi_axes:
            if axis.name in vacios:
                continue
            if not axis.allow_empty and not self.selection(axis.name):
                reasons.append(f"selecciona al menos un valor en {axis.display.lower()}")
        if not self.active_steps():
            reasons.append("selecciona al menos un paso")
        missing = self._missing_keys()
        if missing:
            reasons.append(f"faltan claves de configuración: {', '.join(missing)}")
        return reasons

    def _refresh_summary(self, *_args) -> None:
        self._persist()
        blockers = self._blockers()
        self.run_btn.setEnabled(not blockers)
        self.run_btn.setToolTip(blockers[0].capitalize() if blockers else "")
        if self.dry_btn is not None:
            self.dry_btn.setEnabled(not blockers)
            self.dry_btn.setToolTip(
                blockers[0].capitalize() if blockers
                else "Corre sin tocar nada: solo muestra qué haría")
        self._restyle_run()

    def _restyle_run(self) -> None:
        enabled = self.run_btn.isEnabled()
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.pal.accent if enabled else self.pal.surface_alt};
                color: {self.pal.on_accent if enabled else Colors.TEXT_MUTED};
                border: none; border-radius: 6px;
                padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {self.pal.accent if enabled else self.pal.surface_alt}; }}
        """)

    def _emit_execute(self, _checked: bool = False, *, dry_run: bool = False) -> bool:
        if self._blockers():
            return False
        payload = self.payload()
        if dry_run:
            axis = self._dry_run_axis
            if axis is not None:
                # No toca lo guardado: solo fuerza el modo seguro en el payload
                # de ESTA corrida.
                payload['options'] = {**payload['options'], axis.name: 'simulacro'}
        self.execute_requested.emit(payload)
        return True

    def try_run(self) -> bool:
        """Ejecuta con los parametros actuales de la pestana — que al
        abrirse son los guardados para este boton en este repo, o los por
        defecto si nunca se tocaron. Lo usa el boton ▶ del buscador.
        Devuelve si corrio."""
        return self._emit_execute()
