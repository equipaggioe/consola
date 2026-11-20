"""A status LED."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import (
    Property,
    QCoreApplication,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import (
    QAccessible,
    QAccessibleInterface,
    QBrush,
    QColor,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QAccessibleWidget, QWidget

from app.services.language import QT_TRANSLATE_NOOP
from app.theme import Colors


class LedIndicator(QWidget):
    """Circular LED with states: 'off', 'on', 'green', 'amber', 'red'.

    Only 'green' pulses, and that pulse means *something is alive right
    now*, such as a running service. A static fact, such as an installed
    tool, uses 'on': the same green without animation. Without that
    difference each status bar indicator would leave an animation
    looping forever, and it would lie about what it reports.
    """

    STEADY = ("off", "on", "amber", "red")
    # What each state says to assistive technology, which does not see
    # the color. Whoever places the LED gives it its name.
    WORDS = {
        "off": QT_TRANSLATE_NOOP("LedIndicator", "apagado"),
        "on": QT_TRANSLATE_NOOP("LedIndicator", "encendido"),
        "green": QT_TRANSLATE_NOOP("LedIndicator", "activo"),
        "amber": QT_TRANSLATE_NOOP("LedIndicator", "con advertencia"),
        "red": QT_TRANSLATE_NOOP("LedIndicator", "con error"),
    }

    def __init__(self, parent: QWidget | None = None, size: int = 10) -> None:
        """Build the LED."""
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._state = "off"
        self.setAccessibleDescription(
            QCoreApplication.translate("LedIndicator", self.WORDS["off"])
        )
        self._opacity = 1.0
        self._size = size

        self.animation = QPropertyAnimation(self, b"glow_opacity", self)
        self.animation.setDuration(2000)
        self.animation.setStartValue(0.4)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setLoopCount(-1)

    def set_state(self, state: str) -> None:
        """Set the state, and start or stop the pulse."""
        self._state = state
        # Qt sends the change of description to assistive technology.
        self.setAccessibleDescription(
            QCoreApplication.translate("LedIndicator", self.WORDS[state])
        )
        if state == "green":
            if self.animation.state() != QPropertyAnimation.State.Running:
                self.animation.start()
        else:
            self.animation.stop()
            self._opacity = 1.0
        self.update()

    def get_glow_opacity(self) -> float:
        """Return the glow opacity, for the animation."""
        return self._opacity

    def set_glow_opacity(self, value: float) -> None:
        """Set the glow opacity, for the animation."""
        self._opacity = value
        self.update()

    glow_opacity = Property(float, get_glow_opacity, set_glow_opacity)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_map = {
            "off": Colors.INACTIVE,
            "on": Colors.SUCCESS,
            "green": Colors.SUCCESS,
            "amber": Colors.WARNING,
            "red": Colors.ERROR,
        }
        hex_color = color_map.get(self._state, Colors.INACTIVE)
        base_color = QColor(hex_color)

        if self._state == "green":
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

        if self._state != "off":
            glow_radius = radius + 1
            painter.setBrush(Qt.BrushStyle.NoBrush)
            glow_pen = QPen(base_color)
            glow_pen.setWidth(1)
            glow_pen.setColor(
                QColor(
                    base_color.red(),
                    base_color.green(),
                    base_color.blue(),
                    int(100 * self._opacity),
                )
            )
            painter.setPen(glow_pen)
            painter.drawEllipse(center, glow_radius, glow_radius)

        painter.end()


class _Accessible(QAccessibleWidget):
    """The LED as an indicator: its name, and its state in words."""

    def __init__(self, led: LedIndicator) -> None:
        """Give the LED the indicator role."""
        super().__init__(led, QAccessible.Role.Indicator)


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of `LedIndicator`, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, LedIndicator) else None


QAccessible.installFactory(_interface)
