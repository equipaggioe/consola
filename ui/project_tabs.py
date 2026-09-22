from __future__ import annotations
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFileDialog, QMenu, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QFont, QAction, QPen
)

from ui.theme import Colors, Fonts, tint
from ui.widgets import ReorderableTab, ReorderableBar
from ui import project_store, palettes, params_store
from core.projects import Project


class ProjectTab(ReorderableTab, QWidget):
    """Pestana de nivel superior: un repositorio.

    La activa se pinta de su acento, el mismo de la barra de titulo que la
    sostiene, y va sin contorno: se funde con ella. Las demas se pintan del
    fondo del repo ACTIVO (`chrome`, la banda de la fila de abajo) y llevan
    contorno y nombre en el acento de SU repo — se hunden respecto de la
    activa, que es lo que una pestana de atras tiene que hacer, y aun asi
    cada una dice de que color es.
    """
    clicked = Signal()
    close_requested = Signal()
    theme_changed = Signal()

    # Alto de la barra de titulo entera. 44 y no 38: dentro del contorno, a
    # 38 el nombre quedaba pegado al borde de abajo.
    HEIGHT = 44

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        # `pal` y no `palette`: `QWidget.palette()` ya existe y es otra cosa.
        self.pal = palettes.get(project.theme)
        # La del repo activo, que es de quien esta pintada la barra: de ahi
        # sale el fondo de esta pestana mientras NO sea la activa.
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

    def set_active_palette(self, pal) -> None:
        """La paleta del repo activo: el fondo de esta pestana cuando no lo
        es. La pone la barra al seleccionar o al recolorear (`ProjectTabBar`)."""
        self.active_pal = pal
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
        # Seleccionada: el acento del repo sobre su banda oscura. Las otras:
        # la tinta que se lee sobre el acento del repo activo, que es el fondo
        # de la barra en el que se apoyan.
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
        acento suelto, son los fondos de todos sus paneles.

        Se guarda en el repo (`.consola/params.json`) y no en esta maquina: el
        color es una decision sobre ESE repo y viaja con el.
        """
        if key == self.project.theme:
            return
        self.project.theme = key
        self.pal = palettes.get(key)
        params_store.save_theme(self.project.path, key)
        self._sync_text()
        self.update()
        self.theme_changed.emit()

    def contextMenuEvent(self, event):
        """La ruta y los colores, sin un nivel de por medio.

        Los ocho temas van sueltos en el menu y no dentro de un submenu: el
        menu no tiene nada mas que ofrecer, asi que un submenu seria un paso
        extra para llegar a lo unico que hay. Quitar el repo tampoco esta:
        para eso esta la × de la pestana, y repetirlo aca no agrega un camino,
        agrega una lista mas larga.
        """
        self._context_menu().exec(event.globalPos())

    def _context_menu(self) -> QMenu:
        menu = QMenu(self)
        path_action = QAction(self.project.path, self)
        path_action.setEnabled(False)
        menu.addAction(path_action)
        menu.addSeparator()

        # El color se elige, no toca en suerte: al anadir un repo se le da el
        # primer tema libre y desde aca se cambia por cualquier otro.
        for clave, pal in palettes.THEMES.items():
            accion = QAction(pal.label, self)
            accion.setCheckable(True)
            accion.setChecked(clave == self.project.theme)
            accion.triggered.connect(lambda _=False, k=clave: self.set_theme(k))
            menu.addAction(accion)
        return menu

    # --- pintura -----------------------------------------------------
    def paintEvent(self, event):
        """La seleccionada: `chrome`, la banda de la fila de abajo. Las demas:
        el acento del repo activo —el color de la barra donde se apoyan— y el
        contorno del «+», que es lo unico que las recorta; el hover lo sube."""
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
        borde = QColor(self.active_pal.on_accent)
        borde.setAlpha(150 if (self._hovered or self.is_dragging) else 90)
        pen = QPen(borde)
        pen.setWidthF(1.2)
        if self.is_dragging:
            pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()


class AddProjectTab(QWidget):
    """Pestana corta con el signo de mas: anadir repositorio.

    Lleva el contorno de `on_accent` sobre la barra del repo activo, que es
    el mismo de una pestana no seleccionada: es una pestana mas, la que
    todavia no tiene repo.
    """
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, ProjectTab.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("AddProjectTab { background: transparent; }")
        self.pal = palettes.NEUTRAL
        self._hovered = False
        self.setToolTip("Anadir repositorio")

    def set_palette(self, pal) -> None:
        self.pal = pal
        self.update()

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
        r = QRectF(self.rect()).adjusted(7.5, 6.5, -7.5, -6.5)

        borde = QColor(self.pal.on_accent)
        borde.setAlpha(150 if self._hovered else 90)
        pen = QPen(borde)
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.drawPath(path)

        glifo = QColor(self.pal.on_accent)
        glifo.setAlpha(255 if self._hovered else 190)
        pen = QPen(glifo)
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
        if self._active is not None:
            tab.set_active_palette(self._active.pal)
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
        if tab is self._active:
            # Recolorear el activo repinta el fondo de TODAS las pestanas.
            for t in self.tabs:
                t.set_active_palette(tab.pal)
            self.add_tab.set_palette(tab.pal)
        self._persist()
        self.project_retinted.emit(tab.project)

    def select_tab(self, tab: ProjectTab) -> None:
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
            else:
                self.add_tab.set_palette(palettes.NEUTRAL)
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
        # El color se guarda en el repo desde el primer momento, no al
        # cambiarlo: abrirlo en otra maquina tiene que dar el mismo color.
        params_store.save_theme(limpia, theme)
        project = Project(name, limpia, theme, '📁')
        self.add_project(project, select=True)
        self.project_added.emit(project)

