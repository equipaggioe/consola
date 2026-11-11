"""Which role of the palette paints each part of the window.

The ONE place to change it. A widget never names a role (`pal.bg`,
`Colors.TEXT_DIM`): it asks for its part
(`parts.SECTION_HEADER.on(pal)`) and reads the slot it paints
(`.bg`, `.fg`, `.border`, `.hover`, `.focus`). To repaint a part,
change the role here.

Roles are a `Role` member and not a loose string: typing `Role.` the
editor lists them all, and a role that does not exist fails on import,
not on screen.

Slots:

- `bg`: the background.
- `fg`: the text (or the glyph) over that background.
- `border`: the outline or the dividing line.
- `hover`: the background under the cursor (for a list, the selected
  row).
- `focus`: the border with focus (for the window, its outline while
  active).

A part declares only the slots it paints; asking for another raises.
`tests/test_palettes.py` checks that every part resolves in the eight
themes and that its text reads over its background.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum

from app.theme import Colors
from app.ui.palettes import Palette


class Role(Enum):
    """A color the parts can take.

    The first ten come from the repo's palette (`ui/palettes.py`): the
    accent and the ladder of backgrounds tinted with it. The four
    `TEXT*` are the grays of `theme.py`, the same in every theme.
    """

    ACCENT = "accent"
    ON_ACCENT = "on_accent"  # legible over the accent
    CHROME = "chrome"
    BG = "bg"
    PANEL = "panel"
    SURFACE = "surface"
    SURFACE_HOVER = "surface_hover"
    SURFACE_ALT = "surface_alt"
    BORDER = "border"
    BORDER_LIGHT = "border_light"
    TEXT = "TEXT"
    TEXT_LABEL = "TEXT_LABEL"
    TEXT_DIM = "TEXT_DIM"
    TEXT_MUTED = "TEXT_MUTED"


_GRAYS = {Role.TEXT, Role.TEXT_LABEL, Role.TEXT_DIM, Role.TEXT_MUTED}


def color(role: Role, pal: Palette) -> str:
    """Return the hex of that role in that palette."""
    return getattr(Colors if role in _GRAYS else pal, role.value)


@dataclass(frozen=True)
class Look:
    """The roles of one part, slot by slot."""

    bg: Role | None = None
    fg: Role | None = None
    border: Role | None = None
    hover: Role | None = None
    focus: Role | None = None

    def on(self, pal: Palette) -> Paint:
        """Return this part's colors in that palette."""
        return Paint(self, pal)

    def slots(self) -> dict[str, Role]:
        """Return the slots it declares."""
        return {f.name: role for f in fields(self) if (role := getattr(self, f.name)) is not None}


@dataclass(frozen=True)
class Paint:
    """A part's colors already resolved against one palette."""

    look: Look
    pal: Palette

    def _slot(self, slot: str) -> str:
        role = getattr(self.look, slot)
        if role is None:
            raise LookupError(f"{self.look} does not declare «{slot}»")
        return color(role, self.pal)

    @property
    def bg(self) -> str:
        """Return the background."""
        return self._slot("bg")

    @property
    def fg(self) -> str:
        """Return the text."""
        return self._slot("fg")

    @property
    def border(self) -> str:
        """Return the outline."""
        return self._slot("border")

    @property
    def hover(self) -> str:
        """Return the background under the cursor."""
        return self._slot("hover")

    @property
    def focus(self) -> str:
        """Return the border with focus."""
        return self._slot("focus")


# --- top of the window ------------------------------------------------

# The whole first row: the brand, the window buttons.
TITLE_BAR = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT)
# The repo tabs that are not selected, painted with the ACTIVE repo's
# palette: they rest on the title bar.
REPO_TAB = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT, border=Role.ON_ACCENT)
# The selected repo tab, with its own palette: it joins the menu row.
REPO_TAB_SELECTED = Look(bg=Role.CHROME, fg=Role.ACCENT)
# The «+» that adds a repo.
ADD_TAB = Look(fg=Role.ON_ACCENT, border=Role.ON_ACCENT)
# What is behind everything, and the outline of the frameless window.
WINDOW = Look(bg=Role.BG, border=Role.BORDER, focus=Role.ACCENT)
# The menu row; `hover` is the title of the open menu.
MENU_BAR = Look(bg=Role.CHROME, fg=Role.TEXT, border=Role.BORDER, hover=Role.PANEL)
# A popup of the menu bar; `border` is also its separators.
MENU = Look(bg=Role.PANEL, fg=Role.TEXT, border=Role.BORDER_LIGHT)
# The item under the cursor in a menu.
MENU_ITEM = Look(bg=Role.SURFACE_HOVER, fg=Role.ACCENT)
# The action search's list; `border` is also its scroll bar.
SEARCH_LIST = Look(bg=Role.PANEL, border=Role.BORDER_LIGHT)

