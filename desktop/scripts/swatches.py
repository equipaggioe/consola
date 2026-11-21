"""Show the colors of each role and part, to choose in `theme.py`.

From `desktop/`: `uv run python scripts/swatches.py <theme>`, with one
of the eight theme keys (`blue`, `green`…). The roles go in the eight
themes; the parts, painted in the one given.

It only shows: what changes a part's color is its role in
`theme.py`. Everything is read from the code when it opens, so it
never lags behind the table.
"""

from __future__ import annotations

import argparse
import sys
from typing import override

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import palettes
from app.services.palettes import Palette
from app.theme import Fonts, Layer, Look, Role


class _Square(QWidget):
    """A box filled with a color, framed in the outline of the theme."""

    def __init__(self, color: str, side: int) -> None:
        """Build the box, with its hex in the tooltip."""
        super().__init__()
        self.color = color
        self.setFixedSize(side, side)
        self.setToolTip(color)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self.palette().color(QPalette.ColorRole.Dark))
        p.setBrush(QBrush(self.color))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        p.end()


def _square(color: str, side: int = 16) -> QWidget:
    """Return a box filled with `color`, its hex in the tooltip."""
    return _Square(color, side)


def _text(text: str, color: str, size: int = Fonts.SIZE_XS, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setFont(theme.font(size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    theme.ink(label, color)
    return label


def _name(slot: Role | Layer) -> str:
    """Return a role by its name, and a layer by its two roles."""
    if isinstance(slot, Layer):
        return f"{slot.over.name} {round(slot.opacity * 100)} % / {slot.base.name}"
    return slot.name


class SwatchesDialog(QDialog):
    """Roles in the eight themes, and the parts in this repo's."""

    def __init__(self, pal: Palette, parent: QWidget | None = None) -> None:
        """Build both tables, painted with `pal`."""
        super().__init__(parent)
        self.pal = pal
        self.setWindowTitle(f"Roles y partes · {pal.label}")
        self.resize(1040, 760)
        dialog = theme.DIALOG.on(pal)
        dialog.dress(self)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(20, 16, 20, 20)
        lay.setSpacing(10)
        lay.addWidget(_text("ROLES", dialog.fg, Fonts.SIZE_SM, bold=True))
        lay.addWidget(self._roles())
        lay.addSpacing(14)
        lay.addWidget(_text(f"PARTES · tema {pal.label}", dialog.fg, Fonts.SIZE_SM, bold=True))
        lay.addWidget(self._parts())
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _roles(self) -> QWidget:
        """Return the grid: a row per role, a column per theme.

        This repo's theme goes in bold: it is the one the parts below
        are painted with.
        """
        dialog = theme.DIALOG.on(self.pal)
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        themes = list(palettes.THEMES.values())
        for col, other in enumerate(themes, start=1):
            mine = other.key == self.pal.key
            grid.addWidget(_text(other.label, other.accent, bold=mine), 0, col)
        for row, role in enumerate(Role, start=1):
            grid.addWidget(_text(f"Role.{role.name}", dialog.fg), row, 0)
            for col, other in enumerate(themes, start=1):
                hex_color = theme.color(role, other)
                cell = QHBoxLayout()
                cell.setSpacing(6)
                cell.addWidget(_square(hex_color))
                cell.addWidget(_text(hex_color, dialog.fg, bold=other.key == self.pal.key))
                cell.addStretch(1)
                grid.addLayout(cell, row, col)
        return grid_box

    def _parts(self) -> QWidget:
        """Return a row per part: its sample and each slot's role."""
        dialog = theme.DIALOG.on(self.pal)
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        looks = [(n, v) for n, v in vars(theme).items() if isinstance(v, Look)]
        for row, (name, look) in enumerate(looks):
            grid.addWidget(_text(name, dialog.fg, bold=True), row, 0)
            grid.addWidget(self._sample(look), row, 1)
            slots = QHBoxLayout()
            slots.setSpacing(6)
            for slot, role in look.slots().items():
                slots.addWidget(_square(theme.color(role, self.pal), 14))
                slots.addWidget(_text(f"{slot} = {_name(role)}", dialog.fg))
                slots.addSpacing(10)
            slots.addStretch(1)
            grid.addLayout(slots, row, 2)
        grid.setColumnStretch(2, 1)
        return grid_box

    def _sample(self, look: Look) -> QLabel:
        """Return «Aa» painted as the part paints.

        With its palette, as the widgets take it: a slot the part does
        not declare is left out, and with no `bg` it shows the dialog's
        background, as the part shows what is behind.
        """
        sample = QLabel("Aa")
        sample.setFixedSize(64, 26)
        sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sample.setFont(theme.font(Fonts.SIZE_SM, QFont.Weight.DemiBold))
        look.on(self.pal).dress(sample)
        if "fg" not in look.slots():
            theme.ink(sample, "transparent")
        if "border" in look.slots():
            sample.setFrameShape(QFrame.Shape.StyledPanel)
        return sample


def main() -> None:
    """Open the window with the theme given on the command line."""
    parser = argparse.ArgumentParser(description="Roles y partes de theme.py")
    parser.add_argument("theme", choices=list(palettes.THEMES), help="the parts' theme")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    theme.apply(app)
    SwatchesDialog(palettes.THEMES[args.theme]).show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
