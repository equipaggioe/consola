"""A repo's logo in the UI (ADR-0058).

It appears on the tab, the right column's header, the welcome screen and
the guard's notice. It is `BRAND_ICON`, the same SVG its apps' and
executable's icons come from (ADR-0055). A repo without a logo carries
the Equipaggio mark. One that declares an unreadable logo shows the
error, not the mark: the mark would say a logo is missing when what
exists is a broken path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import override

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPaintEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from app.services import envfile, icons
from app.services.errors import TaskError
from app.theme import Colors

EQUIPAGGIO = Path(__file__).resolve().parents[1] / "assets" / "equipaggio.png"

# The side the logo rasterizes to before cropping: the welcome's, 64 px,
# at 200 % with a margin.
_RASTER = 256
# The alpha from which a pixel counts as drawing when cropping: below it
# is the antialiasing fringe.
_VISIBLE_ALPHA = 8


@dataclass(frozen=True)
class RepoLogo:
    """What gets painted: the image, or the error that prevents it."""

    source: Path | None
    error: str = ""


def resolve(repo_path: str) -> RepoLogo:
    """Return the repo's logo according to its current `config.env`."""
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
    """Return the logo rasterized and cropped to what is drawn.

    The transparent margin belongs to the logo's design, not to the UI:
    a logo may leave 4 of 64 units per side for app icon cropping, and
    the Equipaggio PNG is narrower than its canvas. Without cropping,
    those came out smaller than the ones that fill their square.
    """
    image = QImage(_RASTER, _RASTER, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QIcon(str(source)).paint(painter, image.rect())
    painter.end()
    # ARGB32 is BGRA in memory: alpha is each pixel's fourth byte.
    alpha = bytes(image.constBits())[3::4]
    rows = [
        y for y in range(_RASTER) if max(alpha[y * _RASTER : (y + 1) * _RASTER]) > _VISIBLE_ALPHA
    ]
    columns = [x for x in range(_RASTER) if max(alpha[x::_RASTER]) > _VISIBLE_ALPHA]
    if not rows:
        return image
    return image.copy(
        QRect(columns[0], rows[0], columns[-1] - columns[0] + 1, rows[-1] - rows[0] + 1)
    )


class RepoLogoView(QWidget):
    """The logo in a square of `size` pixels, filled by its long side.

    It scales when painting, at the density of the monitor it is on: set
    on a `QLabel` as a pixmap, at 150 % it would blur.
    """

    def __init__(self, size: int, logo: RepoLogo, parent: QWidget | None = None) -> None:
        """Keep the logo and the square's side."""
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.set_logo(logo)

    def set_logo(self, logo: RepoLogo) -> None:
        """Show another logo."""
        self._image = trimmed(logo.source) if logo.source else None
        self._scaled: QImage | None = None
        self.setToolTip(logo.error)
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._image is not None:
            dpr = self.devicePixelRatioF()
            side = round(self.width() * dpr)
            if self._scaled is None or self._scaled.devicePixelRatio() != dpr:
                # `scaled` averages the source pixels; drawing the large
                # image in a small rectangle only samples, and it came
                # out jagged.
                self._scaled = self._image.scaled(
                    QSize(side, side),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._scaled.setDevicePixelRatio(dpr)
            box = QRectF(0, 0, self._scaled.width() / dpr, self._scaled.height() / dpr)
            box.moveCenter(QRectF(self.rect()).center())
            p.drawImage(box, self._scaled)
            return
        f = QFont(self.font())
        f.setPixelSize(round(self.height() * 0.8))
        p.setFont(f)
        p.setPen(QColor(Colors.ERROR))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "⚠")
