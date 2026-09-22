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
        # Por menu de grupo, sus tramos: cada uno con la raya que lo abre (la
        # del primero es None) y sus acciones. Es lo que necesita
        # `_apply_filters` para podar un menu sin dejar rayas colgando de un
        # tramo que quedo vacio.
        self._blocks: dict[QMenu, list[tuple[QAction | None, list[str]]]] = {}
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
        item que no se puede apretar.

        `QMenu::separator` es obligatoria: con una hoja de estilo puesta sobre
        el `QMenu`, Qt deja de dibujar la linea nativa del separador y solo
        queda su alto en blanco — la misma trampa que ya documentaba
        `_build_action_menus` para `addSection`. Sin esta regla, los cortes de
        ADR-0043 se ven como un espacio vacio, no como una raya."""
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
            QMenu::separator {{
                height: 1px; margin: 4px 8px;
                background: {self.pal.border_light};
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

        Los menus largos se cortan con rayas, no con encabezados: el rotulo de
        una seccion obligaba a nombrar el tramo —y a inventar un nombre para
        los tramos de un solo boton—, cuando lo unico que hace falta es que el
        ojo vea donde el menu deja de hablar de una cosa y empieza a hablar de
        otra. Los nombres, que empiezan por el verbo, dicen el resto.

        De donde sale cada raya:

        - `Capability.cut`: el catalogo declara que este boton abre un tramo.
        - `kind == 'destructive'`: lo que borra va al fondo, siempre detras de
          una raya, sin que nadie lo declare (ADR-0043).

        El titulo de la barra va sin el emoji del grupo: son ocho menus en una
        fila, y a 1000px —el minimo de la ventana— el emoji es lo primero que
        empuja los ultimos al desbordamiento.
        """
        for group, capabilities in registry.get_groups().items():
            menu = self._add_menu(group)
            menu.setToolTipsVisible(True)
            blocks: list[tuple[QAction | None, list[str]]] = []
            destructivas = False
            for cap in capabilities:
                primera_destructiva = cap.kind == 'destructive' and not destructivas
                destructivas = destructivas or primera_destructiva
                if not blocks:
                    blocks.append((None, []))
                elif cap.cut or primera_destructiva:
                    blocks.append((menu.addSeparator(), []))
                menu.addAction(self._make_action(menu, cap))
                blocks[-1][1].append(cap.id)
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
            vivos = 0
            for separator, cap_ids in self._blocks[menu]:
                visibles = 0
                for cap_id in cap_ids:
                    ver = (self._applicable is None or cap_id in self._applicable) and (
                        not self._only_favorites or cap_id in self._favorites)
                    self._actions[cap_id].setVisible(ver)
                    visibles += int(ver)
                # Una raya solo separa si quedo algo de los dos lados.
                if separator is not None:
                    separator.setVisible(visibles > 0 and vivos > 0)
                vivos += visibles
            menu.menuAction().setVisible(vivos > 0)


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
