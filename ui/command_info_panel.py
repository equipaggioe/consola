from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt

from ui.theme import Colors, Fonts
from ui.palettes import Palette, NEUTRAL
from core.registry import Capability
from core import command_docs


class _Heading(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )


class CommandInfoPanel(QWidget):
    """Descripcion larga de la accion abierta y los pasos que ejecuta.

    Vive en la seccion de arriba del acordeon derecho. La cabecera de esa
    seccion lleva el nombre de la accion (lo pone `TabPanel`), asi que plegada
    no se pierde nada: sigue diciendo cual es. El texto sale de
    `core/command_docs.py` cuando existe, y si no de la descripcion de una
    linea de la capacidad mas las etiquetas de sus pasos.

    Solo que hace el boton y en que orden: la ficha no tiene una seccion de
    advertencias ni de casos borde.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # Sin esto, un QWidget derivado ignora el fondo de su propia hoja y
        # deja ver el gris de la hoja global (`ui/theme.py`): el cuerpo de la
        # seccion no se teñia del color del repo.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.pal = NEUTRAL

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll   # lo repinta `_restyle`

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.setSpacing(10)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._content)
        root.addWidget(scroll)

        self._restyle()
        self.set_capability(None)

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

    def set_palette(self, pal: Palette) -> None:
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        # Cuerpo de seccion: `panel`, un escalon por debajo de su cabecera.
        self.setStyleSheet(f"CommandInfoPanel {{ background: {self.pal.panel}; }}")
        self._scroll.setStyleSheet(self._scroll_style())

    # --- API ---------------------------------------------------------------
    def content_height(self) -> int:
        """Alto que pide el texto sin scroll — lo usa `TabPanel._relayout_right`
        para decidir cuanto darle a la seccion."""
        return self._content.sizeHint().height()

    def set_capability(self, capability: Capability | None) -> None:
        self._clear()
        if capability is None:
            self._lay.addWidget(self._muted(
                "Abre una acción para ver de qué se trata y qué pasos ejecuta."))
            return

        doc = command_docs.get(capability.id)
        summary = doc.summary if doc else (
            capability.description or "Esta acción todavía no tiene una "
            "descripción larga.")
        self._lay.addWidget(self._body(summary))

        steps = doc.steps if doc else [s.label for s in capability.steps]
        if steps:
            self._lay.addWidget(_Heading("Pasos"))
            for i, text in enumerate(steps, 1):
                self._lay.addWidget(self._step(i, text))

    # --- interno ---------------------------------------------------------
    def _clear(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _body(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-size: {Fonts.SIZE_SM}px; line-height: 140%;")
        return label

    def _muted(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px;")
        return label

    def _step(self, number: int, text: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        badge = QLabel(str(number))
        badge.setFixedWidth(16)
        badge.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        badge.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700;")

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;")

        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(body, 1)
        return row
