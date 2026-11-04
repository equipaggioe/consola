"""A labeled toggle switch."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.theme import Colors, Fonts


class ToggleSwitch(QWidget):
    """Pill switch with a label to its right.

    A QCheckBox would say «form field»: this is a mode of the view and
    not a run parameter, and a switch says so.
    """

    toggled = Signal(bool)

    TRACK_W = 30
    TRACK_H = 16

    def __init__(
        self,
        label: str,
        checked: bool = False,
        accent: str = Colors.ACCENT,
        parent: QWidget | None = None,
    ) -> None:
        """Build the switch."""
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

    # --- state -------------------------------------------------------
    def is_checked(self) -> bool:
        """Return whether it is on."""
        return self._checked

    def set_checked(self, value: bool, announce: bool = True) -> None:
        """Turn it on or off, telling the listeners if `announce`."""
        if value == self._checked:
            return
        self._checked = value
        self._restyle()
        self.update()
        if announce:
            self.toggled.emit(value)

    def set_accent(self, accent: str) -> None:
        """Change the color of the switch when on."""
        self.accent = accent
        self._restyle()
        self.update()

    def _restyle(self) -> None:
        # Off uses the label gray, not the dimmest one: «only favorites»
        # is a label to be read, not a hint.
        color = self.accent if self._checked else Colors.TEXT_LABEL
        self.label.setStyleSheet(f"background: transparent; color: {color};")

    # --- interaction ---
    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.set_checked(not self._checked)
        super().mouseReleaseEvent(event)

    # --- paint ---
    @override
    def paintEvent(self, event: QPaintEvent) -> None:
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
