"""The top menu bar of actions."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QSettings, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QMenuBar, QMessageBox, QSizePolicy, QWidget

from app import theme
from app.services import favorites, language, motion, section_visibility
from app.services.palettes import NEUTRAL, Palette
from app.services.registry import Capability, registry
from app.theme import Colors

# A text marker and not custom paint: a `QMenu` does not allow tinting
# one item, and this reads just as well without a `QWidgetAction`, which
# would reimplement `ActionRow` inside the popup.
MARK_DANGER = "⚠"  # destructive: check before pressing

# Each translation's name in itself, as «Idioma» lists it: whoever does
# not read the current language still finds theirs. Not from
# `QLocale.nativeLanguageName()`, which names the default region too:
# «español de España», «American English».
LANGUAGE_NAMES = {"en": "English", "es": "Español"}


def chosen_language() -> str:
    """Return the tag saved under `language.KEY`, or "" if none."""
    return str(QSettings().value(language.KEY, ""))


def choose_language(tag: str) -> None:
    """Save the choice, which `language.install` applies on next start.

    "" forgets it, and the system's language rules again.
    """
    settings = QSettings()
    if tag:
        settings.setValue(language.KEY, tag)
    else:
        settings.remove(language.KEY)


class ActionMenuBar(QMenuBar):
    """The top menu bar: the whole action catalog one hover away.

    No accordion, and it takes no width. A click opens the action's tab
    through the same signal as the search on the same row
    (`widgets/action_search.py`), so `MainWindow` cannot tell where the
    click came from. Running at once is left to the search's ▶.
    """

    action_requested = Signal(str)  # capability_id: open its tab
    only_favorites_toggled = Signal(bool)
    section_toggled = Signal(str, bool)  # section id, visible

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the menus from the registry."""
        super().__init__(parent)
        self.pal = NEUTRAL
        theme.MENU_BAR.on(self.pal).dress(self, fill=False)
        # Narrower than its menus, it puts the last ones in «»». A
        # `QMenuBar` does not shrink below its hint by itself, and its
        # hint, with every menu, kept the window wider than a 1920 px
        # screen at 200 %.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

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
        # (`services/catalog.py::applicable_ids`). None = no repo yet:
        # nothing is filtered.
        self._applicable: set[str] | None = None

        self._build_action_menus()
        self._build_view_menu()

        self.set_project_active(False)
        self._apply_filters()

    # --- palette ---
    def set_palette(self, pal: Palette) -> None:
        """Repaint the open menus: they belong to the open repo too.

        The name of the item under the cursor goes in the repo's accent,
        Highlight in the palette of its theme.
        """
        self.pal = pal
        # The open menu's title takes the popup's background (`hover`),
        # so they read as one piece; `Style` draws both.
        theme.MENU_BAR.on(pal).dress(self, fill=False)
        for menu in self._menus:
            theme.workspace(menu, pal)

    def _add_menu(self, title: str) -> QMenu:
        menu = self.addMenu(title)
        theme.workspace(menu, self.pal)
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
        menus in a row, and in a narrow window the emoji is the first
        thing that pushes the last ones into overflow.
        """
        for group, capabilities in registry.get_groups().items():
            # The group is a key: the catalog declares it untranslated.
            menu = self._add_menu(QCoreApplication.translate("catalog", group))
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
        """Build «Solo favoritos», the visible sections and what moves.

        All are preferences of the app, not of the repo: they hold for
        every tab. The checks are read again on opening the menu, since
        a section also hides from its header's right click.

        «Animaciones» stops the console's cursor and the pulse of the
        LEDs, and «RAM disponible» hides the RAM of the status bar,
        which refreshes by itself (`services/motion.py`).
        """
        menu = self._add_menu(QCoreApplication.translate("ActionMenuBar", "Ver"))
        self._view_menu = menu
        self._only_favorites_action = QAction(
            QCoreApplication.translate("ActionMenuBar", "Solo favoritos"), self
        )
        self._only_favorites_action.setCheckable(True)
        self._only_favorites_action.setChecked(self._only_favorites)
        self._only_favorites_action.toggled.connect(self.only_favorites_toggled.emit)
        menu.addAction(self._only_favorites_action)

        menu.addSeparator()
        self._section_actions: dict[str, QAction] = {}
        for section_id in section_visibility.SECTIONS:
            action = QAction(section_visibility.title(section_id), self)
            action.setCheckable(True)

            def on_section(visible: bool, s: str = section_id) -> None:
                self.section_toggled.emit(s, visible)

            action.toggled.connect(on_section)
            self._section_actions[section_id] = action
            menu.addAction(action)

        menu.addSeparator()
        self.animations_action = QAction(
            QCoreApplication.translate("ActionMenuBar", "Animaciones"), self
        )
        self.animations_action.setCheckable(True)
        self.animations_action.setChecked(motion.animated())
        self.animations_action.toggled.connect(motion.set_animated)
        menu.addAction(self.animations_action)
        self.ram_action = QAction(
            QCoreApplication.translate("ActionMenuBar", "RAM disponible"), self
        )
        self.ram_action.setCheckable(True)
        self.ram_action.setChecked(motion.ram_shown())
        self.ram_action.toggled.connect(motion.set_ram_shown)
        menu.addAction(self.ram_action)
        menu.addSeparator()
        self._build_language_menu(menu)
        menu.aboutToShow.connect(self._sync_view_checks)

    def _build_language_menu(self, view: QMenu) -> None:
        """Build «Idioma»: the system's, or one of the translations.

        The choice applies on the next start, and a message says so:
        every widget sets its texts when it is built, after
        `language.install`.
        """
        menu = view.addMenu(QCoreApplication.translate("ActionMenuBar", "Idioma"))
        self.language_actions: dict[str, QAction] = {}
        group = QActionGroup(self)
        current = chosen_language()
        options = [("", QCoreApplication.translate("ActionMenuBar", "El del sistema"))]
        options += [(tag, LANGUAGE_NAMES[tag]) for tag in language.offered()]
        for tag, label in options:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(tag == current)
            group.addAction(action)
            action.triggered.connect(lambda _=False, t=tag: self._choose_language(t))
            self.language_actions[tag] = action
            menu.addAction(action)

    def _choose_language(self, tag: str) -> None:
        if tag == chosen_language():
            return
        choose_language(tag)
        notice = QMessageBox(
            QMessageBox.Icon.Information,
            QCoreApplication.translate("ActionMenuBar", "Idioma"),
            QCoreApplication.translate(
                "ActionMenuBar", "El idioma cambia la próxima vez que se abra Consola."
            ),
            QMessageBox.StandardButton.Ok,
            self.window(),
        )
        notice.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        notice.open()

    @Slot()
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
    level = (
        QCoreApplication.translate("action_menu_bar", "Compuesta · encadena varias atómicas")
        if composite
        else QCoreApplication.translate("action_menu_bar", "Atómica · un solo paso")
    )
    if cap.is_machine_wide:
        level += QCoreApplication.translate("action_menu_bar", " · de la máquina, no del repo")
    lines = [f"<b>{cap.name}</b>"]
    if cap.description:
        lines.append(cap.description)
    lines.append(f"<span style='color:{Colors.ON_SURFACE_VARIANT};'>{level}</span>")
    lines.append(
        QCoreApplication.translate(
            "action_menu_bar", "<span style='color:{0};'>Clic para abrir</span>"
        ).format(Colors.ON_SURFACE_VARIANT)
    )
    return "<br>".join(lines)
