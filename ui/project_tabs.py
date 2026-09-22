from __future__ import annotations
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFileDialog, QMenu, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QFont, QAction, QPen
)

from ui.theme import Colors, Fonts
from ui.widgets import ReorderableTab, ReorderableBar
from ui import project_store, palettes
from core.projects import Project


class ProjectTab(ReorderableTab, QWidget):
    """Pestana de nivel superior: un repositorio.

    La barra de titulo se pinta entera del acento del repo activo
    (`ui/title_bar.py`), y la pestana activa se funde con ella: sin fondo
    propio, texto en negrita del color legible sobre ese fondo (`on_accent`).
    Las demas son una placa oscura con el nombre en el color de SU repo: cada
    una se reconoce por su color sin competir con la barra, y sin un mosaico
    de fondos saturados que le quitaria protagonismo a la activa.
    """
    clicked = Signal()
    close_requested = Signal()
    theme_changed = Signal()

    HEIGHT = 38

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        # `pal` y no `palette`: `QWidget.palette()` ya existe y es otra cosa.
        self.pal = palettes.get(project.theme)
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
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        color = self.pal.on_accent if self.is_active else self.pal.accent
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
                background: {Colors.SURFACE_HOVER};
            }}
        """)
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

    # --- tema ---------------------------------------------------------
    def set_theme(self, key: str) -> None:
        """Cambia el color del repo. Lo repinta todo: la pestana de aca y,
        via `theme_changed`, el espacio de trabajo entero — la paleta no es un
        acento suelto, son los fondos de todos sus paneles."""
        if key == self.project.theme:
            return
        self.project.theme = key
        self.pal = palettes.get(key)
        self._sync_text()
        self.update()
        self.theme_changed.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        path_action = QAction(self.project.path, self)
        path_action.setEnabled(False)
        menu.addAction(path_action)

        # El color se elige, no toca en suerte: al anadir un repo se le da el
        # primer tema libre y desde aca se cambia por cualquier otro.
        menu.addSeparator()
        colores = menu.addMenu("Color del repositorio")
        for clave, pal in palettes.THEMES.items():
            accion = QAction(pal.label, self)
            accion.setCheckable(True)
            accion.setChecked(clave == self.project.theme)
            accion.triggered.connect(lambda _=False, k=clave: self.set_theme(k))
            colores.addAction(accion)

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
        r = QRectF(self.rect()).adjusted(1, 5, -1, -5)

        if not self.is_active:
            chip = QColor(Colors.CHROME)
            chip.setAlpha(245 if (self._hovered or self.is_dragging) else 200)
            path = QPainterPath()
            path.addRoundedRect(r, 5, 5)
            p.fillPath(path, chip)

        if self.is_dragging:
            pen = QPen(QColor(self.pal.accent))
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
        r = QRectF(self.rect()).adjusted(7, 6, -7, -6)
        # Placa oscura como las pestanas inactivas: sobre la barra pintada del
        # color del repo, un contorno gris no se leia.
        chip = QColor(Colors.CHROME)
        chip.setAlpha(245 if self._hovered else 200)
        path = QPainterPath()
        path.addRoundedRect(r, 5, 5)
        p.fillPath(path, chip)
        pen = QPen(QColor(Colors.TEXT if self._hovered else Colors.TEXT_DIM))
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
    project_retinted = Signal(object)   # Project: eligio otro color

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
        """Guarda la lista entera de repos (ruta, nombre, tema, icono) en el
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
        tab.theme_changed.connect(lambda t=tab: self._on_theme_changed(t))
        index = self.layout.indexOf(self.add_tab)
        self.layout.insertWidget(index, tab)
        self.tabs.append(tab)
        self._refresh_closable()
        self._persist()
        if select or self._active is None:
            self.select_tab(tab)
        return tab

    def _on_theme_changed(self, tab: ProjectTab) -> None:
        self._persist()
        self.project_retinted.emit(tab.project)

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
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> None:
        """Abre esa carpeta como pestana, o salta a la suya si ya esta.

        Lo llaman el «+» y lo que deja una carpeta de repo nueva sin que nadie
        la elija: clonar de GitHub (`Capability.opens_repo`). Es el mismo
        camino en los dos casos — primer tema libre, icono por defecto y
        aviso de repo anadido — porque un repo clonado no es un repo distinto
        de uno elegido a mano.
        """
        if not path:
            return
        ya = self.find_tab(path)
        if ya is not None:
            self.select_tab(ya)
            return
        limpia = project_store.display_path(path)
        name = os.path.basename(limpia) or limpia
        theme = palettes.first_free(t.project.theme for t in self.tabs)
        project = Project(name, limpia, theme, '📁')
        self.add_project(project, select=True)
        self.project_added.emit(project)

