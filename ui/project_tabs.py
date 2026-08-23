from __future__ import annotations
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFileDialog, QMenu, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QLinearGradient, QRadialGradient,
    QFont, QAction, QPen, QBrush
)

from ui.theme import Colors, Fonts
from core.projects import Project

# Paleta rotativa para repos anadidos en caliente
PALETTE = ['#58a6ff', '#bc8cff', '#3fb950', '#d29922', '#f47067',
           '#a5d6ff', '#ffa657', '#ff7b72', '#7ee787', '#79c0ff']


class ProjectTab(QWidget):
    """Pestana de nivel superior: un repositorio.

    El estado activo se hace evidente con cuatro senales simultaneas:
    barra superior del color del repo, fondo degradado que se funde con el
    lienzo de abajo, texto brillante en negrita y punto luminoso encendido.
    """
    clicked = Signal()
    close_requested = Signal()

    HEIGHT = 44
    RADIUS = 10

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.is_active = False
        self._hovered = False
        self._closable = True

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(project.path)
        self.setStyleSheet("ProjectTab { background: transparent; }")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 0, 18, 0)  # margen izq. deja sitio al punto
        layout.setSpacing(9)

        self.icon_label = QLabel(project.icon)
        self.icon_label.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_LG}px;")

        self.name_label = QLabel(project.name)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)

        self._sync_text()

    # --- estado -----------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._sync_text()
        self.update()

    def set_closable(self, closable: bool) -> None:
        self._closable = closable

    def _sync_text(self) -> None:
        f = QFont(self.name_label.font())
        f.setPixelSize(Fonts.SIZE_BASE)
        f.setBold(self.is_active)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6 if self.is_active else 0.0)
        self.name_label.setFont(f)
        color = Colors.TEXT if self.is_active else (Colors.TEXT_DIM if self._hovered else Colors.TEXT_MUTED)
        self.name_label.setStyleSheet(f"background: transparent; color: {color};")
        self.updateGeometry()

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(self.HEIGHT)
        return s

    # --- interaccion -------------------------------------------------
    def enterEvent(self, event):
        self._hovered = True
        self._sync_text()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._sync_text()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton and self._closable:
            self.close_requested.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        path_action = QAction(self.project.path, self)
        path_action.setEnabled(False)
        menu.addAction(path_action)
        if self._closable:
            menu.addSeparator()
            close_action = QAction("Quitar repositorio", self)
            close_action.triggered.connect(self.close_requested.emit)
            menu.addAction(close_action)
        menu.exec(event.globalPos())

    # --- pintura -----------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.project.color)
        r = QRectF(self.rect())

        path = QPainterPath()
        path.moveTo(r.left(), r.bottom())
        path.lineTo(r.left(), r.top() + self.RADIUS)
        path.quadTo(r.left(), r.top(), r.left() + self.RADIUS, r.top())
        path.lineTo(r.right() - self.RADIUS, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + self.RADIUS)
        path.lineTo(r.right(), r.bottom())
        path.closeSubpath()

        if self.is_active:
            grad = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 52))
            grad.setColorAt(1.0, QColor(Colors.BG))
            p.fillPath(path, QBrush(grad))

            top = QPainterPath()
            top.addRoundedRect(QRectF(r.left() + 1, r.top(), r.width() - 2, 3.0), 1.5, 1.5)
            p.fillPath(top, color)
        elif self._hovered:
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))

        # punto luminoso a la izquierda
        cx = r.left() + 17
        cy = r.center().y() + 1
        p.setPen(Qt.PenStyle.NoPen)
        if self.is_active:
            halo = QRadialGradient(QPointF(cx, cy), 10)
            halo.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 160))
            halo.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(cx, cy), 10, 10)
            dot = color
        else:
            dot = QColor(Colors.INACTIVE)
        p.setBrush(dot)
        p.drawEllipse(QPointF(cx, cy), 4, 4)
        p.end()


