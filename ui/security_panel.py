from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, Signal

from core import protection
from core.projects import Project
from ui import params_store
from ui.theme import Colors, Fonts

"""
Los seguros del repo: una casilla por tipo de objetivo (`core/protection.py`).

**No viven en `config.env`.** Ese archivo son los datos que las tareas
necesitan para trabajar —la IP del VPS, el usuario, el token, las rutas—, y
ningun paso lee jamas un seguro: quien los mira es la consola, antes de dejar
correr (`TabPanel._guard_ok`). Son de la misma familia que los pasos que quedan
marcados en el panel de una accion, asi que van al mismo archivo que ellos,
`.consola/params.json` (`ui/params_store.py`).

Que sea un archivo distinto tiene ademas una consecuencia visible: aca no hay
boton Guardar. Tocar una casilla la guarda, como en el panel de parametros. El
boton Guardar de Configuracion solo manda sobre `config.env`, y que una seccion
dependiera del boton de otra era justo lo que hacia creer que los seguros no se
estaban guardando.
"""


class SecurityPanel(QWidget):
    """La seccion «Seguridad» del panel derecho.

    Emite `changed` con el estado entero ({target_id: bool}) para el resumen de
    la cabecera y el indicador de la barra de estado, que leen lo que hay en
    pantalla y no lo que quedo en disco.
    """
    changed = Signal(dict)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._state = params_store.load_protection(project.path)
        self._checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Son cinco casillas fijas, pero igual van dentro de un scroll: la
        # seccion del acordeon se arrastra a mano y sin el, achicarla de mas
        # aplastaba las casillas una contra otra en vez de recortarlas.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._body = QWidget()
        self._body.setStyleSheet(f"background: {Colors.SURFACE};")
        lay = QVBoxLayout(self._body)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        for target in protection.TARGETS:
            # La explicacion vive en el tooltip y no en un texto al lado: la
            # etiqueta de la casilla ya dice que protege.
            check = QCheckBox(target.setting_label)
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.setChecked(self._state[target.id])
            check.setToolTip(target.why)
            check.setStyleSheet(f"QCheckBox {{ font-size: {Fonts.SIZE_XS}px; }}")
            check.toggled.connect(lambda marcado, tid=target.id: self._toggle(tid, marcado))
            self._checks[target.id] = check
            lay.addWidget(check)

        scroll.setWidget(self._body)
        root.addWidget(scroll)

    def state(self) -> dict:
        """Lo que se ve, que es lo que `TabPanel._guard_ok` va a aplicar."""
        return dict(self._state)

    def content_height(self) -> int:
        """Alto que piden las casillas sin scroll — lo usa
        `TabPanel._relayout_right` para decidir cuanto darle a la seccion.
        Se pregunta al cuerpo y no al scroll, que no tiene alto propio."""
        return self._body.sizeHint().height()

    def _toggle(self, target_id: str, marcado: bool) -> None:
        self._state[target_id] = bool(marcado)
        params_store.save_protection(self.project.path, self._state)
        self.changed.emit(self.state())
