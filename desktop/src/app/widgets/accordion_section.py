"""The sections of the right column."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QObject, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QAccessible,
    QAccessibleActionInterface,
    QAccessibleInterface,
    QAccessibleStateChangeEvent,
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
)
from PySide6.QtWidgets import QAccessibleWidget, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Fonts
from app.widgets.reorderable_tab import pressed


class _AccordionHeader(QWidget):
    """A section's clickable bar, always visible, open or not.

    It is what keeps all sections visible even if only one fits open.
    Tab reaches it and Space or Enter folds or unfolds it, as a click;
    the menu key opens the menu of its right click. To assistive
    technology it is a button that says whether its section is open.
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
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(title)
        self.pal = NEUTRAL
        self.expanded = True

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
        if self.hasFocus():
            theme.ring(p, QRectF(self.rect()), colors.color(QPalette.ColorRole.Highlight))
        p.end()

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if pressed(event):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    @override
    def focusInEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusInEvent(event)

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.update()
        super().focusOutEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class AccordionSection(QWidget):
    """A header and a collapsible body, like VSCode's sidebar.

    Open, the body shows whole, with the height its content asks for:
    the column that holds the sections is the one that scrolls
    (`TabPanel.right_scroll`), so no section scrolls on its own. Closed,
    only the header shows.
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
        root.addWidget(body)

        # so `set_expanded` does not leave at once
        self._expanded = not expanded
        self.set_expanded(expanded, announce=False)

    # --- state -------------------------------------------------------
    def is_expanded(self) -> bool:
        """Return whether it is open."""
        return self._expanded

    def set_expanded(self, value: bool, announce: bool = True) -> None:
        """Open or close it, and tell the listeners if `announce`."""
        if value == self._expanded:
            return
        self._expanded = value
        self.body.setVisible(value)
        self.header.expanded = value
        self.header.chevron.setText("▾" if value else "▸")
        changed = QAccessible.State()
        # The stubs of PySide6 6.12 declare each state `...` with a
        # type comment, which Pyrefly does not read.
        changed.expanded = True  # pyrefly: ignore[bad-assignment]
        changed.collapsed = True  # pyrefly: ignore[bad-assignment]
        QAccessible.updateAccessibility(QAccessibleStateChangeEvent(self.header, changed))
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


class _Accessible(QAccessibleWidget):
    """A header as a button that opens and closes its section."""

    def __init__(self, header: _AccordionHeader) -> None:
        """Give the header the button role."""
        super().__init__(header, QAccessible.Role.Button)
        self.header = header

    @override
    def state(self) -> QAccessible.State:
        state = super().state()
        # The stubs of PySide6 6.12 declare each state `...` with a
        # type comment, which Pyrefly does not read.
        state.expandable = True  # pyrefly: ignore[bad-assignment]
        state.expanded = self.header.expanded  # pyrefly: ignore[bad-assignment]
        state.collapsed = not self.header.expanded  # pyrefly: ignore[bad-assignment]
        return state

    @override
    def actionNames(self) -> list[str]:
        return [QAccessibleActionInterface.pressAction(), *super().actionNames()]

    @override
    def doAction(self, actionName: str) -> None:
        if actionName == QAccessibleActionInterface.pressAction():
            self.header.clicked.emit()
        else:
            super().doAction(actionName)


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of a header, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, _AccordionHeader) else None


QAccessible.installFactory(_interface)
