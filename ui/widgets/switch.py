from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QFont

from ..theme import Colors, Fonts


class ToggleSwitch(QWidget):
    """Interruptor de pastilla con rotulo a la derecha.

    Un QCheckBox diria 'casilla de un formulario': esto no es un parametro
    de ejecucion sino un modo de la vista, y el interruptor lo dice.
    """
    toggled = Signal(bool)

    TRACK_W = 30
    TRACK_H = 16

    def __init__(self, label: str, checked: bool = False,
                 accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.accent = accent
        self._checked = checked

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("ToggleSwitch { background: transparent; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.TRACK_W + 7, 0, 2, 0)
        lay.setSpacing(0)

        self.label = QLabel(label)
        f = QFont(self.label.font())
        f.setPixelSize(Fonts.SIZE_XS)
        self.label.setFont(f)
        lay.addWidget(self.label)

        self._restyle()

    # --- estado -------------------------------------------------------
    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, value: bool, announce: bool = True) -> None:
        if value == self._checked:
            return
        self._checked = value
        self._restyle()
        self.update()
        if announce:
            self.toggled.emit(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()
        self.update()

    def _restyle(self) -> None:
        color = self.accent if self._checked else Colors.TEXT_MUTED
        self.label.setStyleSheet(f"background: transparent; color: {color};")

    # --- interaccion ---------------------------------------------------
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.set_checked(not self._checked)
        super().mouseReleaseEvent(event)

    # --- pintura -------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - self.TRACK_H) / 2
        track = QRectF(0, top, self.TRACK_W, self.TRACK_H)

        if self._checked:
            fill = QColor(self.accent)
            fill.setAlphaF(0.85)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
        else:
            p.setPen(QColor(Colors.BORDER_LIGHT))
            p.setBrush(QColor(Colors.SURFACE_ALT))
        p.drawRoundedRect(track, self.TRACK_H / 2, self.TRACK_H / 2)

        radius = self.TRACK_H / 2 - 2.5
        cx = track.right() - radius - 2.5 if self._checked else track.left() + radius + 2.5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(Colors.BG if self._checked else Colors.TEXT_MUTED))
        p.drawEllipse(QRectF(cx - radius, track.center().y() - radius, radius * 2, radius * 2))
        p.end()


class StarToggle(QWidget):
    """Estrella de favorito para la cabecera de una accion.

    Vive en la cabecera, no entre las casillas del panel de parametros:
    marcar un favorito es estado del repo, no un parametro de esta corrida.
    """
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.accent = accent
        self._checked = checked
        self._hovered = False

        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("StarToggle { background: transparent; }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.glyph = QLabel("★")
        self.glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.glyph)

        self._restyle()

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, value: bool, announce: bool = True) -> None:
        if value == self._checked:
            return
        self._checked = value
        self._restyle()
        if announce:
            self.toggled.emit(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def _restyle(self) -> None:
        if self._checked:
            color = self.accent
        elif self._hovered:
            color = Colors.TEXT_DIM
        else:
            color = Colors.BORDER_LIGHT
        self.glyph.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_LG}px;"
        )
        self.setToolTip("Quitar de favoritos de este repo" if self._checked
                        else "Marcar como favorita en este repo")

    def enterEvent(self, event):
        self._hovered = True
        self._restyle()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._restyle()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.set_checked(not self._checked)
        super().mouseReleaseEvent(event)
