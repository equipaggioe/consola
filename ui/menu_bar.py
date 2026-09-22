from __future__ import annotations

from PySide6.QtWidgets import QMenuBar, QMenu
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Signal

from ui.theme import Colors, Fonts
from ui.palettes import NEUTRAL, Palette
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
        self.pal = NEUTRAL
        self.setStyleSheet(self._bar_style())

        self._actions: dict[str, QAction] = {}   # capability_id -> item del menu
        self._group_menus: list[QMenu] = []
        # Todos los menus de la barra, de grupo o no: lo que hay que repintar
        # cuando cambia el repo activo.
        self._menus: list[QMenu] = []
        # Por menu de grupo, sus dos tramos —lo que hace y lo que deshace— con
        # la raya que los separa. Es lo que necesita `_apply_filters` para
        # podar un menu sin dejar la raya colgando de un tramo vacio.
        self._blocks: dict[QMenu, tuple[list[str], QAction | None, list[str]]] = {}
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

    # --- paleta ------------------------------------------------------------
    def set_palette(self, pal: Palette) -> None:
        """Los menus desplegados son del repo abierto, como todo lo demas.

        Sin esto se quedaban en los neutros de `ui/theme.py` y el nombre del
        item bajo el cursor salia en el azul fijo de `Colors.ACCENT` — el
        acento de OTRO tema — en los siete repos que no son azules.
        """
        self.pal = pal
        self.setStyleSheet(self._bar_style())
        for menu in self._menus:
            menu.setStyleSheet(self._menu_style())

    def _bar_style(self) -> str:
        """La franja en si no se pinta: el fondo (`chrome`) y la linea de
        abajo los pone la fila que la contiene, que llega mas a la derecha que
        el menu (ahi va el interruptor de favoritos). Lo que si se pinta es el
        titulo del menu abierto, que se pone del fondo del popup que cuelga de
        el para que se lean como una sola pieza."""
        return f"""
            QMenuBar {{
                background: transparent; color: {Colors.TEXT};
                font-size: {Fonts.SIZE_BASE}px;
                min-height: 20px;
                padding: 3px 2px;
            }}
            QMenuBar::item {{ background: transparent; padding: 9px 13px; }}
            QMenuBar::item:selected {{ background: {self.pal.panel}; }}
            QMenuBar::item:pressed {{ background: {self.pal.panel}; }}
        """

    def _menu_style(self) -> str:
        """El popup en `panel`, dos escalones por debajo de la fila de la que
        cuelga: sobre `chrome` no se recortaria (1.06:1 contra la barra), y el
        item bajo el cursor necesita un escalon propio por encima del popup.
        La regla de `:disabled` es por la leyenda del menu Ayuda, que es un
        item que no se puede apretar."""
        return f"""
            QMenu {{
                background: {self.pal.panel}; color: {Colors.TEXT};
                border: 1px solid {self.pal.border_light};
            }}
            QMenu::item:selected {{
                background: {self.pal.surface_hover}; color: {self.pal.accent};
            }}
            QMenu::item:disabled {{
                color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;
            }}
        """

    def _add_menu(self, title: str) -> QMenu:
        menu = self.addMenu(title)
        menu.setStyleSheet(self._menu_style())
        self._menus.append(menu)
        return menu

    # --- construccion ----------------------------------------------------
    def _build_action_menus(self) -> None:
        """Un menu por grupo del registro, en el orden en que el catalogo los
        declara, y dentro las acciones en ese mismo orden.

        No hay encabezados de seccion. El segundo nivel dentro de un menu
        existia porque los menus eran largos y heterogeneos; con los grupos
        reorganizados ninguno pasa de doce items y el orden de declaracion es
        el del uso real —preparar, usar, mirar—, asi que el rotulo no agregaba
        nada. Que los nombres empiecen por el verbo hace el resto: los items de
        la misma familia quedan pegados y se leen como un bloque sin que haya
        que dibujarlo.

        La unica division que queda no es taxonomica sino de seguridad: una
        raya, y debajo lo que borra (`kind == 'destructive'`). El catalogo
        declara esas capacidades al final de su grupo, asi que la raya cae en
        el corte y no parte ninguna familia.

        El titulo de la barra va sin el emoji del grupo: son ocho menus en una
        fila, y a 1000px —el minimo de la ventana— el emoji es lo primero que
        empuja los ultimos al desbordamiento.
        """
        for group, capabilities in registry.get_groups().items():
            menu = self._add_menu(group)
            menu.setToolTipsVisible(True)
            hacen = [c for c in capabilities if c.kind != 'destructive']
            deshacen = [c for c in capabilities if c.kind == 'destructive']
            for cap in hacen:
                menu.addAction(self._make_action(menu, cap))
            separator = menu.addSeparator() if hacen and deshacen else None
            for cap in deshacen:
                menu.addAction(self._make_action(menu, cap))
            self._blocks[menu] = ([c.id for c in hacen], separator,
                                  [c.id for c in deshacen])
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
        menu = self._add_menu('Ver')
        buscar = QAction('Buscar acciones', self)
        buscar.setShortcut(QKeySequence('Ctrl+L'))
        buscar.triggered.connect(self.focus_search_requested.emit)
        menu.addAction(buscar)

    def _build_help_menu(self) -> None:
        """Solo la leyenda del marcador."""
        menu = self._add_menu('Ayuda')
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
        que actuar (ADR-0007). Un grupo que se queda sin
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
            arriba, separator, abajo = self._blocks[menu]
            visibles_arriba = self._show(arriba)
            visibles_abajo = self._show(abajo)
            # La raya solo separa si quedo algo de los dos lados.
            if separator is not None:
                separator.setVisible(bool(visibles_arriba and visibles_abajo))
            menu.menuAction().setVisible(bool(visibles_arriba or visibles_abajo))

    def _show(self, cap_ids: list[str]) -> int:
        """Aplica los filtros a un tramo y devuelve cuantos quedaron a la vista."""
        visibles = 0
        for cap_id in cap_ids:
            ver = (self._applicable is None or cap_id in self._applicable) and (
                not self._only_favorites or cap_id in self._favorites)
            self._actions[cap_id].setVisible(ver)
            visibles += int(ver)
        return visibles


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
