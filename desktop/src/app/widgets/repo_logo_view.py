"""A repo's logo, painted at a size (ADR-0058)."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from app.services.repo_logo import RepoLogo, trimmed
from app.theme import Colors


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
