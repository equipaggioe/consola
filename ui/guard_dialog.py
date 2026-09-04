from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget
)
from PySide6.QtCore import Qt

from ui.theme import Colors, Fonts
from core.projects import Project
from core.protection import Target

"""
El dialogo del seguro: la unica puerta por la que pasa un destructivo cuyo
objetivo esta protegido en este repo (`core/protection.py`).

Pide escribir el NOMBRE DEL REPO, no una palabra magica. La diferencia es todo
el diseno: teclear `BORRAR` es correcto en cualquier repositorio, asi que el
automatismo siempre acierta y no se comprueba nada. Teclear `navetta` solo es
correcto en navetta — si te confundiste de pestana, tus dedos escriben el
nombre del repo que CREES tener abierto y la accion no corre. El reflejo no
degrada esta comprobacion: el reflejo ES la comprobacion.

Por eso el campo arranca vacio, sin autocompletado y sin repetir el nombre que
hay que escribir: si estuviera ahi para copiarlo, volveria a ser una palabra
magica.
"""


class GuardDialog(QDialog):
    """Confirmacion escrita para un destructivo sobre un objetivo protegido."""

    def __init__(self, project: Project, action: str, targets: list[Target],
                 parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle('Confirmar accion destructiva')
        self.setMinimumWidth(460)
        self.setStyleSheet(f"QDialog {{ background: {Colors.SURFACE}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(14)

        titulo = QLabel(f'{action} va a destruir '
                        + _enumerar([t.label for t in targets]))
        titulo.setWordWrap(True)
        titulo.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;")
        lay.addWidget(titulo)

        # La identidad del repo, en grande y con su color: es exactamente el
        # dato que se da por sabido cuando uno se equivoca de pestana.
        lay.addWidget(self._tarjeta_repo())

        pide = QLabel('Escribe el nombre del repositorio para continuar:')
        pide.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-size: {Fonts.SIZE_SM}px;")
        lay.addWidget(pide)

        self.field = QLineEdit()
        self.field.setFixedHeight(34)
        self.field.setPlaceholderText('nombre del repositorio')
        self.field.textChanged.connect(self._revisar)
        self.field.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.SURFACE_ALT}; color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER}; border-radius: 5px;
                padding: 0 10px; font-size: {Fonts.SIZE_SM}px;
            }}
            QLineEdit:focus {{ border: 1px solid {Colors.ERROR}; }}
        """)
        lay.addWidget(self.field)

        self.aviso = QLabel('')
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet(
            f"background: transparent; color: {Colors.WARNING}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        self.aviso.setVisible(False)
        lay.addWidget(self.aviso)

        nota = QLabel('Este seguro se quita en Configuracion, seccion Seguridad: '
                      'por tipo de objetivo y solo para este repositorio.')
        nota.setWordWrap(True)
        nota.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        lay.addWidget(nota)

        botones = QHBoxLayout()
        botones.addStretch()
        cancelar = QPushButton('Cancelar')
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.setFixedHeight(32)
        cancelar.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_DIM}; border-radius: 5px; padding: 0 16px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
        """)
        cancelar.clicked.connect(self.reject)

        self.ok_btn = QPushButton('Destruir')
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setFixedHeight(32)
        self.ok_btn.setEnabled(False)
        # Nunca es el boton por defecto: un Enter de mas no debe destruir nada.
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.setDefault(False)
        cancelar.setDefault(True)
        self.ok_btn.clicked.connect(self.accept)

        botones.addWidget(cancelar)
        botones.addWidget(self.ok_btn)
        lay.addLayout(botones)

        self._restyle_ok()
        self.field.setFocus()

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

    def _revisar(self, texto: str) -> None:
        escrito = texto.strip()
        coincide = escrito.casefold() == self.project.name.casefold()
        self.ok_btn.setEnabled(coincide)
        # El caso que justifica todo el dialogo: escribiste bien el nombre de
        # OTRO repo abierto. Decirlo es mas util que un campo en rojo.
        otro = _otro_repo(self, escrito)
        if otro and not coincide:
            self.aviso.setText(
                f'{otro} es otra pestana. Esta accion corre sobre '
                f'{self.project.name}.')
            self.aviso.setVisible(True)
        else:
            self.aviso.setVisible(False)
        self._restyle_ok()

    def _restyle_ok(self) -> None:
        activo = self.ok_btn.isEnabled()
        self.ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ERROR if activo else Colors.SURFACE_ALT};
                color: {Colors.BG if activo else Colors.TEXT_MUTED};
                border: none; border-radius: 5px; padding: 0 18px;
                font-size: {Fonts.SIZE_XS}px; font-weight: 600;
            }}
        """)


def _enumerar(cosas: list[str]) -> str:
    if len(cosas) <= 1:
        return cosas[0] if cosas else 'algo'
    return ', '.join(cosas[:-1]) + ' y ' + cosas[-1]


def _otro_repo(widget, escrito: str) -> str:
    """Si lo escrito es el nombre de otra pestana abierta, cual.

    Es el aviso mas util del dialogo: no dice "te equivocaste de palabra", dice
    "te equivocaste de repositorio", que es el error real que se busca atajar.
    """
    if not escrito:
        return ''
    # Subiendo por los padres, no por `window()`: un QDialog ES una ventana,
    # asi que `window()` se devuelve a si mismo y nunca llega a MainWindow.
    nodo, barra = widget.parent(), None
    while nodo is not None and barra is None:
        barra = getattr(nodo, 'project_tabs', None)
        nodo = nodo.parent()
    if barra is None:
        return ''
    for tab in getattr(barra, 'tabs', []):
        if tab.project.name.casefold() == escrito.casefold():
            return tab.project.name
    return ''
