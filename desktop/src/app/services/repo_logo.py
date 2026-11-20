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

from PySide6.QtCore import QCoreApplication, QRect, Qt
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from app.services import envfile, icons
from app.services.errors import TaskError

EQUIPAGGIO = ":/assets/equipaggio.png"

# The side the logo rasterizes to before cropping: the welcome's, 64 px,
# at 200 % with a margin.
_RASTER = 256
# The alpha from which a pixel counts as drawing when cropping: below it
# is the antialiasing fringe.
_VISIBLE_ALPHA = 8


@dataclass(frozen=True)
class RepoLogo:
    """What gets painted: the image, or the error that prevents it."""

    source: str | None
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
        return RepoLogo(
            None,
            QCoreApplication.translate("repo_logo", "Qt no pudo leer {0} como SVG.").format(
                svg.name
            ),
        )
    return RepoLogo(str(svg))


def trimmed(source: str) -> QImage:
    """Return the logo rasterized and cropped to what is drawn.

    The transparent margin belongs to the logo's design, not to the UI:
    a logo may leave 4 of 64 units per side for app icon cropping, and
    the Equipaggio PNG is narrower than its canvas. Without cropping,
    those came out smaller than the ones that fill their square.
    """
    image = QImage(_RASTER, _RASTER, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QIcon(source).paint(painter, image.rect())
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