class AddProjectTab(QWidget):
    """Pestana corta con el signo de mas: anadir repositorio."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, ProjectTab.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("AddProjectTab { background: transparent; }")
        self._hovered = False
        self.setToolTip("Anadir repositorio")

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(7, 8, -7, -10)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        if self._hovered:
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))
        else:
            pen = QPen(QColor(Colors.BORDER))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        pen = QPen(QColor(Colors.TEXT if self._hovered else Colors.TEXT_MUTED))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = r.center()
        p.drawLine(QPointF(c.x() - 6, c.y()), QPointF(c.x() + 6, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 6), QPointF(c.x(), c.y() + 6))
        p.end()


class ProjectTabBar(QWidget):
    """Nivel superior de pestanas: un repositorio por pestana + boton '+'."""
    project_selected = Signal(object)   # Project
    project_added = Signal(object)      # Project
    project_removed = Signal(object)    # Project

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ProjectTab.HEIGHT)
        self.tabs: list[ProjectTab] = []
        self._active: ProjectTab | None = None

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 0, 10, 0)
        self.layout.setSpacing(2)

        self.add_tab = AddProjectTab()
        self.add_tab.clicked.connect(self._pick_repo)

        self.layout.addWidget(self.add_tab)
        self.layout.addStretch()

    # --- API ---------------------------------------------------------
    def add_project(self, project: Project, select: bool = False) -> ProjectTab:
        tab = ProjectTab(project)
        tab.clicked.connect(lambda t=tab: self.select_tab(t))
        tab.close_requested.connect(lambda t=tab: self.remove_tab(t))
        index = self.layout.indexOf(self.add_tab)
        self.layout.insertWidget(index, tab)
        self.tabs.append(tab)
        self._refresh_closable()
        if select or self._active is None:
            self.select_tab(tab)
        return tab

    def select_tab(self, tab: ProjectTab) -> None:
        if self._active is tab:
            return
        self._active = tab
        for t in self.tabs:
            t.set_active(t is tab)
        self.update()
        self.project_selected.emit(tab.project)

    def select_project(self, project: Project) -> None:
        for t in self.tabs:
            if t.project is project:
                self.select_tab(t)
                return

    def remove_tab(self, tab: ProjectTab) -> None:
        if len(self.tabs) <= 1:
            return
        idx = self.tabs.index(tab)
        was_active = tab is self._active
        project = tab.project
        self.tabs.remove(tab)
        self.layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()
        self._refresh_closable()
        if was_active:
            self._active = None
            self.select_tab(self.tabs[min(idx, len(self.tabs) - 1)])
        self.project_removed.emit(project)

    @property
    def active_project(self) -> Project | None:
        return self._active.project if self._active else None

    def _refresh_closable(self) -> None:
        only_one = len(self.tabs) <= 1
        for t in self.tabs:
            t.set_closable(not only_one)

    # --- anadir repo --------------------------------------------------
    def _pick_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta del repositorio", "")
        if not path:
            return
        norm = os.path.normcase(os.path.normpath(path))
        for t in self.tabs:
            if os.path.normcase(os.path.normpath(t.project.path)) == norm:
                self.select_tab(t)
                return
        name = os.path.basename(os.path.normpath(path)) or path
        color = PALETTE[len(self.tabs) % len(PALETTE)]
        project = Project(name, path.replace(os.sep, '/'), color, '\U0001F4C1')
        self.add_project(project, select=True)
        self.project_added.emit(project)

    # --- pintura ------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(Colors.CHROME))

        # Linea inferior con el color del repo activo: la pestana activa la
        # rompe al pintar encima su propio fondo, como una carpeta abierta.
        if self._active:
            color = QColor(self._active.project.color)
        else:
            color = QColor(Colors.BORDER)
        p.fillRect(0, self.height() - 2, self.width(), 2, color)
        p.end()
