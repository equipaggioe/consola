from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from app.core import envfile, icons
from app.core.errors import TaskError
from app.theme import Colors

"""
El logo de un repo en la UI: la pestana, la cabecera de la columna derecha, la
bienvenida y el aviso del seguro (ADR-0058).

Es `BRAND_ICON`, el mismo SVG del que salen los iconos de sus apps y de su
ejecutable (ADR-0055). Un repo sin logo lleva la marca de Equipaggio. Uno que
declara un logo que no se puede leer muestra el error, no la marca: la marca
diria que falta un logo cuando lo que hay es una ruta rota.
"""

EQUIPAGGIO = Path(__file__).with_name("assets") / "equipaggio.png"

# Lado al que se rasteriza el logo antes de recortarlo: el de la bienvenida,
# 64 px, a 200 % y con margen.
_RASTER = 256
# Alfa desde el que un pixel cuenta como dibujo al recortar: por debajo es la
# franja del antialiasing.
_VISIBLE_ALPHA = 8


@dataclass(frozen=True)
class RepoLogo:
    """Lo que se pinta: la imagen, o el error que impide pintarla."""

    source: Path | None
    error: str = ""


def resolve(repo_path: str) -> RepoLogo:
    """El logo del repo segun su `config.env` de ahora."""
    value = envfile.load_config(repo_path).get("BRAND_ICON", "")
    if not value:
        return RepoLogo(EQUIPAGGIO)
    try:
        svg = icons.brand_file(Path(repo_path), value, "BRAND_ICON")
    except TaskError as e:
        return RepoLogo(None, str(e))
    if not QSvgRenderer(str(svg)).isValid():
        return RepoLogo(None, f"Qt no pudo leer {svg.name} como SVG.")
    return RepoLogo(svg)


def trimmed(source: Path) -> QImage:
    """El logo rasterizado y recortado a lo que se dibuja.

    El margen transparente es del diseno del logo, no de la UI: el de vettore
    deja 4 de 64 unidades por lado para el recorte de los iconos de app, y el
    PNG de Equipaggio es mas angosto que su lienzo. Sin recortarlo, esos dos
    salian mas chicos que los que llenan su cuadrado.
    """
    imagen = QImage(_RASTER, _RASTER, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    QIcon(str(source)).paint(pintor, imagen.rect())
    pintor.end()
    # ARGB32 va en memoria como BGRA: el alfa es el cuarto byte de cada pixel.
    alfa = bytes(imagen.constBits())[3::4]
    filas = [
        y for y in range(_RASTER) if max(alfa[y * _RASTER : (y + 1) * _RASTER]) > _VISIBLE_ALPHA
    ]
    columnas = [x for x in range(_RASTER) if max(alfa[x::_RASTER]) > _VISIBLE_ALPHA]
    if not filas:
        return imagen
    return imagen.copy(
        QRect(columnas[0], filas[0], columnas[-1] - columnas[0] + 1, filas[-1] - filas[0] + 1)
    )


class RepoLogoView(QWidget):
    """El logo en un cuadrado de `size` pixeles, llenandolo por su lado largo.

    Se escala al pintar, a la densidad del monitor en el que esta: puesto en un
    `QLabel` como pixmap, a 150 % saldria borroso.
    """

    def __init__(self, size: int, logo: RepoLogo, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.set_logo(logo)

    def set_logo(self, logo: RepoLogo) -> None:
        self._image = trimmed(logo.source) if logo.source else None
        self._scaled: QImage | None = None
        self.setToolTip(logo.error)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._image is not None:
            dpr = self.devicePixelRatioF()
            lado = round(self.width() * dpr)
            if self._scaled is None or self._scaled.devicePixelRatio() != dpr:
                # `scaled` promedia los pixeles de origen; dibujar la imagen
                # grande en un rectangulo chico solo muestrea, y dentaba.
                self._scaled = self._image.scaled(
                    QSize(lado, lado),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._scaled.setDevicePixelRatio(dpr)
            caja = QRectF(0, 0, self._scaled.width() / dpr, self._scaled.height() / dpr)
            caja.moveCenter(QRectF(self.rect()).center())
            p.drawImage(caja, self._scaled)
            return
        f = QFont(self.font())
        f.setPixelSize(round(self.height() * 0.8))
        p.setFont(f)
        p.setPen(QColor(Colors.ERROR))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "⚠")
