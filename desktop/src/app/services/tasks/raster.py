"""The repo's logo as PNG or ICO.

Qt comes in only as an image library (ADR-0055): no application, no
widgets and no signals. App icons (`images.py`) and the executable's
(`builders.py`) use it.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from app.services.errors import TaskError

# The sides of an `.ico`: what Windows asks for Explorer, the taskbar
# and shortcuts.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# The resolution written in the PNG, in dots per meter. Unset, Qt writes
# the monitor's with an open application and 3937 without one: the same
# logo came out with other bytes from the window, and the button rewrote
# icons that had not changed.
_DOTS_PER_METER = 3937


def svg_to_png(svg: Path, side: int) -> bytes:
    """Return the SVG as a square PNG of `side` pixels, antialiased.

    QtSvg implements SVG Tiny 1.2: a logo with filters, masks or CSS
    looks different than in the browser (ADR-0055).
    """
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise TaskError(f"Qt no pudo leer {svg.name} como SVG.")
    box = renderer.viewBoxF()
    # Qt stretches the viewBox to fill the image: a non-square one comes
    # out distorted.
    if abs(box.width() - box.height()) > 1e-6:
        raise TaskError(
            f"{svg.name} no es cuadrado: su viewBox mide {box.width():g}×{box.height():g}."
        )
    image = QImage(side, side, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    image.setDotsPerMeterX(_DOTS_PER_METER)
    image.setDotsPerMeterY(_DOTS_PER_METER)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")  # pyrefly: ignore[no-matching-overload]
    return bytes(buffer.data().data())


def svg_to_ico(svg: Path) -> bytes:
    """Return the SVG as an `.ico` with every side of `ICO_SIZES`.

    Qt writes a one-image ICO; Pillow builds the multi-image one from
    the largest side.
    """
    large = Image.open(io.BytesIO(svg_to_png(svg, max(ICO_SIZES))))
    output = io.BytesIO()
    large.save(output, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    return output.getvalue()
