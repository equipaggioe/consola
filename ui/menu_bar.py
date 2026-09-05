from __future__ import annotations

from PySide6.QtWidgets import QMenuBar, QMenu, QApplication
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtCore import Signal, Qt

from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import Project


# Marcadores de texto en vez de pintado propio: un `QMenu` no deja tenir un
# item suelto, y estos dos leen igual de bien y no cuestan un `QWidgetAction`
# (que seria reimplementar `ActionRow` dentro del popup).
MARK_DANGER = '⚠'   # destructiva: revisar antes de apretar
MARK_READY = '▸'    # tiene todo lo que necesita: Ctrl+clic la corre de una


class ActionMenuBar(QMenuBar):
    """Barra de menu superior: el catalogo entero de acciones a un recorrido
    de hover, sin acordeon y sin ocupar ancho.

    Convive con el rail (`ui/rail.py`) en vez de reemplazarlo: el rail sigue
    siendo la superficie *siempre visible* — que puede correr ya, cuales son
    favoritas, el ▶ por fila —, y el menu es el indice completo. Las dos
    superficies emiten exactamente las mismas dos senales, asi que
    `MainWindow` no distingue de donde vino el clic.

    Un clic abre la pestana de la accion. Ctrl+clic la corre de una, igual
    que el ▶ del rail, y cae en abrir la pestana si le falta configuracion —
    para que la pulsacion nunca se pierda en silencio.
    """

    action_requested = Signal(str)        # capability_id: abrir su pestana
    run_requested = Signal(str)           # capability_id: correr de una
    add_project_requested = Signal()
    close_project_requested = Signal()
    project_chosen = Signal(str)          # ruta del repo a activar
    focus_filter_requested = Signal()
    rail_auto_width_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QMenuBar {{
                background: {Colors.CHROME}; color: {Colors.TEXT};
                border-bottom: 1px solid {Colors.BORDER};
                font-size: {Fonts.SIZE_BASE}px;
                min-height: 20px;
                padding: 3px 2px;
            }}
            QMenuBar::item {{ background: transparent; padding: 9px 13px; }}
            QMenuBar::item:selected {{ background: {Colors.SURFACE_HOVER}; }}
            QMenuBar::item:pressed {{ background: {Colors.SURFACE_ALT}; }}
        """)

        self._actions: dict[str, QAction] = {}   # capability_id -> item del menu
        self._labels: dict[str, str] = {}        # capability_id -> texto sin marca
        self._ready: set[str] = set()
        self._group_menus: list[QMenu] = []

        self._repo_menu = self.addMenu('Repositorio')
        self._repo_group = QActionGroup(self)    # el repo activo, como radio
        self._repo_group.setExclusive(True)
        self._build_action_menus()
        self._build_view_menu()
        self._build_help_menu()

        self.set_projects([], None)
        self.set_project_active(False)

    # --- construccion ----------------------------------------------------
    def _build_action_menus(self) -> None:
        """Un menu por grupo del registro, en su orden; dentro, las acciones
        separadas por `Capability.section`.

        `section` estaba declarado en `core/catalog.py` y no lo miraba nadie:
        el rail agrupa solo por grupo. Aqui da el segundo nivel sin anadir un
        submenu — que para las secciones de una sola accion (Utils tiene
        varias) seria un clic de mas por nada: queda todo a un nivel, con la
        seccion como encabezado.

        El encabezado es una accion deshabilitada y no `addSection`: con una
        hoja de estilo puesta sobre el `QMenu`, Qt dibuja la raya de
        `addSection` pero se come su texto, y «Base de datos» quedaba con
        nueve acciones partidas por seis rayas sin explicacion.

        El titulo de la barra va sin el emoji del grupo aunque el rail si lo
        use: son once menus en una fila, y a 1000px —el minimo de la ventana—
        el emoji es lo primero que empuja los ultimos al desbordamiento.
        """
        for group, capabilities in registry.get_groups().items():
            menu = self.addMenu(group)
            menu.setToolTipsVisible(True)
            menu.setStyleSheet(
                f"QMenu::item:disabled {{ color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px; }}")
            sections = _by_section(capabilities)
            titled = len(sections) > 1
            for i, (section, caps) in enumerate(sections.items()):
                if titled and section:
                    if i:
                        menu.addSeparator()
                    header = QAction(section, menu)
                    header.setEnabled(False)
                    menu.addAction(header)
                for cap in caps:
                    menu.addAction(self._make_action(menu, cap))
            self._group_menus.append(menu)

    def _make_action(self, menu: QMenu, cap) -> QAction:
        label = f"{cap.icon}  {cap.name}".strip()
        if cap.kind == 'destructive':
            label += f"  {MARK_DANGER}"
        action = QAction(label, menu)
        action.setToolTip(_tooltip(cap))
        action.triggered.connect(lambda _checked=False, cid=cap.id: self._trigger(cid))
        self._labels[cap.id] = label
        self._actions[cap.id] = action
        return action

    def _build_view_menu(self) -> None:
        menu = self.addMenu('Ver')
        menu.setToolTipsVisible(True)

        filtrar = QAction('Filtrar acciones en el rail', self)
        filtrar.setShortcut(QKeySequence('Ctrl+L'))
        filtrar.triggered.connect(self.focus_filter_requested.emit)
        menu.addAction(filtrar)

        auto = QAction('Ancho automático del rail', self)
        auto.setToolTip('Lo mismo que hacer doble clic en el separador del rail')
        auto.triggered.connect(self.rail_auto_width_requested.emit)
        menu.addAction(auto)

    def _build_help_menu(self) -> None:
        """Solo la leyenda de los marcadores: el menu no inventa funciones que
        el rail no tenga, esta fase solo anade la superficie."""
        menu = self.addMenu('Ayuda')
        for text in (f'{MARK_READY}  = lista para correr con lo guardado',
                     f'{MARK_DANGER}  = destructiva',
                     'Ctrl+clic sobre una acción la corre de una'):
            item = QAction(text, self)
            item.setEnabled(False)
            menu.addAction(item)

    # --- estado -----------------------------------------------------------
    def set_projects(self, projects: list[Project], active_path: str | None) -> None:
        """Rehace el menu Repositorio: los repos abiertos son sus items, el
        activo va marcado, y Ctrl+1..9 vive aqui (no como `QShortcut` suelto)
        para que el atajo se lea junto a la accion que dispara."""
        # Sacar los items del grupo ANTES de vaciar el menu: `clear()` los
        # destruye, y el `QActionGroup` se quedaria apuntando a objetos
        # muertos. Por lo mismo cuelgan del menu y no de la barra — asi
        # `clear()` es quien de verdad los libera, y no se acumulan en la
        # barra una copia por cada vez que se rehace la lista.
        for action in self._repo_group.actions():
            self._repo_group.removeAction(action)
        self._repo_menu.clear()

        add = QAction('Añadir repositorio…', self._repo_menu)
        add.setShortcut(QKeySequence('Ctrl+T'))
        add.triggered.connect(self.add_project_requested.emit)
        self._repo_menu.addAction(add)

        if projects:
            self._repo_menu.addSection('Abiertos')
        for i, project in enumerate(projects):
            item = QAction(f"{project.icon}  {project.name}", self._repo_menu)
            item.setCheckable(True)
            item.setChecked(project.path == active_path)
            item.setToolTip(project.path)
            if i < 9:
                item.setShortcut(QKeySequence(f'Ctrl+{i + 1}'))
            item.triggered.connect(lambda _c=False, p=project.path: self.project_chosen.emit(p))
            self._repo_group.addAction(item)
            self._repo_menu.addAction(item)

        self._repo_menu.addSeparator()
        close = QAction('Cerrar repositorio actual', self._repo_menu)
        close.setEnabled(bool(projects))
        close.triggered.connect(self.close_project_requested.emit)
        self._repo_menu.addAction(close)
        self._repo_menu.setToolTipsVisible(True)

    def set_project_active(self, active: bool) -> None:
        """Sin repo en pestanas no hay nada sobre lo que correr: los menus de
        acciones se deshabilitan enteros, igual que el rail apaga sus cajas
        (`ActionRail.clear_project`)."""
        for menu in self._group_menus:
            menu.setEnabled(active)

    def set_ready(self, ready: set[str]) -> None:
        """Marca con `▸` las acciones que pueden correr de una con lo que hay
        guardado. Misma cuenta que el ▶ del rail: `ui/readiness.py`."""
        if ready == self._ready:
            return
        self._ready = set(ready)
        for cap_id, action in self._actions.items():
            label = self._labels[cap_id]
            action.setText(f"{label}  {MARK_READY}" if cap_id in ready else label)

    # --- disparo ----------------------------------------------------------
    def _trigger(self, cap_id: str) -> None:
        """Ctrl+clic corre de una; sin Ctrl —o con Ctrl pero sin la
        configuracion que la accion necesita— abre su pestana, que es donde
        se completan los parametros que faltan."""
        ctrl = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl and cap_id in self._ready:
            self.run_requested.emit(cap_id)
        else:
            self.action_requested.emit(cap_id)


def _by_section(capabilities: list) -> dict[str, list]:
    sections: dict[str, list] = {}
    for cap in capabilities:
        sections.setdefault(cap.section, []).append(cap)
    return sections


def _tooltip(cap) -> str:
    """El mismo contenido que el tooltip del rail (`ActionRow._tooltip`):
    que hace, de que nivel es, y como se usa la entrada."""
    composite = bool(cap.composed_of or len(cap.steps) > 1)
    level = ('Compuesta · encadena varias atómicas' if composite
             else 'Atómica · un solo paso')
    if cap.is_machine_wide:
        level += ' · de la máquina, no del repo'
    lines = [f"<b>{cap.name}</b>"]
    if cap.description:
        lines.append(cap.description)
    lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>{level}</span>")
    lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>"
                 "Clic para abrir · Ctrl+clic para correr de una</span>")
    return '<br>'.join(lines)
