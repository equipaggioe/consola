from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QScrollArea, QFrame, QButtonGroup, QLineEdit, QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal

from ui.theme import Colors, Fonts
from core import envfile
from core.catalog import for_project
from core.registry import Capability, AxisDef, Step, registry
from core.projects import Project
from core.settings import required_keys_for
from ui import params_store


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )


class ParamsPanel(QWidget):
    """Parametros de UNA ejecucion: variantes, pasos y opciones.

    Vive dentro de la pestana de la accion, asi que su estado sobrevive a
    cambiar de pestana y volver — y desde ahi se puede volver a correr.
    """
    execute_requested = Signal(dict)
    params_changed = Signal()   # lo guardado cambio: el rail revisa que puede correr

    def __init__(self, capability: Capability, project: Project, env_panel, parent=None):
        super().__init__(parent)
        # Los ejes descubiertos se resuelven contra ESTE repo, no contra el
        # catalogo: la lista de apps sale de mirar las carpetas (PLAN.md 2.4).
        self.capability = for_project(capability, project.path)
        self.project = project
        self.accent = project.color
        self.env_panel = env_panel
        self.steps: list[Step] = registry.resolve_steps(capability)
        self._env: dict[str, str] = {}

        self._checks: dict[str, dict[str, QCheckBox]] = {}   # axis -> value -> check
        self._options: dict[str, dict[str, QCheckBox]] = {}  # axis -> value -> check (exclusivo)
        self._fields: dict[str, QLineEdit | QPlainTextEdit] = {}  # axis -> valor escrito
        self._option_groups: list[QButtonGroup] = []
        self._step_checks: dict[str, QCheckBox] = {}
        self._restoring = True   # mientras se arma, ningun cambio se guarda

        self.setStyleSheet(f"ParamsPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._body_widget = self._build_body()
        self._footer_widget = self._build_footer()

        root.addWidget(self._body_widget, 1)
        root.addWidget(self._footer_widget)

        # Lo elegido la ultima vez para este boton EN ESTE repo manda sobre
        # los valores por defecto; sin nada guardado, quedan los de arriba.
        self.apply_state(params_store.load(self.project.path, self.capability.id))
        self._restoring = False
        self._refresh_summary()

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

        self._content = content
        scroll.setWidget(content)
        return scroll

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

        self._checks[axis.name] = {}
        for value in axis.values:
            check = QCheckBox(value)
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

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setStyleSheet(f"background: {Colors.SURFACE}; border-top: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(6)

        for text, handler in (("Recargar", self.env_panel.reload), ("Guardar", self.env_panel.save)):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {Colors.BORDER};
                    color: {Colors.TEXT_DIM}; border-radius: 5px;
                    padding: 0 12px; font-size: {Fonts.SIZE_XS}px;
                }}
                QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
            """)
            btn.clicked.connect(handler)
            lay.addWidget(btn)
        lay.addStretch()

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
        return (self._content.sizeHint().height()
                + self._footer_widget.sizeHint().height()
                + 4)

    def relevant_keys(self) -> set[str]:
        """Claves de `.env` que esta accion puede llegar a necesitar (todos los
        pasos, no solo los activos) — para filtrar el panel de configuracion."""
        needed = set(required_keys_for(self.capability.id))
        for step in self.steps:
            needed |= step.requires_env
            needed |= set(required_keys_for(step.id))
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
        vacios = {a.name for a in self.capability.axes if a.is_discovered and not a.values}
        for axis in self.capability.axes:
            if axis.name in vacios:
                reasons.append(f"no hay {axis.display.lower()} en este repo")
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

    def _emit_execute(self) -> bool:
        if self._blockers():
            return False
        self.execute_requested.emit(self.payload())
        return True

    def try_run(self) -> bool:
        """Ejecuta con los parametros actuales de la pestana — que al
        abrirse son los guardados para este boton en este repo, o los por
        defecto si nunca se tocaron. Lo usa el boton de correr del rail.
        Devuelve si corrio."""
        return self._emit_execute()
