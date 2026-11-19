"""The top-level tabs: one per repository."""

from __future__ import annotations

import os
from typing import override

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QWidget,
)

from app import theme
from app.services import palettes, params_store, project_store
from app.services.palettes import Palette
from app.services.projects import Project
from app.widgets.project_tab import ProjectTab
from app.widgets.reorderable_bar import ReorderableBar


class _AddProjectTab(QWidget):
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
        self.setStyleSheet("_AddProjectTab { background: transparent; }")
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
        r = QRectF(self.rect()).adjusted(7.5, 5.5, -7.5, -5.5)

        add = theme.ADD_TAB.on(self.pal)
        edge = QColor(add.border)
        edge.setAlpha(150 if self._hovered else 90)
        pen = QPen(edge)
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.drawPath(path)

        glyph = QColor(add.fg)
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

        self.add_tab = _AddProjectTab()
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
        (`services/project_store.py`).
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
    @Slot()
    def _pick_repo(self) -> None:
        # Open the folder dialog: `open_path` takes what it chooses.
        dialog = QFileDialog(self, "Elegir carpeta del repositorio")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)
        dialog.fileSelected.connect(self.open_path)
        dialog.open()

    @Slot(str)
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
