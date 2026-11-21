"""The sections of the right column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Fonts

# `QWIDGETSIZE_MAX`: what Qt understands as «no height limit».
NO_CAP = 16777215


class _AccordionHeader(QWidget):
    """A section's clickable bar, always visible, open or not.

    It is what keeps all sections visible even if only one fits open.
    """

    clicked = Signal()

    HEIGHT = 30

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        # Repainted when the cursor comes in or goes out.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pal = NEUTRAL

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 12, 0)
        lay.setSpacing(6)

        self.chevron = QLabel("▾")
        self.chevron.setFixedWidth(11)
        self.title = QLabel(title.upper())

        # What the section has to say without opening it («3 de 5
        # protegidos»). Empty by default: not every section has a useful
        # summary.
        self.summary = QLabel("")
        self.summary.setFont(theme.font(Fonts.SIZE_XS))
        self.chevron.setFont(theme.font(Fonts.SIZE_XS))
        self.title.setFont(theme.caption())
        self.warn = False

        lay.addWidget(self.chevron)
        lay.addWidget(self.title)
        self._restyle()
        lay.addStretch(1)
        lay.addWidget(self.summary)

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        # The header and its section's body go on different steps:
        # that separates a section from its neighbor and the label from
        # its content. When both were the same gray, the right column
        # read as one stain.
        theme.SECTION_HEADER.on(self.pal).dress(self, fill=False)
        # The summary is a hint, or a warning when the section asks for
        # attention.
        (theme.WARNING_TEXT if self.warn else theme.HINT).on(self.pal).dress(self.summary)
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the band, or its hover, and the line below."""
        colors = self.palette()
        p = QPainter(self)
        fill = QPalette.ColorRole.Midlight if self.underMouse() else QPalette.ColorRole.Window
        p.fillRect(self.rect(), colors.color(fill))
        p.fillRect(0, self.height() - 1, self.width(), 1, colors.color(QPalette.ColorRole.Dark))
        p.end()

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AccordionSection(QWidget):
    """A header and a collapsible body, like VSCode's sidebar.

    It is meant to live in a vertical `QSplitter`: closed, it sets a
    `maximumHeight` of its header's height, the only thing the splitter
    respects to stop dragging it further. Open, it lets go and its
    container shares out the height (`TabPanel._relayout_right`).

    Tabs were not chosen for this reason: the right panel's sections
    read together. A `ParamsPanel` block may say config keys are missing
    while those keys are in the section below, and tabs would force
    switching between what is being compared.
    """

    toggled = Signal(bool)

    def __init__(
        self, title: str, body: QWidget, expanded: bool = True, parent: QWidget | None = None
    ) -> None:
        """Build the section around its body."""
        super().__init__(parent)
        self.body = body

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = _AccordionHeader(title)
        self.header.clicked.connect(self.toggle)
        root.addWidget(self.header)
        root.addWidget(body, 1)

        self._allotted: int | None = None
        # so `set_expanded` does not leave at once
        self._expanded = not expanded
        self.set_expanded(expanded, announce=False)

    # --- state -------------------------------------------------------
    def is_expanded(self) -> bool:
        """Return whether it is open."""
        return self._expanded

    def set_allotted(self, height: int) -> None:
        """Keep the height `TabPanel._relayout_right` granted.

        It is needed besides `maximumHeight` because `QBoxLayout` shares
        out by `sizeHint` and only crops with the limit: a body asking
        for less than granted, such as anything in a `QScrollArea`,
        stayed at its hint and the spare pixels fell into the column's
        final spring, a dead gap below. Answering the grant here makes
        the hints add up exactly.
        """
        if height == self._allotted:
            return
        self._allotted = height
        self.updateGeometry()

    @override
    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if self._allotted is None:
            return hint
        return QSize(hint.width(), self._allotted)

    def header_height(self) -> int:
        """Return the height of the header alone."""
        return _AccordionHeader.HEIGHT

    def set_expanded(self, value: bool, announce: bool = True) -> None:
        """Open or close it, and tell the listeners if `announce`."""
        if value == self._expanded:
            return
        self._expanded = value
        self.body.setVisible(value)
        self.header.chevron.setText("▾" if value else "▸")
        self.setMinimumHeight(_AccordionHeader.HEIGHT)
        self.setMaximumHeight(NO_CAP if value else _AccordionHeader.HEIGHT)
        if announce:
            self.toggled.emit(value)

    @Slot()
    def toggle(self) -> None:
        """Flip open and closed."""
        self.set_expanded(not self._expanded)

    def set_summary(self, text: str, detail: str = "", warn: bool = False) -> None:
        """Set the summary, its tooltip and whether it warns.

        `warn` paints it in the warning color instead of the hint's:
        the state of «Configuración del repo» when the file is not
        ready, whose detail reads in the tooltip.
        """
        summary = self.header.summary
        summary.setText(text)
        summary.setToolTip(detail)
        self.header.warn = warn
        self.header.set_palette(self.header.pal)

    def set_palette(self, pal: Palette) -> None:
        """Repaint the header.

        Whoever set the body repaints it, since each panel has its own.
        """
        self.header.set_palette(pal)
