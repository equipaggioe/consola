from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt

from ui.theme import Colors, Fonts
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
    no se pierde nada: sigue diciendo cual es. El texto largo sale de
    `core/command_docs.py` cuando existe, y si no de la descripcion de una
    linea de la capacidad mas las etiquetas de sus pasos.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"CommandInfoPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.setSpacing(10)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._content)
        root.addWidget(scroll)

        self.set_capability(None)

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

        if doc and doc.notes:
            self._lay.addWidget(_Heading("A tener en cuenta"))
            for text in doc.notes:
                self._lay.addWidget(self._note(text))

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

    def _note(self, text: str) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        dot = QLabel("·")
        dot.setFixedWidth(16)
        dot.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        dot.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px;")

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;")

        lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(body, 1)
        return row
