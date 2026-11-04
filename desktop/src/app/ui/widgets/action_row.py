"""A row of the action search, with its marks."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QEnterEvent, QFont, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.theme import Colors, Fonts, tint


def _alpha(hex_color: str, alpha: float) -> QColor:
    """Return the same color with transparency.

    QColor does not understand 'rgba(...)', which is what `theme.tint`
    serves for style sheets.
    """
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


class LevelMark(QLabel):
    """An action's level mark: one step or several chained.

    Small on purpose and with no color of its own: the row's color
    already speaks of something else (destructive, favorite, ready), so
    the level is told by shape. `◈` is composite and `◦` is atomic.
    Whoever cannot guess reads it in the tooltip, where the description
    already lives.
    """

    COMPOSITE = "◈"
    ATOMIC = "◦"

    def __init__(self, composite: bool, parent: QWidget | None = None) -> None:
        """Draw the shape for the level."""
        super().__init__(parent)
        self.setText(self.COMPOSITE if composite else self.ATOMIC)
        self.setFixedWidth(12)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(
            "Compuesta: encadena varias acciones atómicas"
            if composite
            else "Atómica: un solo paso, idempotente"
        )
        color = Colors.TEXT_DIM if composite else Colors.TEXT_MUTED
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )


class ScopeMark(QLabel):
    """A reach mark: this action happens to the machine, not the repo.

    It only appears on `scope='machine'` actions, such as installing an
    SDK, because no mark already means «of this repo», the normal case.
    `⌂` reads as the machine itself, and does not get confused with the
    level's shapes next to it.
    """

    GLYPH = "⌂"

    def __init__(self, parent: QWidget | None = None) -> None:
        """Draw the mark."""
        super().__init__(parent)
        self.setText(self.GLYPH)
        self.setFixedWidth(12)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("De la máquina: no depende del repositorio abierto")
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )


class ActionRow(QWidget):
    """An action in the search list: a full-width line.

    Each action fills the row, like a menu entry, with an accent stripe
    at the left that only appears on hover or if destructive. That
    stripe is the favorite button: a click there marks the action
    without opening it.
    """

    triggered = Signal(str)
    favorite_toggled = Signal(str, bool)
    run_requested = Signal(str)

    HEIGHT = 32
    # clickable width of the stripe, roomier than its visual stroke
    PIN_ZONE = 12

    def __init__(
        self,
        capability_id: str,
        label: str,
        icon: str = "",
        danger: bool = False,
        accent: str = Colors.ACCENT,
        favorite: bool = False,
        composite: bool = False,
        description: str = "",
        machine: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Build the row."""
        super().__init__(parent)
        self.capability_id = capability_id
        self.danger = danger
        self.accent = accent
        self.favorite = favorite
        self.composite = composite
        self.description = description
        self.machine = machine
        self._hovered = False
        self._pin_hovered = False
        self._ready = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(self._tooltip(label))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(9)

        self.icon_label = QLabel(icon or "·")
        self.icon_label.setFixedWidth(18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_SM}px;")

        self.text_label = QLabel(label)
        f = QFont(self.text_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        self.text_label.setFont(f)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        if machine:
            layout.addWidget(ScopeMark())
        layout.addWidget(LevelMark(composite))

        self.run_btn = QPushButton("▶")
        self.run_btn.setFixedSize(26, 26)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.capability_id))
        layout.addWidget(self.run_btn)

        self._restyle()
        self._restyle_run()

    def _tooltip(self, label: str) -> str:
        """Name, what it does, its level and how the row is used."""
        level = (
            "Compuesta · encadena varias atómicas" if self.composite else "Atómica · un solo paso"
        )
        if self.machine:
            level += " · de la máquina, no del repo"
        lines = [f"<b>{label}</b>"]
        if self.description:
            lines.append(self.description)
        lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>{level}</span>")
        lines.append(
            f"<span style='color:{Colors.TEXT_MUTED};'>"
            "Clic para abrir · clic en el filete para marcar favorita</span>"
        )
        return "<br>".join(lines)

    def matches(self, needle: str) -> bool:
        """Return the text the filter looks at.

        The filter also looks at the description: searching 'disco' or
        'caché' should find Limpiar artefactos even if its name does not
        say so.
        """
        return needle in self.text_label.text().lower() or needle in self.description.lower()

    def set_ready(self, value: bool) -> None:
        """Show or hide ▶, for an action that can run at once."""
        if value == self._ready:
            return
        self._ready = value
        self._restyle_run()

    def set_highlighted(self, value: bool) -> None:
        """Set the hover highlight from outside.

        The menu bar search uses it to mark the row chosen with the
        arrows.
        """
        if value == self._hovered:
            return
        self._hovered = value
        self._restyle()
        self.update()

    def _restyle_run(self) -> None:
        self.run_btn.setEnabled(self._ready)
        self.run_btn.setToolTip(
            "Correr con los parámetros guardados de este repo"
            if self._ready
            else "Faltan claves de configuración para correr sin abrir la pestaña"
        )
        color = self.accent if self._ready else Colors.TEXT_MUTED
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {color};
                font-size: {Fonts.SIZE_LG}px; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {tint(self.accent, 0.16)}; }}
            QPushButton:disabled {{ color: {Colors.BORDER_LIGHT}; }}
        """)

    def set_accent(self, accent: str) -> None:
        """Change the stripe's color."""
        self.accent = accent
        self._restyle_run()
        self.update()

    def set_favorite(self, value: bool) -> None:
        """Mark or unmark the favorite."""
        if value == self.favorite:
            return
        self.favorite = value
        self._restyle()
        self.update()

    def _restyle(self) -> None:
        if self.danger:
            color = Colors.ERROR if self._hovered else Colors.TEXT_DIM
        else:
            color = Colors.TEXT if (self._hovered or self.favorite) else Colors.TEXT_DIM
        self.text_label.setStyleSheet(f"background: transparent; color: {color};")

    def _in_pin_zone(self, pos: QPointF) -> bool:
        return 0 <= pos.x() <= self.PIN_ZONE

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self._restyle()
        self.update()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self._pin_hovered = False
        self._restyle()
        self.update()
        super().leaveEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pin_hovered = self._in_pin_zone(event.position())
        if pin_hovered != self._pin_hovered:
            self._pin_hovered = pin_hovered
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        inside = self.rect().contains(pos.toPoint())
        if event.button() == Qt.MouseButton.LeftButton and inside:
            if self._in_pin_zone(pos):
                self.favorite = not self.favorite
                self._restyle()
                self.update()
                self.favorite_toggled.emit(self.capability_id, self.favorite)
            else:
                self.triggered.emit(self.capability_id)
        super().mouseReleaseEvent(event)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        edge = QColor(Colors.ERROR) if self.danger else QColor(self.accent)

        if self._hovered:
            p.fillRect(
                r, _alpha(self.accent, 0.09) if not self.danger else _alpha(Colors.ERROR, 0.08)
            )

        # Accent stripe: always visible and faint if destructive (a
        # permanent warning) or favorite, wider on hover because that is
        # where the click marks it. So a favorite stands out even when
        # seeing everything, and its button needs no separate place.
        if self.danger or self.favorite or self._hovered:
            bar_alpha = (
                0.9
                if (self._hovered and not self._pin_hovered)
                else (0.7 if self.favorite else 0.55)
            )
            if self._pin_hovered:
                bar_alpha = 1.0
            bar_width = 5.0 if self._pin_hovered else 2.5
            p.fillRect(QRectF(0, 3, bar_width, r.height() - 6), _alpha(edge.name(), bar_alpha))
        p.end()
