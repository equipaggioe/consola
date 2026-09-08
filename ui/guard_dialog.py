from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt

from ui.theme import Colors, Fonts
from core.projects import Project
from core.protection import Target

"""
Los dos avisos del seguro por tipo de objetivo (`core/protection.py`). Ninguno
pide escribir nada: ni una palabra, ni el nombre del repo.

- `BlockedDialog` — un objetivo del radio de dano esta protegido en este repo.
  La accion NO corre y este dialogo no tiene forma de dejarla correr: su unico
  boton cierra. El seguro se quita en Configuracion, seccion Seguridad, una vez.
  Un seguro que se puede saltar en el mismo gesto con el que se aprieta Ejecutar
  no es un seguro.

- `ReminderDialog` — la accion destruye algo pero este repo no protege ese
  objetivo. No hay nada que comprobar, solo algo que recordar: sobre que repo se
  esta trabajando. Cancelar y Continuar, y Continuar nunca es el predeterminado
  —un Enter de mas no destruye nada—.

El error que los dos atajan es el mismo: apretar el boton correcto en el repo
equivocado. Por eso los dos muestran la identidad del repo en grande, con su
color, su icono y su ruta completa — el dato que se da por sabido cuando uno se
confunde de pestana.
"""


class _GuardDialog(QDialog):
    """Base de los dos avisos: el encabezado, la tarjeta del repo y la nota."""

    def __init__(self, project: Project, titulo_ventana: str, encabezado: str,
                 nota: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle(titulo_ventana)
        self.setMinimumWidth(460)
        self.setStyleSheet(f"QDialog {{ background: {Colors.SURFACE}; }}")

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 20, 22, 18)
        self._lay.setSpacing(14)

        cabecera = QLabel(encabezado)
        cabecera.setWordWrap(True)
        cabecera.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;")
        self._lay.addWidget(cabecera)

        self._lay.addWidget(self._tarjeta_repo())

        pie = QLabel(nota)
        pie.setWordWrap(True)
        pie.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        self._lay.addWidget(pie)

    def _tarjeta_repo(self) -> QWidget:
        caja = QWidget()
        caja.setStyleSheet(
            f"background: {Colors.SURFACE_ALT}; border-left: 3px solid "
            f"{self.project.color}; border-radius: 4px;")
        lay = QVBoxLayout(caja)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)

        nombre = QLabel(f'{self.project.icon or chr(9671)}  {self.project.name}')
        nombre.setStyleSheet(
            f"background: transparent; color: {self.project.color}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 700;")
        ruta = QLabel(self.project.path)
        ruta.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        lay.addWidget(nombre)
        lay.addWidget(ruta)
        return caja

    def _boton(self, texto: str) -> QPushButton:
        boton = QPushButton(texto)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.setFixedHeight(32)
        return boton


class BlockedDialog(_GuardDialog):
    """La accion toca un objetivo protegido: se informa y no corre.

    No hereda de nadie que tenga boton de aceptar: aca no hay 'continuar igual'.
    """

    def __init__(self, project: Project, action: str, targets: list[Target],
                 parent=None):
        cuales = _enumerar([t.label for t in targets])
        super().__init__(
            project,
            'Accion bloqueada',
            f'{action} toca {cuales}, y este repositorio lo tiene protegido.',
            'El seguro se quita en Configuracion, seccion Seguridad: por tipo '
            'de objetivo y solo para este repositorio.',
            parent)

        razones = QLabel('\n'.join(
            f'•  {t.setting_label} — {t.why}' for t in targets))
        razones.setWordWrap(True)
        razones.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        self._lay.insertWidget(2, razones)

        botones = QHBoxLayout()
        botones.addStretch()
        entendido = self._boton('Entendido')
        entendido.setDefault(True)
        entendido.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER}; border-radius: 5px;
                padding: 0 18px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; }}
        """)
        entendido.clicked.connect(self.reject)
        botones.addWidget(entendido)
        self._lay.addLayout(botones)


class ReminderDialog(_GuardDialog):
    """La accion destruye algo no protegido: recordatorio del repo, sin mas."""

    def __init__(self, project: Project, action: str, targets: list[Target],
                 parent=None):
        cuales = _enumerar([t.label for t in targets])
        super().__init__(
            project,
            'Confirmar accion',
            f'{action} va a destruir {cuales}.',
            'Este objetivo no esta protegido en este repositorio. Se protege '
            'en Configuracion, seccion Seguridad.',
            parent)

        botones = QHBoxLayout()
        botones.addStretch()

        cancelar = self._boton('Cancelar')
        cancelar.setDefault(True)
        cancelar.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_DIM}; border-radius: 5px; padding: 0 16px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
        """)
        cancelar.clicked.connect(self.reject)

        continuar = self._boton('Continuar')
        # Nunca es el boton por defecto: un Enter de mas no destruye nada.
        continuar.setAutoDefault(False)
        continuar.setDefault(False)
        continuar.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ERROR}; color: {Colors.BG};
                border: none; border-radius: 5px; padding: 0 18px;
                font-size: {Fonts.SIZE_XS}px; font-weight: 600;
            }}
        """)
        continuar.clicked.connect(self.accept)

        botones.addWidget(cancelar)
        botones.addWidget(continuar)
        self._lay.addLayout(botones)


def _enumerar(cosas: list[str]) -> str:
    if len(cosas) <= 1:
        return cosas[0] if cosas else 'algo'
    return ', '.join(cosas[:-1]) + ' y ' + cosas[-1]
