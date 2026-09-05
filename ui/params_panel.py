from __future__ import annotations
from dataclasses import replace

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QScrollArea, QFrame, QButtonGroup, QLineEdit, QPlainTextEdit, QComboBox,
    QCompleter
)
from PySide6.QtCore import Qt, Signal, QThread

from ui.theme import Colors, Fonts
from core import envfile
from core.catalog import for_project, machine_values
from core.registry import Capability, AxisDef, Step, registry
from core.projects import Project
from core.settings import relevant_keys_for, required_keys_for
from ui import params_store


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )


class MachineAxesLoader(QThread):
    """Lee en segundo plano los catalogos de la maquina que pide una capacidad.

    Preguntarle al SDK que dispositivos y que system images existen tarda de
    segundos a un minuto la primera vez (despues queda cacheado en
    `core/cache.py`). Hacerlo en el hilo de la interfaz congelaria la ventana
    cada vez que se abre la pestana del emulador, asi que el panel se dibuja
    con las listas vacias y se completa solo cuando esto termina.
    """
    ready = Signal(dict)

    def __init__(self, capability: Capability, refresh: bool = False, parent=None):
        super().__init__(parent)
        self._capability = capability
        self._refresh = refresh

    def run(self) -> None:
        resuelto = {}
        for axis in self._capability.axes:
            if axis.is_from_machine:
                resuelto[axis.name] = machine_values(axis.source, refresh=self._refresh)
        if self._capability.live_state:
            resuelto[_LIVE] = machine_values(self._capability.live_state)
        self.ready.emit(resuelto)


# Clave con la que viaja el inventario de "lo que esta corriendo" dentro del
# resultado del loader. No es un eje: no se elige, se mira y se apaga.
_LIVE = '@live'


