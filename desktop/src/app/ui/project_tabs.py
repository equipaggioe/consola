"""The top-level tabs: one per repository."""

from __future__ import annotations

import os
from typing import override

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QEnterEvent,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.core.projects import Project
from app.theme import Colors, Fonts, tint
from app.ui import palettes, params_store, project_store, repo_logo
from app.ui.palettes import Palette
from app.ui.widgets import ReorderableBar, ReorderableTab


class ProjectTab(ReorderableTab):
    """A top-level tab: one repository.

    The active one paints in its accent, the same as the title bar
    holding it, with no outline: it melts into it. The others paint in
    the ACTIVE repo's background (`chrome`, the band of the row below)
    with outline and name in THEIR repo's accent: they sink against the
    active one, as a back tab should, and each still says which color it
    is.
    """

    clicked = Signal()
    close_requested = Signal()
    theme_changed = Signal()

    # The whole title bar's height. 44 and not 38: inside the outline,
    # at 38 the name stuck to the bottom edge.
    HEIGHT = 44
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
        self.setStyleSheet("ProjectTab { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 10, 0)
        layout.setSpacing(8)

        # Left of the name: the × is on the right, and a logo next to it
        # would read as another button.
        self.logo = repo_logo.RepoLogoView(self.LOGO, repo_logo.resolve(project.path))

        self.name_label = QLabel(project.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.close_btn = QPushButton("×")
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
        color = self.pal.accent if self.is_active else self.active_pal.on_accent
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

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton and self._closable:
            self.close_requested.emit()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._reorder_move(event)
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._reorder_release(event)
        super().mouseReleaseEvent(event)

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

        The eight themes go loose in the menu and not in a submenu: the
        menu offers nothing else, so a submenu would be an extra step to
        reach all there is. Removing the repo is not here either: the
        tab's × does it.
        """
        self._context_menu().exec(event.globalPos())

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        path_action = QAction(self.project.path, self)
        path_action.setEnabled(False)
        menu.addAction(path_action)
        menu.addSeparator()

        # Color is chosen, not assigned by chance: adding a repo gives
        # it the first free theme, and any other can be picked here.
        for key, pal in palettes.THEMES.items():
            action = QAction(pal.label, self)
            action.setCheckable(True)
            action.setChecked(key == self.project.theme)
            action.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            menu.addAction(action)
        return menu

    # --- paint -----------------------------------------------------
    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the tab.

        Selected: `chrome`, the band of the row below. The others: the
        active repo's accent, the color of the bar they rest on, and the
        «+»'s outline, which is all that sets them apart; hover raises
        it.
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 5.0, -1.5, -5.0)
        path = QPainterPath()
        path.addRoundedRect(r, 7, 7)

        if self.is_active:
            p.fillPath(path, QColor(self.pal.chrome))
            p.end()
            return

        p.fillPath(path, QColor(self.active_pal.accent))
        edge = QColor(self.active_pal.on_accent)
        edge.setAlpha(150 if (self._hovered or self.is_dragging) else 90)
        pen = QPen(edge)
        pen.setWidthF(1.2)
        if self.is_dragging:
            pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class AddProjectTab(QWidget):
    """A short tab with the plus sign: add a repository.

    It carries the `on_accent` outline over the active repo's bar, the
    same as an unselected tab: it is one more tab, the one with no repo
    yet.
    """

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the tab."""
        super().__init__(parent)
        self.setFixedSize(48, ProjectTab.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("AddProjectTab { background: transparent; }")
        self.pal = palettes.NEUTRAL
        self._hovered = False
        self.setToolTip("Anadir repositorio")

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self.update()

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    @override
    def leaveEvent(self, event: QEvent) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(7.5, 6.5, -7.5, -6.5)

        edge = QColor(self.pal.on_accent)
        edge.setAlpha(150 if self._hovered else 90)
        pen = QPen(edge)
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.drawPath(path)

        glyph = QColor(self.pal.on_accent)
        glyph.setAlpha(255 if self._hovered else 190)
        pen = QPen(glyph)
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = r.center()
        p.drawLine(QPointF(c.x() - 6, c.y()), QPointF(c.x() + 6, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 6), QPointF(c.x(), c.y() + 6))
        p.end()


class ProjectTabBar(ReorderableBar):
    """Top level of tabs: one repository per tab and a «+» button."""

    project_selected = Signal(object)  # Project
    project_added = Signal(object)  # Project
    project_removed = Signal(object)  # Project
    project_retinted = Signal(object)  # Project: it chose another color

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the empty bar."""
        super().__init__(parent)
        self.setFixedHeight(ProjectTab.HEIGHT)
        self.tabs: list[ProjectTab] = []
        self._active: ProjectTab | None = None
        # While MainWindow populates tabs at startup, the store should
        # not be rewritten on each `add_project`: it saves once at the
        # end.
        self._loading = False

        self.row_layout = QHBoxLayout(self)
        self.row_layout.setContentsMargins(8, 0, 10, 0)
        self.row_layout.setSpacing(2)

        self.add_tab = AddProjectTab()
        self.add_tab.clicked.connect(self._pick_repo)

        self.row_layout.addWidget(self.add_tab)
        self.row_layout.addStretch()

    # --- reorder by dragging ---------------------------------------
    @override
    def _tab_layout(self) -> QHBoxLayout:
        return self.row_layout

    @override
    def tabs_reordered(self) -> None:
        self.update()
        self._persist()

    # --- persistent set ----------------------------------------
    def _persist(self) -> None:
        """Save the whole list of repos, in order: path and name.

        Adding, removing and reordering survive a restart
        (`ui/project_store.py`).
        """
        if self._loading:
            return
        project_store.save([t.project for t in self.tabs])

    # --- API ---------------------------------------------------------
    def load_projects(self, projects: list[Project]) -> None:
        """Populate the bar at startup, without rewriting the store.

        It keeps MainWindow from touching the saving internals: adding
        eight repos fired eight writes of the whole list, and only the
        last was right.
        """
        self._loading = True
        try:
            for project in projects:
                self.add_project(project)
        finally:
            self._loading = False
        self._persist()

    def find_tab(self, path: str) -> ProjectTab | None:
        """Return that folder's tab, however its path is written."""
        key = project_store.identity(path)
        return next((t for t in self.tabs if project_store.identity(t.project.path) == key), None)

    def add_project(self, project: Project, select: bool = False) -> ProjectTab:
        # One folder, one tab: two tabs of the same repo would be two
        # panels writing the same `.consola/params.json`.
        """Add a repo's tab, and select it if asked."""
        existing = self.find_tab(project.path)
        if existing is not None:
            if select:
                self.select_tab(existing)
            return existing

        tab = ProjectTab(project)
        if self._active is not None:
            tab.set_active_palette(self._active.pal)
        tab.clicked.connect(lambda t=tab: self.select_tab(t))
        tab.close_requested.connect(lambda t=tab: self.remove_tab(t))
        tab.theme_changed.connect(lambda t=tab: self._on_theme_changed(t))
        index = self.row_layout.indexOf(self.add_tab)
        self.row_layout.insertWidget(index, tab)
        self.tabs.append(tab)
        self._refresh_closable()
        self._persist()
        if select or self._active is None:
            self.select_tab(tab)
        return tab

    def _on_theme_changed(self, tab: ProjectTab) -> None:
        if tab is self._active:
            # Recoloring the active one repaints the background of ALL
            # tabs.
            for t in self.tabs:
                t.set_active_palette(tab.pal)
            self.add_tab.set_palette(tab.pal)
        self._persist()
        self.project_retinted.emit(tab.project)

    def select_tab(self, tab: ProjectTab) -> None:
        """Select a tab."""
        if self._active is tab:
            return
        self._active = tab
        for t in self.tabs:
            t.set_active_palette(tab.pal)
            t.set_active(t is tab)
        self.add_tab.set_palette(tab.pal)
        self.update()
        self.project_selected.emit(tab.project)

    def select_project(self, project: Project) -> None:
        """Select a project's tab."""
        for t in self.tabs:
            if t.project is project:
                self.select_tab(t)
                return

    def remove_tab(self, tab: ProjectTab) -> None:
        """Remove a tab."""
        if tab not in self.tabs:
            return
        idx = self.tabs.index(tab)
        was_active = tab is self._active
        project = tab.project
        self.tabs.remove(tab)
        self.row_layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()
        self._refresh_closable()
        self._persist()
        if was_active:
            # Removing the last repo leaves the bar empty: there is
            # nowhere to jump to, and MainWindow shows the «add a
            # repository» screen.
            self._active = None
            if self.tabs:
                self.select_tab(self.tabs[min(idx, len(self.tabs) - 1)])
            else:
                self.add_tab.set_palette(palettes.NEUTRAL)
        self.project_removed.emit(project)

    @property
    def active_project(self) -> Project | None:
        """Return the active tab's project."""
        return self._active.project if self._active else None

    def _refresh_closable(self) -> None:
        # Any tab can close, the last included: having no open repos is
        # a valid state, not a dead end.
        for t in self.tabs:
            t.set_closable(True)

    # --- add a repo --------------------------------------------------
    def _pick_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta del repositorio", "")
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        """Open that folder as a tab, or jump to its tab if open.

        The «+» calls it, and so does whatever leaves a new repo folder
        with nobody choosing it: cloning from GitHub
        (`Capability.opens_repo`). Both take the same path, first free
        theme and added-repo notice, because a cloned repo is no
        different from one chosen by hand.
        """
        if not path:
            return
        already = self.find_tab(path)
        if already is not None:
            self.select_tab(already)
            return
        clean = project_store.display_path(path)
        name = os.path.basename(clean) or clean
        theme = palettes.first_free(t.project.theme for t in self.tabs)
        # Color saves in the repo from the first moment, not on changing
        # it: opening it on another machine has to give the same color.
        params_store.save_theme(clean, theme)
        project = Project(name, clean, theme)
        self.add_project(project, select=True)
        self.project_added.emit(project)
