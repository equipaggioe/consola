from __future__ import annotations
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPen
from PySide6.QtCore import Qt, QPropertyAnimation, Property, QEasingCurve
from ..theme import Colors

class LedIndicator(QWidget):
    """Circular LED with states: 'off', 'green', 'amber', 'red'.
    When 'green', pulses smoothly between 0.5 and 1.0 opacity."""
    
    def __init__(self, parent=None, size: int = 10):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._state = 'off'
        self._opacity = 1.0
        self._size = size
        
        self.animation = QPropertyAnimation(self, b"glowOpacity", self)
        self.animation.setDuration(2000)
        self.animation.setStartValue(0.4)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setLoopCount(-1)
        
    def set_state(self, state: str) -> None:
        self._state = state
        if state == 'green':
            if self.animation.state() != QPropertyAnimation.State.Running:
                self.animation.start()
        else:
            self.animation.stop()
            self._opacity = 1.0
        self.update()

    def get_glowOpacity(self) -> float:
        return self._opacity
        
    def set_glowOpacity(self, value: float) -> None:
        self._opacity = value
        self.update()
        
    glowOpacity = Property(float, get_glowOpacity, set_glowOpacity)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        color_map = {
            'off': Colors.INACTIVE,
            'green': Colors.SUCCESS,
            'amber': Colors.WARNING,
            'red': Colors.ERROR
        }
        hex_color = color_map.get(self._state, Colors.INACTIVE)
        base_color = QColor(hex_color)
        
        if self._state == 'green':
            base_color.setAlphaF(self._opacity)
            
        center = self.rect().center()
        radius = self._size / 2 - 1
        
        gradient = QRadialGradient(center, radius)
        light_color = base_color.lighter(130)
        
        gradient.setColorAt(0.0, light_color)
        gradient.setColorAt(0.7, base_color)
        gradient.setColorAt(1.0, base_color.darker(150))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, radius, radius)
        
        if self._state != 'off':
            glow_radius = radius + 1
            painter.setBrush(Qt.BrushStyle.NoBrush)
            glow_pen = QPen(base_color)
            glow_pen.setWidth(1)
            glow_pen.setColor(QColor(base_color.red(), base_color.green(), base_color.blue(), int(100 * self._opacity)))
            painter.setPen(glow_pen)
            painter.drawEllipse(center, glow_radius, glow_radius)
        
        painter.end()
