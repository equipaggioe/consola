from __future__ import annotations

from PySide6.QtWidgets import QMenuBar, QMenu
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Signal

from ui.theme import Colors, Fonts
from ui import favorites
from core.registry import registry


# Marcador de texto en vez de pintado propio: un `QMenu` no deja tenir un
# item suelto, y se lee igual de bien sin costar un `QWidgetAction` (que
# seria reimplementar `ActionRow` dentro del popup).
MARK_DANGER = '⚠'   # destructiva: revisar antes de apretar


class ActionMenuBar(QMenuBar):
    """Barra de menu superior: el catalogo entero de acciones a un recorrido
    de hover, sin acordeon y sin ocupar ancho.

    Un clic abre la pestana de la accion, por la misma senal que el buscador
    de la misma fila (`ui/action_search.py`), asi que `MainWindow` no
    distingue de donde vino el clic. Correr de una queda para el ▶ del
    buscador.
    """

    action_requested = Signal(str)        # capability_id: abrir su pestana
    focus_search_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Su propia franja, debajo de la barra de titulo — no un tramo
        # compartido con la marca y los botones de ventana (`ui/title_bar.py`):
        # ahi quedaba demasiado apretada. El fondo y la linea de abajo los
        # pinta la fila que la contiene, que llega mas a la derecha que el
        # menu (ahi va el interruptor de favoritos).
        self.setStyleSheet(f"""
            QMenuBar {{
                background: transparent; color: {Colors.TEXT};
                font-size: {Fonts.SIZE_BASE}px;
                min-height: 20px;
                padding: 3px 2px;
            }}
            QMenuBar::item {{ background: transparent; padding: 9px 13px; }}
            QMenuBar::item:selected {{ background: {Colors.SURFACE_HOVER}; }}
            QMenuBar::item:pressed {{ background: {Colors.SURFACE_ALT}; }}
        """)

        self._actions: dict[str, QAction] = {}   # capability_id -> item del menu
        self._group_menus: list[QMenu] = []
        # Por menu de grupo, sus bloques de seccion: cada uno con el separador
        # y el encabezado que lo abren (si los tiene) y sus acciones. Es lo que
        # necesita `_apply_filters` para podar un menu sin dejar rayas ni
        # encabezados sueltos sobre una seccion que quedo vacia.
        self._blocks: dict[QMenu, list[tuple[QAction | None, QAction | None, list[str]]]] = {}
        self._favorites: set[str] = favorites.favorite_ids()
        self._only_favorites = favorites.only_favorites()
        # Lo que tiene sentido en el repo abierto (`core/catalog.py::applicable_ids`).
        # None = todavia no hay repo: no se filtra nada, que es lo mismo que
        # hacia antes de que existiera este filtro.
        self._applicable: set[str] | None = None

        self._build_action_menus()
        self._build_view_menu()
        self._build_help_menu()

        self.set_project_active(False)
        self._apply_filters()

    # --- construccion ----------------------------------------------------
    def _build_action_menus(self) -> None:
        """Un menu por grupo del registro, en su orden; dentro, las acciones
        separadas por `Capability.section`.

        `section` da el segundo nivel sin anadir un
        submenu — que para las secciones de una sola accion (Utils tiene
        varias) seria un clic de mas por nada: queda todo a un nivel, con la
        seccion como encabezado.

        El encabezado es una accion deshabilitada y no `addSection`: con una
        hoja de estilo puesta sobre el `QMenu`, Qt dibuja la raya de
        `addSection` pero se come su texto, y «Base de datos» quedaba con
        nueve acciones partidas por seis rayas sin explicacion.

        El titulo de la barra va sin el emoji del grupo: son once menus en una fila, y a 1000px —el minimo de la ventana—
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
            blocks: list[tuple[QAction | None, QAction | None, list[str]]] = []
            for i, (section, caps) in enumerate(sections.items()):
                separator = header = None
                if titled and section:
                    if i:
                        separator = menu.addSeparator()
                    header = QAction(section, menu)
                    header.setEnabled(False)
                    menu.addAction(header)
                for cap in caps:
                    menu.addAction(self._make_action(menu, cap))
                blocks.append((separator, header, [c.id for c in caps]))
            self._blocks[menu] = blocks
            self._group_menus.append(menu)

    def _make_action(self, menu: QMenu, cap) -> QAction:
        label = f"{cap.icon}  {cap.name}".strip()
        if cap.kind == 'destructive':
            label += f"  {MARK_DANGER}"
        action = QAction(label, menu)
        action.setToolTip(_tooltip(cap))
        action.triggered.connect(lambda _checked=False, cid=cap.id: self.action_requested.emit(cid))
        self._actions[cap.id] = action
        return action

    def _build_view_menu(self) -> None:
        menu = self.addMenu('Ver')
        buscar = QAction('Buscar acciones', self)
        buscar.setShortcut(QKeySequence('Ctrl+L'))
        buscar.triggered.connect(self.focus_search_requested.emit)
        menu.addAction(buscar)

    def _build_help_menu(self) -> None:
        """Solo la leyenda del marcador."""
        menu = self.addMenu('Ayuda')
        item = QAction(f'{MARK_DANGER}  = destructiva', self)
        item.setEnabled(False)
        menu.addAction(item)

    # --- estado -----------------------------------------------------------
    def set_project_active(self, active: bool) -> None:
        """Sin repo en pestanas no hay nada sobre lo que correr: los menus de
        acciones se deshabilitan enteros, igual que el buscador."""
        for menu in self._group_menus:
            menu.setEnabled(active)

    def set_applicable(self, ids: set[str]) -> None:
        """Que acciones tienen sentido en el repo abierto.

        Las que no —"Migrar" en un repo que no lleva migraciones— se van del
        menu enteras, no quedan en ambar: no les falta un dato, les falta sobre
        que actuar (docs/capacidades-por-repo.md 1). Un grupo que se queda sin
        ninguna desaparece de la barra, igual que con «solo favoritos».
        """
        if self._applicable is not None and ids == self._applicable:
            return
        self._applicable = set(ids)
        self._apply_filters()

    # --- solo favoritos ---------------------------------------------------
    def set_only_favorites(self, value: bool) -> None:
        """El interruptor de la barra de titulo: con el puesto, los menus de
        grupo muestran solo las acciones marcadas — y el grupo que no tenga
        ninguna desaparece de la barra, no queda como un menu vacio."""
        if value == self._only_favorites:
            return
        self._only_favorites = value
        self._apply_filters()

    def set_favorites(self, ids: set[str]) -> None:
        """Se marco o desmarco una favorita en otra superficie (el filete del
        buscador, la estrella de la cabecera de parametros)."""
        if ids == self._favorites:
            return
        self._favorites = set(ids)
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Los dos filtros de la barra, en una sola pasada: lo que no aplica a
        este repo y —si el interruptor esta puesto— lo que no esta marcado."""
        for menu in self._group_menus:
            vivos = 0
            for separator, header, cap_ids in self._blocks.get(menu, []):
                visibles = 0
                for cap_id in cap_ids:
                    action = self._actions[cap_id]
                    ver = (self._applicable is None or cap_id in self._applicable) and (
                        not self._only_favorites or cap_id in self._favorites)
                    action.setVisible(ver)
                    visibles += int(ver)
                # El encabezado (y la raya que lo precede) solo tienen sentido
                # si quedo algo debajo.
                if header is not None:
                    header.setVisible(visibles > 0)
                if separator is not None:
                    separator.setVisible(visibles > 0 and vivos > 0)
                vivos += visibles
            menu.menuAction().setVisible(vivos > 0)


def _by_section(capabilities: list) -> dict[str, list]:
    sections: dict[str, list] = {}
    for cap in capabilities:
        sections.setdefault(cap.section, []).append(cap)
    return sections


def _tooltip(cap) -> str:
    """El mismo contenido que el tooltip de las filas del buscador (`ActionRow._tooltip`):
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
                 "Clic para abrir</span>")
    return '<br>'.join(lines)
