from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from app.core.errors import TaskError

"""
El logo del repo como PNG o como ICO.

Qt entra aca solo como biblioteca de imagenes (ADR-0055): sin aplicacion, sin
widgets y sin senales. Lo usan los iconos de las apps (`images.py`) y el del
ejecutable (`builders.py`).
"""

# Los lados que lleva un `.ico`: los que pide Windows para el explorador, la
# barra de tareas y los accesos directos.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# La resolucion que se anota en el PNG, en puntos por metro. Sin fijarla, Qt
# anota la del monitor cuando hay una aplicacion abierta y 3937 cuando no: el
# mismo logo salia con otros bytes desde la ventana, y el boton reescribia
# iconos que no cambiaron.
_DOTS_PER_METER = 3937


def svg_to_png(svg: Path, side: int) -> bytes:
    """El SVG como PNG cuadrado de `lado` pixeles, con antialiasing.

    QtSvg implementa SVG Tiny 1.2: un logo con filtros, mascaras o CSS sale
    distinto que en el navegador (ADR-0055).
    """
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise TaskError(f"Qt no pudo leer {svg.name} como SVG.")
    box = renderer.viewBoxF()
    # Qt estira el viewBox hasta llenar la imagen: uno que no es cuadrado sale
    # deformado.
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
    """El SVG como `.ico` con todos los lados de `ICO_SIZES`.

    Qt escribe un ICO de una sola imagen; Pillow arma el de varias a partir
    del lado mas grande.
    """
    large = Image.open(io.BytesIO(svg_to_png(svg, max(ICO_SIZES))))
    output = io.BytesIO()
    large.save(output, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    return output.getvalue()
