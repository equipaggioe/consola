"""A repo's tab on the title row."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QEnterEvent,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app import theme
from app.services import palettes, params_store, repo_logo
from app.services.palettes import Palette
from app.services.projects import Project
from app.theme import Colors, Fonts, on_color, tint
from app.widgets.reorderable_tab import ReorderableTab
from app.widgets.repo_logo_view import RepoLogoView


class ProjectTab(ReorderableTab):
    """A top-level tab: one repository.

    The selected one paints in the menu row's background, with its name
    in its accent: it joins the row below. The others paint in the
    ACTIVE repo's accent, the title bar they rest on, with outline and
    name in the ink that reads over it (`theme.py`).
    """

    close_requested = Signal()
    theme_changed = Signal()

    # The whole title bar's height. 40 with the outline 4 px in from
    # each edge: at 38 with 5 px, the name stuck to the bottom edge.
    HEIGHT = 40
    LOGO = 18

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Build the tab."""
        super().__init__(parent)
        self.project = project
        # `pal` and not `palette`: `QWidget.palette()` exists and is
        # something else.
        self.pal = palettes.get(project.theme)
        # The active repo's, whose color the bar is painted in: this
        # tab's background while it is NOT the active one.
        self.active_pal = self.pal
        self.is_active = False
        self._hovered = False
        self._closable = True

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(project.path)
        self.setAccessibleName(project.name)
        self.setStyleSheet("ProjectTab { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(8)

        # Left of the name: the × is on the right, and a logo next to it
        # would read as another button.
        self.logo = RepoLogoView(self.LOGO, repo_logo.resolve(project.path))

        self.name_label = QLabel(project.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.close_btn = QPushButton("×")
        self.close_btn.setAccessibleName(f"Cerrar {project.name}")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.close_requested.emit)

        layout.addWidget(self.logo)
        layout.addWidget(self.name_label)
        layout.addWidget(self.close_btn)

        self._init_reorder()
        self._sync_text()
        self.set_closable(True)

    # --- state -----------------------------------------------------
    def set_active(self, active: bool) -> None:
        """Set whether it is the active tab."""
        self.is_active = active
        self._sync_text()
        self.update()
        self._announce_active()

    def set_active_palette(self, pal: Palette) -> None:
        """Set the active repo's palette, the background of a back tab.

        The bar sets it when selecting or recoloring (`ProjectTabBar`).
        """
        self.active_pal = pal
        self._sync_text()
        self.update()

    def set_logo(self, logo: repo_logo.RepoLogo) -> None:
        """Show another logo."""
        self.logo.set_logo(logo)

    def set_closable(self, closable: bool) -> None:
        """Set whether the × shows."""
        self._closable = closable
        # visible whenever it can close
        self.close_btn.setVisible(closable)

    def _sync_text(self) -> None:
        f = QFont(self.name_label.font())
        f.setPixelSize(Fonts.SIZE_BASE)
        f.setBold(self.is_active)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6 if self.is_active else 0.0)
        self.name_label.setFont(f)
        # Selected: the repo's accent over its dark band. The others:
        # the ink that reads over the active repo's accent, the
        # background of the bar they rest on.
        color = (
            theme.REPO_TAB_SELECTED.on(self.pal).fg
            if self.is_active
            else theme.REPO_TAB.on(self.active_pal).fg
        )
        self.name_label.setStyleSheet(f"background: transparent; color: {color};")
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {color};
                background: transparent;
                border: none; padding: 0;
                text-align: center;
                border-radius: 4px;
                font-size: {Fonts.SIZE_LG}px;
            }}
            QPushButton:hover {{
                color: {Colors.ERROR};
                background: {tint(color, 0.16)};
            }}
        """)
        self.updateGeometry()

    @override
    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        s.setHeight(self.HEIGHT)
        return s

    # --- interaction -------------------------------------------------
    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self._sync_text()
        self.update()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    # The tab keeps its press and its drag: passed on to the parent,
    # they reached `TitleBar`, which after 6 px starts moving the
    # window, and Windows's move loop took the drag from the tab. A
    # double click does go on, and maximizes as on the rest of the bar.
    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton and self._closable:
            self.close_requested.emit()
        event.accept()

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._reorder_move(event)
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._reorder_release(event)
        event.accept()

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Not the default, which calls `mousePressEvent` and would keep
        # it: it goes on to `TitleBar`.
        event.ignore()

    # --- theme ---
    def set_theme(self, key: str) -> None:
        """Change the repo's color, repainting everything.

        This tab and, through `theme_changed`, the whole workspace: the
        palette is not a loose accent but the backgrounds of all its
        panels.

        It saves in the repo (`.consola/params.json`) and not on this
        machine: color is a decision about THAT repo and travels with
        it.
        """
        if key == self.project.theme:
            return
        self.project.theme = key
        self.pal = palettes.get(key)
        params_store.save_theme(self.project.path, key)
        self._sync_text()
        self.update()
        self.theme_changed.emit()

    @override
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show the path and the colors, with no level in between.

        The eight themes go loose in the menu and not in a submenu: a
        submenu would be an extra step to reach them. Below them, «Roles
        y partes» shows what each color is made of. Removing the repo is
        not here: the tab's × does it.
        """
        self._context_menu().exec(event.globalPos())

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        # Qt sets the samples against the edge; these leave them where
        # the Ver menu sets its checks
        # (`widgets/action_menu_bar.py::_menu_style`).
        menu.setStyleSheet("QMenu::icon { left: 8px; } QMenu::item { padding-left: 16px; }")
        path_action = QAction(self.project.path, self)
        path_action.setEnabled(False)
        menu.addAction(path_action)
        menu.addSeparator()

        # Color is chosen, not assigned by chance: adding a repo gives
        # it the first free theme, and any other can be picked here.
        # Each item carries its sample in the box where a check would
        # go, and the chosen one carries the check inside its sample.
        ratio = self.devicePixelRatioF()
        for key, pal in palettes.THEMES.items():
            action = QAction(
                swatch(pal.accent, chosen=key == self.project.theme, ratio=ratio), pal.label, self
            )
            action.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            menu.addAction(action)
        return menu

    # --- paint -----------------------------------------------------
    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the tab.

        Selected: `surface_alt`, the band of the row below. The others:
        the active repo's accent, the color of the bar they rest on, and
        the «+»'s outline, which is all that sets them apart; hover
        raises it.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 4.0, -1.5, -4.0)
        path = QPainterPath()
        path.addRoundedRect(r, 7, 7)

        if self.is_active:
            p.fillPath(path, QColor(theme.REPO_TAB_SELECTED.on(self.pal).bg))
            p.end()
            return

        tab = theme.REPO_TAB.on(self.active_pal)
        p.fillPath(path, QColor(tab.bg))
        edge = QColor(tab.border)
        edge.setAlpha(150 if (self._hovered or self.is_dragging) else 90)
        pen = QPen(edge)
        pen.setWidthF(1.2)
        if self.is_dragging:
            pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


def swatch(color: str, *, chosen: bool, ratio: float) -> QIcon:
    """Return a box filled with `color`, with a check if `chosen`.

    The size and the radius of a check box (`QCheckBox::indicator` in
    `app/theme.py`), so the color menu reads as a list of boxes.
    """
    side = 15
    pixmap = QPixmap(round(side * ratio), round(side * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QPainterPath()
    box.addRoundedRect(QRectF(0.5, 0.5, side - 1, side - 1), 4, 4)
    p.fillPath(box, QColor(color))
    if chosen:
        pen = QPen(QColor(on_color(color)))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        tick = QPainterPath(QPointF(3.8, 7.8))
        tick.lineTo(6.4, 10.4)
        tick.lineTo(11.2, 4.8)
        p.drawPath(tick)
    p.end()
    return QIcon(pixmap)
