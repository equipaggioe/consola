"""Rasterize the brand's diamond to `src/app/icon.png`.

From `desktop/`: `uv run python scripts/icon.py`. It paints the
diamond of the title bar, at 1024 × 1024 px and in the accent, so the
app's icon is the same drawing and not a copy of its geometry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from app.theme import Colors
from app.widgets.title_bar import _Diamond

ICON = Path(__file__).resolve().parents[1] / "src" / "app" / "icon.png"
SIDE = 1024


def main() -> None:
    """Write the icon."""
    QApplication(sys.argv)
    diamond = _Diamond()
    diamond.set_color(Colors.PRIMARY)
    image = QImage(SIDE, SIDE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    # The widget paints in its logical pixels: the ratio scales them to
    # the icon's side, so the stroke stays a vector one. Without the
    # window's background: the icon is transparent around the diamond.
    image.setDevicePixelRatio(SIDE / diamond.width())
    diamond.render(image, QPoint(), QRegion(), QWidget.RenderFlag(0))
    image.setDevicePixelRatio(1)
    if not image.save(str(ICON)):
        raise OSError(f"Qt could not write {ICON}")


if __name__ == "__main__":
    main()
