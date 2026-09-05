from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal

from ..theme import Colors, Fonts


# `QWIDGETSIZE_MAX`: el valor con el que Qt entiende "sin tope de alto".
SIN_TOPE = 16777215


class AccordionHeader(QWidget):
    """La barra clicable de una seccion. Siempre visible, este abierta o no:
    es lo que hace que las tres secciones se sigan viendo aunque solo quepa
    una desplegada."""

    clicked = Signal()

    HEIGHT = 30

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName('accordionHeader')
        # Un QWidget *derivado* no pinta el fondo de su hoja de estilo sin
        # esto; los QWidget sueltos del resto del archivo si lo hacen.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QWidget#accordionHeader {{
                background: {Colors.SURFACE};
                border-bottom: 1px solid {Colors.BORDER};
            }}
            QWidget#accordionHeader:hover {{ background: {Colors.SURFACE_HOVER}; }}
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 12, 0)
        lay.setSpacing(6)

        self.chevron = QLabel('▾')
        self.chevron.setFixedWidth(11)
        self.chevron.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")

        self.title = QLabel(title.upper())
        self.title.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.1px;")

        # Lo que la seccion tiene para decir sin abrirla ("3 de 5 protegidos").
        # Vacio por defecto: no toda seccion tiene un resumen que valga.
        self.summary = QLabel('')
        self.summary.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;")

        lay.addWidget(self.chevron)
        lay.addWidget(self.title)
        lay.addStretch(1)
        lay.addWidget(self.summary)

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AccordionSection(QWidget):
    """Cabecera + cuerpo plegable, al estilo de la barra lateral de VSCode.

    Pensada para vivir dentro de un `QSplitter` vertical: cerrada se pone un
    `maximumHeight` de la altura de su cabecera, que es lo unico que el
    splitter respeta para no dejar arrastrarla mas alla. Abierta lo suelta y
    quien la contiene reparte el alto (`TabPanel._relayout_right`).

    No se eligio pestanas justamente por esto: las tres secciones del panel
    derecho se leen juntas —un bloqueo de `ParamsPanel` puede decir "faltan
    claves de configuracion" y esas claves estan en la seccion de abajo—, y
    unas pestañas obligarian a alternar entre lo que se compara.
    """

    toggled = Signal(bool)

    def __init__(self, title: str, body: QWidget, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.body = body

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = AccordionHeader(title)
        self.header.clicked.connect(self.toggle)
        root.addWidget(self.header)
        root.addWidget(body, 1)

        self._expanded = not expanded   # para que `set_expanded` no salga de una
        self.set_expanded(expanded, announce=False)

    # --- estado -------------------------------------------------------
    def is_expanded(self) -> bool:
        return self._expanded

    def header_height(self) -> int:
        return AccordionHeader.HEIGHT

    def set_expanded(self, value: bool, announce: bool = True) -> None:
        if value == self._expanded:
            return
        self._expanded = value
        self.body.setVisible(value)
        self.header.chevron.setText('▾' if value else '▸')
        self.setMinimumHeight(AccordionHeader.HEIGHT)
        self.setMaximumHeight(SIN_TOPE if value else AccordionHeader.HEIGHT)
        if announce:
            self.toggled.emit(value)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_summary(self, text: str) -> None:
        self.header.summary.setText(text)
