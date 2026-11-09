"""The top menu bar of actions."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMenuBar, QWidget

from app.core.registry import Capability, registry
from app.theme import Colors, Fonts
from app.ui import favorites, section_visibility
from app.ui.palettes import NEUTRAL, Palette

# A text marker and not custom paint: a `QMenu` does not allow tinting
# one item, and this reads just as well without a `QWidgetAction`, which
# would reimplement `ActionRow` inside the popup.
MARK_DANGER = "⚠"  # destructive: check before pressing


class ActionMenuBar(QMenuBar):
    """The top menu bar: the whole action catalog one hover away.

    No accordion, and it takes no width. A click opens the action's tab
    through the same signal as the search on the same row
    (`ui/action_search.py`), so `MainWindow` cannot tell where the click
    came from. Running at once is left to the search's ▶.
    """

    action_requested = Signal(str)  # capability_id: open its tab
    only_favorites_toggled = Signal(bool)
    section_toggled = Signal(str, bool)  # section id, visible

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the menus from the registry."""
        super().__init__(parent)
        self.pal = NEUTRAL
        self.setStyleSheet(self._bar_style())

        # capability_id -> menu item
        self._actions: dict[str, QAction] = {}
        self._group_menus: list[QMenu] = []
        # All the bar's menus, of a group or not: what has to be
        # repainted when the active repo changes.
        self._menus: list[QMenu] = []
        # Per group menu, its stretches: each with the line that opens
        # it (None for the first) and its actions. `_apply_filters`
        # needs it to prune a menu without leaving lines hanging from an
        # emptied stretch.
        self._blocks: dict[QMenu, list[tuple[QAction | None, list[str]]]] = {}
        self._favorites: set[str] = favorites.favorite_ids()
        self._only_favorites = favorites.only_favorites()
        # What makes sense in the open repo
        # (`core/catalog.py::applicable_ids`). None = no repo yet:
        # nothing is filtered.
        self._applicable: set[str] | None = None

        self._build_action_menus()
        self._build_view_menu()

        self.set_project_active(False)
        self._apply_filters()

    # --- palette ---
    def set_palette(self, pal: Palette) -> None:
        """Repaint the open menus: they belong to the open repo too.

        Without this they stayed in the neutrals of `theme.py`, and the
        name of the item under the cursor came out in the fixed blue of
        `Colors.ACCENT`, the accent of ANOTHER theme, in the seven repos
        that are not blue.
        """
        self.pal = pal
        self.setStyleSheet(self._bar_style())
        for menu in self._menus:
            menu.setStyleSheet(self._menu_style(checks=menu is self._view_menu))

    def _bar_style(self) -> str:
        """Return the bar's style.

        The strip itself is not painted: the row that holds it sets the
        background (`chrome`) and the bottom line, and it reaches
        further right than the menu, where the search goes. What is
        painted is the open menu's title, in the background of
        the popup hanging from it, so they read as one piece.
        """
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

    def _menu_style(self, *, checks: bool = False) -> str:
        """Return the popup's style.

        The popup is `panel`, two steps below the row it hangs from: on
        `chrome` it would not stand out (1.06:1 against the bar), and
        the item under the cursor needs its own step above the popup.

        `QMenu::separator` is required: with a style sheet on the
        `QMenu`, Qt stops drawing the separator's native line and only
        its blank height remains. Without this rule, the cuts of
        ADR-0043 show as empty space, not a line.

        `checks` is for the Ver menu, whose items carry a check: by
        default Qt draws it 5 px from the edge and the text at 41.
        These two rules leave them at 13 and 33, measured offscreen.
        """
        checks_css = (
            "QMenu::indicator { left: 8px; } QMenu::item { padding-left: 16px; }" if checks else ""
        )
        return (
            checks_css
            + f"""
            QMenu {{
                background: {self.pal.panel}; color: {Colors.TEXT};
                border: 1px solid {self.pal.border_light};
            }}
            QMenu::item:selected {{
                background: {self.pal.surface_hover}; color: {self.pal.accent};
            }}
            QMenu::separator {{
                height: 1px; margin: 4px 8px;
                background: {self.pal.border_light};
            }}
        """
        )

    def _add_menu(self, title: str, *, checks: bool = False) -> QMenu:
        menu = self.addMenu(title)
        menu.setStyleSheet(self._menu_style(checks=checks))
        self._menus.append(menu)
        return menu

    # --- building ---
    def _build_action_menus(self) -> None:
        """Build one menu per registry group, in catalog order.

        Inside, actions go in that same order. Long menus cut with
        lines, not headings: a section label forced naming each stretch,
        and inventing a name for one-button stretches, when all that is
        needed is for the eye to see where the menu stops speaking of
        one thing. The names, which start with the verb, say the rest.

        Where each line comes from:

        - `Capability.cut`: the catalog declares that this button opens
          a stretch.
        - `kind == 'destructive'`: what deletes goes to the bottom,
          always behind a line, without anyone declaring it (ADR-0043).

        The bar's title goes without the group's emoji: there are eight
        menus in a row, and at 1000px, the window's minimum, the emoji
        is the first thing that pushes the last ones into overflow.
        """
        for group, capabilities in registry.get_groups().items():
            menu = self._add_menu(group)
            menu.setToolTipsVisible(True)
            blocks: list[tuple[QAction | None, list[str]]] = []
            destructive = False
            for cap in capabilities:
                first_destructive = cap.kind == "destructive" and not destructive
                destructive = destructive or first_destructive
                if not blocks:
                    blocks.append((None, []))
                elif cap.cut or first_destructive:
                    blocks.append((menu.addSeparator(), []))
                menu.addAction(self._make_action(menu, cap))
                blocks[-1][1].append(cap.id)
            self._blocks[menu] = blocks
            self._group_menus.append(menu)

    def _make_action(self, menu: QMenu, cap: Capability) -> QAction:
        """Return the menu item: the name, without the emoji."""
        label = cap.name
        if cap.kind == "destructive":
            label += f"  {MARK_DANGER}"
        action = QAction(label, menu)
        action.setToolTip(_tooltip(cap))
        action.triggered.connect(
            lambda _checked=False, cid=cap.id: self.action_requested.emit(cid)
        )
        self._actions[cap.id] = action
        return action

    def _build_view_menu(self) -> None:
        """Build «Solo favoritos» and the visible sections.

        Both are preferences of the app, not of the repo: they hold for
        every tab. The checks are read again on opening the menu, since
        a section also hides from its header's right click.
        """
        menu = self._add_menu("Ver", checks=True)
        self._view_menu = menu
        self._only_favorites_action = QAction("Solo favoritos", self)
        self._only_favorites_action.setCheckable(True)
        self._only_favorites_action.setChecked(self._only_favorites)
        self._only_favorites_action.toggled.connect(self.only_favorites_toggled.emit)
        menu.addAction(self._only_favorites_action)

        menu.addSeparator()
        self._section_actions: dict[str, QAction] = {}
        for section_id, title in section_visibility.SECTIONS.items():
            action = QAction(title, self)
            action.setCheckable(True)

            def on_section(visible: bool, s: str = section_id) -> None:
                self.section_toggled.emit(s, visible)

            action.toggled.connect(on_section)
            self._section_actions[section_id] = action
            menu.addAction(action)
        menu.aboutToShow.connect(self._sync_view_checks)

    def _sync_view_checks(self) -> None:
        hidden = section_visibility.hidden_sections()
        for section_id, action in self._section_actions.items():
            action.blockSignals(True)
            action.setChecked(section_id not in hidden)
            action.blockSignals(False)

    # --- state ---
    def set_project_active(self, active: bool) -> None:
        """Enable or disable the action menus.

        With no repo in tabs there is nothing to run on: the action
        menus are disabled whole, like the search.
        """
        for menu in self._group_menus:
            menu.setEnabled(active)

    def set_applicable(self, ids: set[str]) -> None:
        """Set which actions make sense in the open repo.

        Those that do not, such as «Migrar» in a repo without
        migrations, leave the menu whole and do not stay amber: they
        lack no datum but something to act on (ADR-0007). A group left
        with none disappears from the bar, as with «solo favoritos».
        """
        if self._applicable is not None and ids == self._applicable:
            return
        self._applicable = set(ids)
        self._apply_filters()

    # --- only favorites ---
    def set_only_favorites(self, value: bool) -> None:
        """Apply «Solo favoritos» of the Ver menu.

        With it on, group menus show only marked actions, and a group
        with none disappears from the bar instead of staying as an empty
        menu.
        """
        if value == self._only_favorites:
            return
        self._only_favorites = value
        self._only_favorites_action.blockSignals(True)
        self._only_favorites_action.setChecked(value)
        self._only_favorites_action.blockSignals(False)
        self._apply_filters()

    def set_favorites(self, ids: set[str]) -> None:
        """React to a favorite marked on another surface.

        That is the search's stripe or the star of the parameters
        header.
        """
        if ids == self._favorites:
            return
        self._favorites = set(ids)
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply the bar's two filters in one pass.

        What does not apply to this repo and, with the switch on, what
        is not marked.
        """
        for menu in self._group_menus:
            alive = 0
            for separator, cap_ids in self._blocks[menu]:
                visible = 0
                for cap_id in cap_ids:
                    see = (self._applicable is None or cap_id in self._applicable) and (
                        not self._only_favorites or cap_id in self._favorites
                    )
                    self._actions[cap_id].setVisible(see)
                    visible += int(see)
                # A line only separates if something remains on both
                # sides.
                if separator is not None:
                    separator.setVisible(visible > 0 and alive > 0)
                alive += visible
            menu.menuAction().setVisible(alive > 0)


def _tooltip(cap: Capability) -> str:
    """Return the same content as a search row's tooltip.

    That is `ActionRow._tooltip`: what it does, its level and how the
    entry is used.
    """
    composite = bool(cap.composed_of or len(cap.steps) > 1)
    level = "Compuesta · encadena varias atómicas" if composite else "Atómica · un solo paso"
    if cap.is_machine_wide:
        level += " · de la máquina, no del repo"
    lines = [f"<b>{cap.name}</b>"]
    if cap.description:
        lines.append(cap.description)
    lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>{level}</span>")
    lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>Clic para abrir</span>")
    return "<br>".join(lines)
