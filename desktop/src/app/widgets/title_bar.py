"""The window's title row."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAccessible,
    QAccessibleInterface,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QAccessibleWidget, QHBoxLayout, QLabel, QPushButton, QWidget

from app import theme
from app.services.language import QT_TRANSLATE_NOOP
from app.services.palettes import NEUTRAL, Palette
from app.theme import Colors, Fonts, tint
from app.widgets.project_tab import ProjectTab


class _Diamond(QWidget):
    """The brand's diamond, painted.

    As a character (`◇`) it is a one-pixel stroke lost against the
    accent at this scale, and bold does not thicken it: it is a
    geometric symbol, not a letter. Painted, it can have the weight the
    brand needs.
    """

    SIZE = 17
    STROKE = 2.2

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the diamond."""
        super().__init__(parent)
        self.setFixedSize(self.SIZE + 4, self.SIZE + 4)
        self._color = Colors.INK

    def set_color(self, color: str) -> None:
        """Change its color."""
        self._color = color
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color)
        pen.setWidthF(self.STROKE)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = QRectF(self.rect()).center()
        h = self.SIZE / 2 - self.STROKE / 2
        diamond = QPolygonF(
            [
                QPointF(c.x(), c.y() - h),
                QPointF(c.x() + h, c.y()),
                QPointF(c.x(), c.y() + h),
                QPointF(c.x() - h, c.y()),
            ]
        )
        p.drawPolygon(diamond)
        p.end()


class _BrandMark(QWidget):
    """The app's brand: the diamond and `CONSOLA` on the title bar.

    The bar is painted in the active repo's color. It opens the bar, to
    the left of the repo tabs: where a browser puts its menu button or
    logo.

    With no plate to separate it, weight holds it up: the diamond has
    its own stroke and the name goes in print black.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the brand."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(9)

        self.diamond = _Diamond()
        self.title = QLabel("CONSOLA")
        self.title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self.diamond)
        layout.addWidget(self.title)
        self.set_palette(NEUTRAL)

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        fg = theme.TITLE_BAR.on(pal).fg
        self.diamond.set_color(fg)
        self.title.setStyleSheet(f"""
            background: transparent;
            color: {fg};
            font-size: {Fonts.SIZE_SM}px;
            font-weight: 900;
            letter-spacing: 3px;
        """)


class _WindowButton(QPushButton):
    """Minimize, maximize and close, drawn by us.

    The window is frameless (`Qt.FramelessWindowHint`) so the repo tabs
    and the brand share a row with these three buttons; in exchange,
    they have to be supplied.

    The glyph is **painted**, not written. As text («─», «□», «✕») they
    were one-pixel strokes lost against the accent, and bold does not
    thicken box-drawing characters. Painted, all three have the same
    weight and size.
    """

    WIDTH = 46
    NAMES = {
        "min": QT_TRANSLATE_NOOP("_WindowButton", "Minimizar"),
        "max": QT_TRANSLATE_NOOP("_WindowButton", "Maximizar"),
        "close": QT_TRANSLATE_NOOP("_WindowButton", "Cerrar"),
    }
    STROKE = 1.6
    GLYPH = 11  # side of the square or the cross, in pixels

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        """Build the button of that kind."""
        super().__init__(parent)
        self.kind = kind  # 'min' | 'max' | 'close'
        # The glyph is painted: the name says it in words.
        self.setAccessibleName(QCoreApplication.translate("_WindowButton", self.NAMES[kind]))
        self.maximized = False
        self.setFixedWidth(self.WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._fg = Colors.TEXT_DIM
        self.set_foreground(Colors.TEXT_DIM)

    def set_foreground(self, color: str) -> None:
        """Set the stroke to the legible color over the bar.

        The hover background comes from that same color and not a fixed
        gray: a dark gray over a light bar was a stain unlike anything
        else in the window. Close's is red: there the color IS the
        warning.
        """
        self._fg = color
        hover = Colors.ERROR if self.kind == "close" else tint(color, 0.16)
        self.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; padding: 0; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {
            tint(Colors.ERROR if self.kind == "close" else color, 0.32)
        }; }}
        """)
        self.update()

    def set_maximized(self, value: bool) -> None:
        """Set whether the window is maximized."""
        self.maximized = value
        self.setAccessibleName(
            QCoreApplication.translate("_WindowButton", "Restaurar")
            if value
            else QCoreApplication.translate("_WindowButton", self.NAMES["max"])
        )
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)  # the sheet sets the hover background
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = Colors.ON_ERROR if (self.kind == "close" and self.underMouse()) else self._fg
        pen = QPen(color)
        pen.setWidthF(self.STROKE)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        c = QRectF(self.rect()).center()
        h = self.GLYPH / 2
        if self.kind == "min":
            p.drawLine(QPointF(c.x() - h, c.y()), QPointF(c.x() + h, c.y()))
        elif self.kind == "max":
            if self.maximized:
                # Restore: the back sheet peeking from above and to the
                # right.
                p.drawRect(QRectF(c.x() - h, c.y() - h + 2.5, self.GLYPH - 2.5, self.GLYPH - 2.5))
                p.drawLine(
                    QPointF(c.x() - h + 2.5, c.y() - h + 2.5), QPointF(c.x() - h + 2.5, c.y() - h)
                )
                p.drawLine(QPointF(c.x() - h + 2.5, c.y() - h), QPointF(c.x() + h, c.y() - h))
                p.drawLine(QPointF(c.x() + h, c.y() - h), QPointF(c.x() + h, c.y() + h - 2.5))
            else:
                p.drawRect(QRectF(c.x() - h, c.y() - h, self.GLYPH, self.GLYPH))
        else:
            p.drawLine(QPointF(c.x() - h, c.y() - h), QPointF(c.x() + h, c.y() + h))
            p.drawLine(QPointF(c.x() + h, c.y() - h), QPointF(c.x() - h, c.y() + h))
        p.end()

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self.update()
        super().leaveEvent(event)


