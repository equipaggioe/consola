from __future__ import annotations
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFileDialog, QMenu, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QLinearGradient,
    QFont, QAction, QPen, QBrush
)

from ui.theme import Colors, Fonts
from ui.widgets import ReorderableTab, ReorderableBar
from ui import project_store
from core.projects import Project

# Paleta rotativa para repos anadidos en caliente
PALETTE = ['#58a6ff', '#bc8cff', '#3fb950', '#d29922', '#f47067',
           '#a5d6ff', '#ffa657', '#ff7b72', '#7ee787', '#79c0ff']


class ProjectTab(ReorderableTab, QWidget):
    """Pestana de nivel superior: un repositorio.

    El estado activo se hace evidente con tres senales simultaneas: un
    contorno del color del repo que envuelve la pestana por arriba y por
    los lados (abierto por abajo, para fundirse con la linea separadora
    de la barra), fondo degradado que se funde con el lienzo de abajo, y
    texto brillante en negrita.
    """
    clicked = Signal()
    close_requested = Signal()

    HEIGHT = 44
    BORDER_WIDTH = 2.0

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
        layout.setContentsMargins(16, 0, 10, 0)
        layout.setSpacing(8)

        self.name_label = QLabel(project.name)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: {Fonts.SIZE_LG}px;
            }}
            QPushButton:hover {{
                color: {Colors.ERROR};
                background: {Colors.SURFACE_HOVER};
            }}
        """)
        self.close_btn.clicked.connect(self.close_requested.emit)

        layout.addWidget(self.name_label)
        layout.addWidget(self.close_btn)

        self._init_reorder()
        self._sync_text()
        self.set_closable(True)

    # --- estado -----------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._sync_text()
        self.update()

    def set_closable(self, closable: bool) -> None:
        self._closable = closable
        self.close_btn.setVisible(closable)  # visible siempre que se pueda cerrar

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
            self._reorder_press(event)
        elif event.button() == Qt.MouseButton.MiddleButton and self._closable:
            self.close_requested.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self._reorder_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._reorder_release(event)
        super().mouseReleaseEvent(event)

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
        bw = self.BORDER_WIDTH
        r = QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, 0)

        if self.is_active:
            grad = QLinearGradient(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 52))
            grad.setColorAt(1.0, QColor(Colors.BG))
            p.fillRect(r, QBrush(grad))

            # Contorno recto abierto por abajo: sube por la izquierda, cruza
            # por arriba y baja por la derecha, para conectar con la linea
            # separadora que dibuja ProjectTabBar justo debajo — una sola
            # figura continua alrededor de la pestana activa.
            outline = QPainterPath()
            outline.moveTo(r.left(), r.bottom())
            outline.lineTo(r.left(), r.top())
            outline.lineTo(r.right(), r.top())
            outline.lineTo(r.right(), r.bottom())

            pen = QPen(color)
            pen.setWidthF(bw)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(outline)
        elif self._hovered or self.is_dragging:
            p.fillRect(r, QColor(Colors.SURFACE_HOVER))

        if self.is_dragging:
            pen = QPen(color)
            pen.setWidthF(1.4)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(1, 1, -1, -1))

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
        if self._hovered:
            p.fillRect(r, QColor(Colors.SURFACE_HOVER))
        else:
            pen = QPen(QColor(Colors.BORDER))
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
        pen = QPen(QColor(Colors.TEXT if self._hovered else Colors.TEXT_MUTED))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = r.center()
        p.drawLine(QPointF(c.x() - 6, c.y()), QPointF(c.x() + 6, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 6), QPointF(c.x(), c.y() + 6))
        p.end()


class ProjectTabBar(ReorderableBar, QWidget):
    """Nivel superior de pestanas: un repositorio por pestana + boton '+'."""
    project_selected = Signal(object)   # Project
    project_added = Signal(object)      # Project
    project_removed = Signal(object)    # Project

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ProjectTab.HEIGHT)
        self.tabs: list[ProjectTab] = []
        self._active: ProjectTab | None = None
        # Mientras MainWindow puebla las pestanas al arrancar no hay que
        # reescribir el store en cada `add_project`: se guarda ya al terminar.
        self._loading = False

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 0, 10, 0)
        self.layout.setSpacing(2)

        self.add_tab = AddProjectTab()
        self.add_tab.clicked.connect(self._pick_repo)

        self.layout.addWidget(self.add_tab)
        self.layout.addStretch()

    # --- reordenar arrastrando ---------------------------------------
    def _tab_layout(self):
        return self.layout

    def tabs_reordered(self) -> None:
        self.update()
        self._persist()

    # --- conjunto persistente ----------------------------------------
    def _persist(self) -> None:
        """Guarda la lista entera de repos (ruta, nombre, color, icono) en el
        orden actual: anadir, quitar y reordenar sobreviven al reinicio
        (`ui/project_store.py`)."""
        if self._loading:
            return
        project_store.save([t.project for t in self.tabs])

    # --- API ---------------------------------------------------------
    def load_projects(self, projects: list[Project]) -> None:
        """Puebla la barra al arrancar sin reescribir el store en cada paso.

        Existe para que MainWindow no tenga que tocar el guardado por dentro:
        anadir ocho repos disparaba ocho escrituras de la lista entera, y la
        ultima era la unica correcta.
        """
        self._loading = True
        try:
            for project in projects:
                self.add_project(project)
        finally:
            self._loading = False
        self._persist()

    def find_tab(self, path: str) -> ProjectTab | None:
        """La pestana de esa carpeta, sin importar como este escrita la ruta."""
        key = project_store.identity(path)
        return next((t for t in self.tabs
                     if project_store.identity(t.project.path) == key), None)

    def add_project(self, project: Project, select: bool = False) -> ProjectTab:
        # Una carpeta, una pestana: dos pestanas del mismo repo serian dos
        # paneles escribiendo el mismo `.consola/params.json`.
        existente = self.find_tab(project.path)
        if existente is not None:
            if select:
                self.select_tab(existente)
            return existente

        tab = ProjectTab(project)
        tab.clicked.connect(lambda t=tab: self.select_tab(t))
        tab.close_requested.connect(lambda t=tab: self.remove_tab(t))
        index = self.layout.indexOf(self.add_tab)
        self.layout.insertWidget(index, tab)
        self.tabs.append(tab)
        self._refresh_closable()
        self._persist()
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
        if tab not in self.tabs:
            return
        idx = self.tabs.index(tab)
        was_active = tab is self._active
        project = tab.project
        self.tabs.remove(tab)
        self.layout.removeWidget(tab)
        tab.setParent(None)
        tab.deleteLater()
        self._refresh_closable()
        self._persist()
        if was_active:
            # Quitar el ultimo repo deja la barra vacia: no hay a que saltar y
            # MainWindow muestra la pantalla de "anade un repositorio".
            self._active = None
            if self.tabs:
                self.select_tab(self.tabs[min(idx, len(self.tabs) - 1)])
        self.project_removed.emit(project)

    @property
    def active_project(self) -> Project | None:
        return self._active.project if self._active else None

    def _refresh_closable(self) -> None:
        # Toda pestana se puede cerrar, incluida la ultima: quedarse sin repos
        # abiertos es un estado valido, no un callejon.
        for t in self.tabs:
            t.set_closable(True)

    # --- anadir repo --------------------------------------------------
    def _pick_repo(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta del repositorio", "")
        if not path:
            return
        ya = self.find_tab(path)
        if ya is not None:
            self.select_tab(ya)
            return
        limpia = project_store.display_path(path)
        name = os.path.basename(limpia) or limpia
        color = PALETTE[len(self.tabs) % len(PALETTE)]
        project = Project(name, limpia, color, '\U0001F4C1')
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
