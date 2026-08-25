from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Property
from PySide6.QtGui import QPainter, QColor, QFont
from ..theme import Colors, Fonts


class ChevronWidget(QWidget):
    """Flecha que apunta hacia abajo cerrada y hacia arriba abierta (rota
    entre 0 y 180 grados); usada por GroupCard para marcar si una caja de
    grupo esta cerrada o abierta."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self._angle = 0.0

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = value
        self.update()

    angle = Property(float, get_angle, set_angle)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.translate(-self.width() / 2, -self.height() / 2)

        font = QFont(painter.font())
        font.setPixelSize(Fonts.SIZE_XL)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(Colors.TEXT))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▾")
        painter.end()