class TitleBar(QWidget):
    """The window's title row, like a browser's.

    The brand, the repo tabs and the window buttons, all on the top
    edge.

    An open repository is what a browser tab is: the whole context of
    what shows below. Placing them here and not on a strip of their own
    says exactly that, and gives one row of height back to the window.

    The gap the tabs leave is a drag zone: `ProjectTabBar` does not take
    the mouse outside its tabs, so the event comes up here.
    """

    HEIGHT = ProjectTab.HEIGHT

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, tabs: QWidget, parent: QWidget | None = None) -> None:
        """Build the row."""
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        # The whole row paints in the active repo's color: it signals
        # which repo is open, instead of a line under its tab.
        self.fill = theme.TITLE_BAR.on(NEUTRAL).bg
        self._press_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.brand = _BrandMark()
        layout.addWidget(self.brand)

        self.tabs = tabs
        layout.addWidget(self.tabs, 1)

        self.min_btn = _WindowButton("min")
        self.max_btn = _WindowButton("max")
        self.close_btn = _WindowButton("close")
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedHeight(self.HEIGHT)
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        self.max_btn.clicked.connect(self.maximize_requested.emit)
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)
        self.set_palette(NEUTRAL)

    # --- state ---
    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        paint = theme.TITLE_BAR.on(pal)
        self.fill = paint.bg
        self.brand.set_palette(pal)
        fg = paint.fg
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.set_foreground(fg)
        self.update()

    def set_maximized(self, value: bool) -> None:
        """Set whether the window is maximized."""
        self.max_btn.set_maximized(value)
        self.max_btn.setToolTip(
            QCoreApplication.translate("TitleBar", "Restaurar")
            if value
            else QCoreApplication.translate("TitleBar", "Maximizar")
        )

    # --- dragging the window ---
    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Start the system move only on a real drag.

        Calling `startSystemMove()` on press would eat the double click,
        which is how one maximizes, because Windows's drag loop keeps
        the next events.
        """
        if self._press_pos is None:
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._press_pos).manhattanLength() < 6:
            return super().mouseMoveEvent(event)
        self._press_pos = None
        handle = self.window().windowHandle()
        if handle is not None:
            handle.startSystemMove()
        return None

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_requested.emit()
        super().mouseDoubleClickEvent(event)

    # --- paint ---
    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.fill)
        p.end()


class _Accessible(QAccessibleWidget):
    """The diamond as decoration: assistive technology does not see it.

    `CONSOLA`, next to it, already names the brand.
    """

    def __init__(self, diamond: _Diamond) -> None:
        """Give the diamond the graphic role."""
        super().__init__(diamond, QAccessible.Role.Graphic)

    @override
    def state(self) -> QAccessible.State:
        state = super().state()
        # The stubs of PySide6 6.12 declare each state `...` with a
        # type comment, which Pyrefly does not read.
        state.invisible = True  # pyrefly: ignore[bad-assignment]
        return state


def _interface(key: str, obj: QObject) -> QAccessibleInterface | None:
    """Return the interface of `_Diamond`, for `installFactory`."""
    return _Accessible(obj) if isinstance(obj, _Diamond) else None


QAccessible.installFactory(_interface)
