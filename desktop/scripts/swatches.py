"""Show the colors of each role and part, to choose in `ui/parts.py`.

From `desktop/`: `uv run python scripts/swatches.py <theme>`, with one
of the eight theme keys (`blue`, `green`…). The roles go in the eight
themes; the parts, painted in the one given.

It only shows: what changes a part's color is its role in
`ui/parts.py`. Everything is read from the code when it opens, so it
never lags behind the table.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.theme import Fonts, apply_theme
from app.ui import palettes, parts
from app.ui.palettes import Palette
from app.ui.parts import Look, Role


def _square(color: str, side: int = 16) -> QLabel:
    """Return a box filled with `color`, its hex in the tooltip."""
    box = QLabel()
    box.setFixedSize(side, side)
    box.setToolTip(color)
    box.setStyleSheet(
        f"background: {color}; border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 3px;"
    )
    return box


def _text(text: str, color: str, size: int = Fonts.SIZE_XS, bold: bool = False) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"background: transparent; color: {color}; font-size: {size}px;"
        f"font-weight: {700 if bold else 400};"
    )
    return label


class SwatchesDialog(QDialog):
    """Roles in the eight themes, and the parts in this repo's."""

    def __init__(self, pal: Palette, parent: QWidget | None = None) -> None:
        """Build both tables, painted with `pal`."""
        super().__init__(parent)
        self.pal = pal
        self.setWindowTitle(f"Roles y partes · {pal.label}")
        self.resize(1040, 760)
        dialog = parts.DIALOG.on(pal)
        self.setStyleSheet(f"QDialog {{ background: {dialog.bg}; }}")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
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
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {dialog.bg}; width: 8px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _roles(self) -> QWidget:
        """Return the grid: a row per role, a column per theme.

        This repo's theme goes in bold: it is the one the parts below
        are painted with.
        """
        dialog = parts.DIALOG.on(self.pal)
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        themes = list(palettes.THEMES.values())
        for col, theme in enumerate(themes, start=1):
            mine = theme.key == self.pal.key
            grid.addWidget(_text(theme.label, theme.accent, bold=mine), 0, col)
        for row, role in enumerate(Role, start=1):
            grid.addWidget(_text(f"Role.{role.name}", dialog.fg), row, 0)
            for col, theme in enumerate(themes, start=1):
                hex_color = parts.color(role, theme)
                cell = QHBoxLayout()
                cell.setSpacing(6)
                cell.addWidget(_square(hex_color))
                cell.addWidget(_text(hex_color, dialog.fg, bold=theme.key == self.pal.key))
                cell.addStretch(1)
                grid.addLayout(cell, row, col)
        return grid_box

    def _parts(self) -> QWidget:
        """Return a row per part: its sample and each slot's role."""
        dialog = parts.DIALOG.on(self.pal)
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        looks = [(n, v) for n, v in vars(parts).items() if isinstance(v, Look)]
        for row, (name, look) in enumerate(looks):
            grid.addWidget(_text(name, dialog.fg, bold=True), row, 0)
            grid.addWidget(self._sample(look), row, 1)
            slots = QHBoxLayout()
            slots.setSpacing(6)
            for slot, role in look.slots().items():
                slots.addWidget(_square(parts.color(role, self.pal), 14))
                slots.addWidget(_text(f"{slot} = {role.name}", dialog.fg))
                slots.addSpacing(10)
            slots.addStretch(1)
            grid.addLayout(slots, row, 2)
        grid.setColumnStretch(2, 1)
        return grid_box

    def _sample(self, look: Look) -> QLabel:
        """Return «Aa» painted as the part paints.

        A slot the part does not declare is left out: with no `bg` it
        shows the dialog's background, as the part shows what is behind.
        """
        paint = look.on(self.pal)
        slots = look.slots()
        css = "border-radius: 4px; padding: 3px 10px;"
        css += f"background: {paint.bg};" if "bg" in slots else "background: transparent;"
        css += f"color: {paint.fg};" if "fg" in slots else "color: transparent;"
        css += f"border: 1px solid {paint.border};" if "border" in slots else "border: none;"
        sample = QLabel("Aa")
        sample.setFixedSize(64, 26)
        sample.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sample.setStyleSheet(css + f"font-size: {Fonts.SIZE_SM}px; font-weight: 600;")
        return sample


def main() -> None:
    """Open the window with the theme given on the command line."""
    parser = argparse.ArgumentParser(description="Roles y partes de ui/parts.py")
    parser.add_argument("theme", choices=list(palettes.THEMES), help="the parts' theme")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    SwatchesDialog(palettes.THEMES[args.theme]).show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
