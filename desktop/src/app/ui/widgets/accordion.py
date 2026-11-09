"""The sections of the right column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.theme import Colors, Fonts
from app.ui.palettes import NEUTRAL, Palette

# `QWIDGETSIZE_MAX`: what Qt understands as «no height limit».
NO_CAP = 16777215


class AccordionHeader(QWidget):
    """A section's clickable bar, always visible, open or not.

    It is what keeps all sections visible even if only one fits open.
    """

    clicked = Signal()

    HEIGHT = 30

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        self.setObjectName("accordionHeader")
        # A *subclassed* QWidget does not paint its style sheet's
        # background without this; the plain QWidgets in the rest of the
        # file do.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pal = NEUTRAL
        self._restyle()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 12, 0)
        lay.setSpacing(6)

        self.chevron = QLabel("▾")
        self.chevron.setFixedWidth(11)
        self.chevron.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.title = QLabel(title.upper())
        self.title.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.1px;"
        )

        # What the section has to say without opening it («3 de 5
        # protegidos»). Empty by default: not every section has a useful
        # summary.
        self.summary = QLabel("")
        self.summary.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )

        lay.addWidget(self.chevron)
        lay.addWidget(self.title)
        lay.addStretch(1)
        lay.addWidget(self.summary)

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        # The header goes one step LIGHTER than its section's body
        # (`pal.panel`): that separates a section from its neighbor and
        # the label from its content. When both were the same gray, the
        # right column read as one stain.
        self.setStyleSheet(f"""
            QWidget#accordionHeader {{
                background: {self.pal.surface};
                border-bottom: 1px solid {self.pal.border};
            }}
            QWidget#accordionHeader:hover {{ background: {self.pal.surface_hover}; }}
        """)

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

        self.header = AccordionHeader(title)
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
        return AccordionHeader.HEIGHT

    def set_expanded(self, value: bool, announce: bool = True) -> None:
        """Open or close it, and tell the listeners if `announce`."""
        if value == self._expanded:
            return
        self._expanded = value
        self.body.setVisible(value)
        self.header.chevron.setText("▾" if value else "▸")
        self.setMinimumHeight(AccordionHeader.HEIGHT)
        self.setMaximumHeight(NO_CAP if value else AccordionHeader.HEIGHT)
        if announce:
            self.toggled.emit(value)

    def toggle(self) -> None:
        """Flip open and closed."""
        self.set_expanded(not self._expanded)

    def set_summary(self, text: str, detail: str = "", warn: bool = False) -> None:
        """Set the summary, its tooltip and whether it warns.

        `warn` paints it in `Colors.WARNING` instead of the muted gray:
        the state of «Configuración del repo» when the file is not
        ready, whose detail reads in the tooltip.
        """
        summary = self.header.summary
        summary.setText(text)
        summary.setToolTip(detail)
        color = Colors.WARNING if warn else Colors.TEXT_MUTED
        summary.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )

    def set_palette(self, pal: Palette) -> None:
        """Repaint the header.

        Whoever set the body repaints it, since each panel has its own.
        """
        self.header.set_palette(pal)


class SectionResizeGrip(QWidget):
    """A thin bar between two open sections of the accordion.

    Dragging it shares the height by hand: what the upper section gains,
    the rest lose (`TabPanel._resize_section`). A double click returns
    to the automatic sharing. It shows only when there is something to
    negotiate with: its section open and at least one open below.
    """

    pressed = Signal()  # a drag starts: resync with reality
    # px moved since the last event (+ = grow the upper section)
    dragged = Signal(int)
    reset = Signal()

    HEIGHT = 7

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        self.setObjectName("sectionGrip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.SplitVCursor)
        self.pal = NEUTRAL
        self._restyle()
        self._last_y: float | None = None

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(f"""
            QWidget#sectionGrip {{
                background: {self.pal.surface};
                border-bottom: 1px solid {self.pal.border};
            }}
            QWidget#sectionGrip:hover {{ background: {self.pal.surface_hover}; }}
        """)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_y = event.globalPosition().y()
            self.pressed.emit()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_y is None:
            return
        y = event.globalPosition().y()
        delta = int(y - self._last_y)
        if delta:
            self._last_y = y
            self.dragged.emit(delta)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_y = None

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.reset.emit()
