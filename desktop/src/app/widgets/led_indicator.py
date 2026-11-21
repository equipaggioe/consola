"""A status LED."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import (
    QCoreApplication,
    QEasingCurve,
    QObject,
    Qt,
    QVariantAnimation,
    Slot,
)
from PySide6.QtGui import (
    QAccessible,
    QAccessibleInterface,
    QBrush,
    QPainter,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QAccessibleWidget, QWidget

from app.services import motion
from app.services.language import QT_TRANSLATE_NOOP
from app.theme import Colors


class LedIndicator(QWidget):
    """Circular LED with states: 'off', 'on', 'green', 'amber', 'red'.

    Only 'green' pulses, and that pulse means *something is alive right
    now*, such as a running service. A static fact, such as an installed
    tool, uses 'on': the same green without animation. Without that
    difference each status bar indicator would leave an animation
    looping forever, and it would lie about what it reports.

    The pulse stops with «Animaciones» in the Ver menu
    (`services/motion.py`): the LED stays lit, and its state is still in
    its description.
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

        # A `QVariantAnimation` and not a `QPropertyAnimation`: that one
        # needs a `Property` on the class, and in PySide6 6.12 a
        # `Property` is not collected at shutdown (`ResourceWarning`
        # under `PYTHONDEVMODE`).
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(2000)
        self.animation.setStartValue(0.4)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setLoopCount(-1)
        self.animation.valueChanged.connect(self._glow)
        motion.notifier.changed.connect(self._pulse)

    def set_state(self, state: str) -> None:
        """Set the state, and start or stop the pulse."""
        self._state = state
        # Qt sends the change of description to assistive technology.
        self.setAccessibleDescription(
            QCoreApplication.translate("LedIndicator", self.WORDS[state])
        )
        self._pulse()

    @Slot()
    def _pulse(self) -> None:
        """Pulse if green and things may move; else stay lit."""
        if self._state == "green" and motion.animated():
            if self.animation.state() != QVariantAnimation.State.Running:
                self.animation.start()
        else:
            self.animation.stop()
            self._opacity = 1.0
        self.update()

    @Slot(object)
    def _glow(self, value: float) -> None:
        """Set the glow opacity, a step of the pulse."""
        self._opacity = value
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_map = {
            "off": Colors.OUTLINE,
            "on": Colors.SUCCESS,
            "green": Colors.SUCCESS,
            "amber": Colors.WARNING,
            "red": Colors.ERROR,
        }
        hex_color = color_map.get(self._state, Colors.OUTLINE)
        base_color = QBrush(hex_color).color()

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
            glow = base_color.toRgb()
            glow.setAlpha(int(100 * self._opacity))
            glow_pen.setColor(glow)
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