class ParamsPanel(QWidget):
    """Parametros de UNA ejecucion: variantes, pasos y opciones.

    Vive dentro de la pestana de la accion, asi que su estado sobrevive a
    cambiar de pestana y volver — y desde ahi se puede volver a correr.
    """
    execute_requested = Signal(dict)
    params_changed = Signal()   # lo guardado cambio: el rail revisa que puede correr
    stop_requested = Signal(str)  # apagar algo que esta corriendo (un serial de emulador)

    def __init__(self, capability: Capability, project: Project, env_panel, parent=None):
        super().__init__(parent)
        # Los ejes descubiertos se resuelven contra ESTE repo, no contra el
        # catalogo: la lista de apps sale de mirar las carpetas (PLAN.md 2.4).
        # Copia propia de los ejes: los descubiertos y los de maquina se
        # rellenan sobre esta capacidad, y el catalogo global no se toca.
        base = for_project(capability, project.path)
        self.capability = replace(base, axes=[replace(a) for a in base.axes])
        self.project = project
        self.accent = project.color
        self.env_panel = env_panel
        self.steps: list[Step] = registry.resolve_steps(capability)
        self._env: dict[str, str] = {}

        self._checks: dict[str, dict[str, QCheckBox]] = {}   # axis -> value -> check
        self._options: dict[str, dict[str, QCheckBox]] = {}  # axis -> value -> check (exclusivo)
        self._fields: dict[str, QLineEdit | QPlainTextEdit] = {}  # axis -> valor escrito
        self._picks: dict[str, QComboBox] = {}   # axis -> lista larga con busqueda
        self._multi_layouts: dict[str, QVBoxLayout] = {}  # axis -> donde van sus casillas
        self._loader: MachineAxesLoader | None = None
        self._loading = any(a.is_from_machine for a in self.capability.axes)
        self._option_groups: list[QButtonGroup] = []
        self._step_checks: dict[str, QCheckBox] = {}
        self._restoring = True   # mientras se arma, ningun cambio se guarda

        self.setStyleSheet(f"ParamsPanel {{ background: {Colors.SURFACE}; }}")

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

        root.addWidget(self._body_widget, 1)

        # Lo elegido la ultima vez para este boton EN ESTE repo manda sobre
        # los valores por defecto; sin nada guardado, quedan los de arriba.
        self.apply_state(params_store.load(self.project.path, self.capability.id))
        self._restoring = False
        self._refresh_summary()
        if self._loading or self.capability.live_state:
            self._load_machine()

    # --- catalogos de la maquina --------------------------------------
    def _load_machine(self, refresh: bool = False) -> None:
        """Pide los catalogos del SDK sin bloquear la ventana."""
        if self._loader is not None and self._loader.isRunning():
            return
        self._loading = any(a.is_from_machine for a in self.capability.axes)
        self._refresh_summary()
        self._loader = MachineAxesLoader(self.capability, refresh, self)
        self._loader.ready.connect(self._on_machine_ready)
        self._loader.start()

    def _on_machine_ready(self, resuelto: dict) -> None:
        """Llena las listas que dependian del SDK y repone lo que estaba elegido."""
        guardado = params_store.load(self.project.path, self.capability.id)
        self._restoring = True
        try:
            for axis in self.capability.axes:
                if axis.name not in resuelto:
                    continue
                axis.values, axis.labels = resuelto[axis.name]
                if axis.name in self._picks:
                    self._fill_pick(axis)
                elif axis.name in self._multi_layouts:
                    self._fill_multi(axis)
            self._fill_live(resuelto.get(_LIVE, ([], {})))
        finally:
            self._restoring = False
        self._loading = False
        self.apply_state(guardado)
        self._refresh_summary()

    def refresh_machine(self) -> None:
        """Vuelve a preguntarle al SDK, salteando la cache. Es el boton ↻."""
        self._load_machine(refresh=True)

    # --- construccion -------------------------------------------------
    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

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
        singles = [a for a in self.capability.single_axes if a.values]
        if singles:
            lay.addWidget(self._build_options(singles))

        # ↻ Catálogo va junto a los ejes que llena (los del SDK), no en el pie:
        # ahi solo va Ejecutar. Recargar/Guardar del .env se fueron a su propia
        # seccion (`ui/env_panel.py`).
        if any(a.is_from_machine for a in self.capability.axes) or self.capability.live_state:
            lay.addWidget(self._build_catalog_bar())

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
            row = QVBoxLayout()
            row.setSpacing(4)
            label = QLabel(axis.display)
            label.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            combo = QComboBox()
            combo.setEditable(True)          # editable solo para poder escribir y filtrar
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.setMinimumHeight(30)
            combo.setMaxVisibleItems(18)
            completer = QCompleter(combo.model(), combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.setCompleter(completer)
            combo.setStyleSheet(f"""
                QComboBox {{
                    background: {Colors.SURFACE_ALT}; border: 1px solid {Colors.BORDER};
                    border-radius: 5px; padding: 0 8px;
                    color: {Colors.TEXT}; font-size: {Fonts.SIZE_SM}px;
                }}
                QComboBox:focus {{ border: 1px solid {self.accent}; }}
                QComboBox QAbstractItemView {{
                    background: {Colors.SURFACE_ALT}; color: {Colors.TEXT};
                    selection-background-color: {self.accent};
                    border: 1px solid {Colors.BORDER};
                }}
            """)
            combo.currentIndexChanged.connect(self._refresh_summary)
            self._picks[axis.name] = combo
            self._fill_pick(axis)
            row.addWidget(combo)
            lay.addLayout(row)
        return box

    def _fill_pick(self, axis: AxisDef) -> None:
        """(Re)carga las opciones de una lista larga, conservando lo elegido."""
        combo = self._picks.get(axis.name)
        if combo is None:
            return
        anterior = self.pick_value(axis.name)
        combo.blockSignals(True)
        combo.clear()
        for value in axis.values:
            combo.addItem(axis.text_of(value), value)
        if not axis.values:
            combo.lineEdit().setPlaceholderText(
                'leyendo el catálogo del SDK…' if self._loading else 'no hay ninguno en esta máquina')
        indice = combo.findData(anterior)
        combo.setCurrentIndex(indice if indice >= 0 else 0)
        combo.blockSignals(False)

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
            check.setChecked(axis.checked_by_default)
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
                f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_SM}px;")
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
                f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            # `values[0]` es el valor por defecto, y se escribe en el campo en
            # vez de dejarlo de marca de agua: asi se ve que se va a usar.
            # `placeholder` es lo contrario: un ejemplo del formato para un
            # campo que arranca vacio a proposito (las rutas a copiar), y que
            # no debe prellenarse con algo que este repo quiza no tiene.
            default = axis.values[0] if axis.values else ''
            if axis.multiline:
                field = QPlainTextEdit(default)
                field.setFixedHeight(88)   # ~4 renglones: la lista tipica entra entera
                field.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                field.textChanged.connect(self._refresh_summary)
            else:
                field = QLineEdit(default)
                field.setFixedHeight(30)
                field.textChanged.connect(self._refresh_summary)
            field.setPlaceholderText(axis.placeholder or default)
            field.setStyleSheet(f"""
                QLineEdit, QPlainTextEdit {{
                    background: {Colors.SURFACE_ALT}; border: 1px solid {Colors.BORDER};
                    border-radius: 5px; padding: {'5px 8px' if axis.multiline else '0 8px'};
                    color: {Colors.TEXT}; font-size: {Fonts.SIZE_SM}px;
                }}
                QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {self.accent}; }}
            """)
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
            check.setChecked(axis.checked_by_default)
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
                f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            group = QButtonGroup(self)
            group.setExclusive(True)
            self._option_groups.append(group)
            self._options[axis.name] = {}
            # Un eje con un solo valor excluyente no se elige: se muestra fijo.
            locked = len(axis.exclusive_values) <= 1 and not axis.combine
            for value in axis.values:
                check = QCheckBox(value)
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
                        check.setChecked(True)
                        check.setEnabled(False)
                        check.setCursor(Qt.CursorShape.ArrowCursor)
                check.toggled.connect(self._refresh_summary)
                self._options[axis.name][value] = check
                row.addWidget(check)
            lay.addLayout(row)
        return box

    def _build_catalog_bar(self) -> QWidget:
        """El boton ↻ Catálogo: releer los catálogos del SDK salteando la caché
        (se cachea por semanas). Es el unico modo de enterarse de una API nueva
        sin reiniciar Consola."""
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        btn = QPushButton("↻ Catálogo")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(28)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_DIM}; border-radius: 5px;
                padding: 0 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
        """)
        btn.clicked.connect(self.refresh_machine)
        lay.addWidget(btn)
        lay.addStretch()
        return bar

    @property
    def _dry_run_axis(self) -> AxisDef | None:
        """El eje excluyente que ofrece un simulacro (`clean_artifacts`,
        `sync_common_files`, borrar emuladores). Su presencia es lo que hace
        aparecer el boton Simulacro."""
        return next((a for a in self.capability.single_axes
                     if 'simulacro' in a.values), None)

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setStyleSheet(f"background: {Colors.SURFACE}; border-top: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)
        lay.addStretch()

        self.dry_btn: QPushButton | None = None
        if self._dry_run_axis is not None:
            self.dry_btn = QPushButton("Simulacro")
            self.dry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.dry_btn.setFixedHeight(34)
            self.dry_btn.setToolTip("Corre sin tocar nada: solo muestra qué haría")
            self.dry_btn.clicked.connect(lambda: self._emit_execute(dry_run=True))
            self.dry_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {Colors.BORDER};
                    color: {Colors.TEXT_DIM}; border-radius: 6px;
                    padding: 0 16px; font-size: {Fonts.SIZE_SM}px;
                }}
                QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
                QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; }}
            """)
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
        """El id elegido en una lista larga (no su etiqueta)."""
        combo = self._picks.get(axis_name)
        if combo is None:
            return ''
        value = combo.currentData()
        return value if isinstance(value, str) else ''

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
            'picks': {name: self.pick_value(name) for name in self._picks},
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
            'picks': {name: self.pick_value(name) for name in self._picks},
            'missing_env': self._missing_keys(),
        }

    def set_env(self, values: dict[str, str]) -> None:
        """El panel de configuracion de abajo alimenta la validacion previa."""
        self._env = values
        self._refresh_summary()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle_run()

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
        """Claves de `.env` que esta accion puede llegar a necesitar (todos los
        pasos, no solo los activos) — para filtrar el panel de configuracion."""
        needed = set(relevant_keys_for(self.capability.id))
        for step in self.steps:
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
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(required_keys_for(step.id))
        cfg = envfile.Config(self._env, repo_name=envfile.repo_name_of(self.project.path))
        return sorted(k for k in needed if not cfg.get(k))

    def blockers(self) -> list[str]:
        """Publico para el rail: por que no se puede correr sin abrir la
        pestana (`ui/tab_panel.py::quick_run` lo reporta en la consola)."""
        return self._blockers()

    def _blockers(self) -> list[str]:
        """Razones por las que 'Ejecutar' no puede correr."""
        reasons = []
        # Un eje descubierto sin valores no es "olvidaste elegir": es que el
        # repo no tiene eso. Se dice asi, y no se pide ademas que elija de una
        # lista vacia.
        if self._loading:
            return ["leyendo el catálogo del SDK…"]
        vacios = {a.name for a in self.capability.axes if a.is_discovered and not a.values}
        for axis in self.capability.axes:
            if axis.name not in vacios:
                continue
            donde = 'en esta máquina' if axis.is_from_machine else 'en este repo'
            # Un eje opcional que ademas admite estar vacio (las dos listas de
            # "Liberar disco") no bloquea: que no haya AVD creados no impide
            # borrar una imagen.
            if axis.is_multi and axis.allow_empty:
                continue
            reasons.append(f"no hay {axis.display.lower()} {donde}")
        for axis in self.capability.pick_axes:
            if axis.values and not self.pick_value(axis.name):
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
                background: {self.accent if enabled else Colors.SURFACE_ALT};
                color: {Colors.BG if enabled else Colors.TEXT_MUTED};
                border: none; border-radius: 6px;
                padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {self.accent if enabled else Colors.SURFACE_ALT}; }}
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
        defecto si nunca se tocaron. Lo usa el boton de correr del rail.
        Devuelve si corrio."""
        return self._emit_execute()
