from __future__ import annotations
import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from ..errors import TaskError

"""
El logo del repo como PNG o como ICO.

Qt entra aca solo como biblioteca de imagenes (ADR-0055): sin aplicacion, sin
widgets y sin senales. Lo usan los iconos de las apps (`images.py`) y el del
ejecutable (`builders.py`).
"""

# Los lados que lleva un `.ico`: los que pide Windows para el explorador, la
# barra de tareas y los accesos directos.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def svg_to_png(svg: Path, lado: int) -> bytes:
    """El SVG como PNG cuadrado de `lado` pixeles, con antialiasing.

    QtSvg implementa SVG Tiny 1.2: un logo con filtros, mascaras o CSS sale
    distinto que en el navegador (ADR-0055).
    """
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise TaskError(f'Qt no pudo leer {svg.name} como SVG.')
    caja = renderer.viewBoxF()
    # Qt estira el viewBox hasta llenar la imagen: uno que no es cuadrado sale
    # deformado.
    if abs(caja.width() - caja.height()) > 1e-6:
        raise TaskError(f'{svg.name} no es cuadrado: su viewBox mide '
                        f'{caja.width():g}×{caja.height():g}.')
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(pintor)
    pintor.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(buffer, 'PNG')
    return bytes(buffer.data())


def svg_to_ico(svg: Path) -> bytes:
    """El SVG como `.ico` con todos los lados de `ICO_SIZES`.

    Qt escribe un ICO de una sola imagen; Pillow arma el de varias a partir
    del lado mas grande.
    """
    grande = Image.open(io.BytesIO(svg_to_png(svg, max(ICO_SIZES))))
    salida = io.BytesIO()
    grande.save(salida, format='ICO', sizes=[(n, n) for n in ICO_SIZES])
    return salida.getvalue()
