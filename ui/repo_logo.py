from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QIcon
from PySide6.QtSvg import QSvgRenderer

from ui.theme import Colors
from core import envfile, icons
from core.errors import TaskError

"""
El logo de un repo en la UI: la pestana, la cabecera de la columna derecha, la
bienvenida y el aviso del seguro (ADR-0058).

Es `BRAND_ICON`, el mismo SVG del que salen los iconos de sus apps y de su
ejecutable (ADR-0055). Un repo sin logo lleva la marca de Equipaggio. Uno que
declara un logo que no se puede leer muestra el error, no la marca: la marca
diria que falta un logo cuando lo que hay es una ruta rota.
"""

EQUIPAGGIO = Path(__file__).with_name('assets') / 'equipaggio.png'


@dataclass(frozen=True)
class RepoLogo:
    """Lo que se pinta: la imagen, o el error que impide pintarla."""
    source: Path | None
    error: str = ''


def resolve(repo_path: str) -> RepoLogo:
    """El logo del repo segun su `config.env` de ahora."""
    value = envfile.load_config(repo_path).get('BRAND_ICON', '')
    if not value:
        return RepoLogo(EQUIPAGGIO)
    try:
        svg = icons.brand_file(Path(repo_path), value, 'BRAND_ICON')
    except TaskError as e:
        return RepoLogo(None, str(e))
    if not QSvgRenderer(str(svg)).isValid():
        return RepoLogo(None, f'Qt no pudo leer {svg.name} como SVG.')
    return RepoLogo(svg)


class RepoLogoView(QWidget):
    """El logo pintado en un cuadrado de `size` pixeles.

    Pintado con `QIcon.paint` y no puesto en un `QLabel` como pixmap: asi se
    rasteriza a la densidad del monitor en el que esta, y el SVG sale nitido
    tambien a 150 %.
    """

    def __init__(self, size: int, logo: RepoLogo, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.set_logo(logo)

    def set_logo(self, logo: RepoLogo) -> None:
        self._icon = QIcon(str(logo.source)) if logo.source else None
        self.setToolTip(logo.error)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._icon is not None:
            self._icon.paint(p, self.rect())
            return
        f = QFont(self.font())
        f.setPixelSize(round(self.height() * 0.8))
        p.setFont(f)
        p.setPen(QColor(Colors.ERROR))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, '⚠')