# --- left: runs -------------------------------------------------------

# The bar with the run tabs.
RUN_BAR = Look(bg=Role.PANEL, border=Role.BORDER)
# A run tab that is not active.
RUN_TAB = Look(bg=Role.PANEL, fg=Role.TEXT_MUTED, border=Role.BORDER_LIGHT)
# The active run tab, open into the console below it.
RUN_TAB_ACTIVE = Look(bg=Role.BG, fg=Role.TEXT, border=Role.BORDER)
# The bar under the run tabs that names the view: «CONSOLA».
CONSOLE_HEADER = Look(bg=Role.BG, fg=Role.TEXT_DIM, border=Role.BORDER)
# Behind the console and the second view.
CANVAS = Look(bg=Role.BG)
# The output of a run.
CONSOLE = Look(bg=Role.BG, fg=Role.TEXT_DIM)
# The strip above the console, the browser and the database.
TOOL_BAR = Look(bg=Role.SURFACE, border=Role.BORDER)
# The small buttons of those bars.
CHIP = Look(bg=Role.SURFACE_ALT, fg=Role.TEXT_DIM)

# --- left: database ---------------------------------------------------

# The grid and the tree; `border` is the grid lines, `hover` the
# selected row.
TABLE = Look(bg=Role.BG, fg=Role.TEXT, border=Role.SURFACE, hover=Role.SURFACE_HOVER)
# Every other row of the grid.
TABLE_ALT_ROW = Look(bg=Role.PANEL)
# The column titles.
TABLE_HEADER = Look(bg=Role.SURFACE, fg=Role.TEXT_DIM, border=Role.BORDER)
# The tree's column, left of the grid.
TABLE_TREE = Look(bg=Role.BG, border=Role.BORDER)
# The tab of the explorer that is open (Datos, Columnas…).
TABLE_TAB = Look(fg=Role.TEXT, border=Role.ACCENT)

# --- right: sections --------------------------------------------------

# The clickable bar with a section's name.
SECTION_HEADER = Look(bg=Role.BG, fg=Role.TEXT_DIM, border=Role.BORDER, hover=Role.SURFACE_HOVER)
# The bar to drag between two open sections.
SECTION_GRIP = Look(bg=Role.SURFACE, border=Role.BORDER, hover=Role.SURFACE_HOVER)
# What a section holds, with its scroll bar.
SECTION_BODY = Look(bg=Role.PANEL)
# The bottom strip of a panel: Limpiar · Ejecutar, Guardar · Recargar.
FOOTER = Look(bg=Role.SURFACE, border=Role.BORDER)
# Text fields and closed lists.
FIELD = Look(bg=Role.SURFACE_ALT, fg=Role.TEXT, border=Role.BORDER, focus=Role.ACCENT)
# A field of «Configuración del repo» whose key has no value.
FIELD_EMPTY = Look(border=Role.BORDER_LIGHT)
# The open list of a combo; `hover` is the selected entry.
COMBO_LIST = Look(bg=Role.SURFACE_ALT, fg=Role.TEXT, border=Role.BORDER, hover=Role.ACCENT)
# The fill of a marked check box.
CHECK = Look(bg=Role.ACCENT, border=Role.ACCENT)
# Ejecutar, when it can run.
RUN_BUTTON = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT)
# Ejecutar, when it cannot.
RUN_BUTTON_OFF = Look(bg=Role.SURFACE_ALT, fg=Role.TEXT_MUTED)
# Outlined buttons: Limpiar, Simulacro, Cancelar.
BUTTON = Look(fg=Role.TEXT_DIM, border=Role.BORDER, hover=Role.SURFACE_HOVER)
# Outlined buttons in the accent: Crear, Importar, Guardar, Recargar.
ACCENT_BUTTON = Look(fg=Role.ACCENT, border=Role.ACCENT, hover=Role.SURFACE_HOVER)
# Filled buttons: «Entendido», «Abrir en el navegador del sistema».
FILLED_BUTTON = Look(
    bg=Role.SURFACE_ALT, fg=Role.TEXT, border=Role.BORDER, hover=Role.SURFACE_HOVER
)

# --- bottom and dialogs -----------------------------------------------

# The bottom bar with padlocks, tools and RAM.
STATUS_BAR = Look(bg=Role.SURFACE, border=Role.BORDER)
# A closed padlock (the open one is red in every theme).
PADLOCK = Look(fg=Role.ACCENT)
# The notices of the destructive guard.
DIALOG = Look(bg=Role.PANEL, fg=Role.TEXT)
# The repo's card in those notices.
REPO_CARD = Look(bg=Role.SURFACE_ALT, fg=Role.ACCENT, border=Role.ACCENT)
