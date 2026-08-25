from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QScrollArea, QFrame, QButtonGroup
)
from PySide6.QtCore import Qt, Signal

from ui.theme import Colors, Fonts
from core.registry import Capability, AxisDef, Step, registry
from core.projects import Project
from core.settings import required_keys_for


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

    def __init__(self, capability: Capability, project: Project, env_panel, parent=None):
        super().__init__(parent)
        self.capability = capability
        self.project = project
        self.accent = project.color
        self.env_panel = env_panel
        self.steps: list[Step] = registry.resolve_steps(capability)
        self._env: dict[str, str] = {}

        self._checks: dict[str, dict[str, QCheckBox]] = {}   # axis -> value -> check
        self._options: dict[str, dict[str, QCheckBox]] = {}  # axis -> value -> check (exclusivo)
        self._option_groups: list[QButtonGroup] = []
        self._step_checks: dict[str, QCheckBox] = {}

        self.setStyleSheet(f"ParamsPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._body_widget = self._build_body()
        self._footer_widget = self._build_footer()

        root.addWidget(self._body_widget, 1)
        root.addWidget(self._footer_widget)

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

        for axis in self.capability.multi_axes:
            lay.addWidget(self._build_multi_axis(axis))

        if len(self.steps) > 1:
            lay.addWidget(self._build_steps())

        singles = self.capability.single_axes
        if singles:
            lay.addWidget(self._build_options(singles))

        self._content = content
        scroll.setWidget(content)
        return scroll

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
            check.setChecked(True)  # por defecto todas: replica el comportamiento de hoy
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
            for i, value in enumerate(axis.values):
                check = QCheckBox(value)
                check.setCursor(Qt.CursorShape.PointingHandCursor)
                if value in axis.danger:
                    check.setStyleSheet(f"QCheckBox {{ color: {Colors.ERROR}; }}")
                if i == 0:
                    check.setChecked(True)
                group.addButton(check)
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

    def payload(self) -> dict:
        return {
            'capability_id': self.capability.id,
            'project': self.project.name,
            'variants': {name: self.selection(name) for name in self._checks},
            'steps': [s.id for s in self.active_steps()],
            'options': {name: self.option_value(name) for name in self._options},
            'missing_env': self._missing_keys(),
        }

    def set_env(self, values: dict[str, str]) -> None:
        """El panel de configuracion de abajo alimenta la validacion previa."""
        self._env = values
        self._refresh_summary()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle_run()

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
        needed = set(required_keys_for(self.capability.id))
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(required_keys_for(step.id))
        return sorted(k for k in needed if not self._env.get(k, '').strip())

    def _blockers(self) -> list[str]:
        """Razones por las que 'Ejecutar' no puede correr."""
        reasons = []
        for axis in self.capability.multi_axes:
            if not self.selection(axis.name):
                reasons.append(f"selecciona al menos un valor en {axis.display.lower()}")
        if not self.active_steps():
            reasons.append("selecciona al menos un paso")
        missing = self._missing_keys()
        if missing:
            reasons.append(f"faltan claves de configuración: {', '.join(missing)}")
        return reasons

    def _refresh_summary(self, *_args) -> None:
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
        """Ejecuta con los parametros actuales de la pestana (los por
        defecto si recien se abrio); usado por el boton de correr sin
        abrir la pestana, en el rail. Devuelve si corrio."""
        return self._emit_execute()
