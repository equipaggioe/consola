"""The sizes, the style sheet and the parts of the app.

The colors come from `colors.py`, generated from `brand/tokens/`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication

from app.colors import INITIAL

if TYPE_CHECKING:
    # Only for the annotations: `services/palettes.py` imports this
    # module.
    from app.services.palettes import Palette

# The scheme of the theme without a repo. What is the same in every
# theme, the surfaces, the text and the states, is read from it.
SCHEME = INITIAL.dark

# The opacities of the state layers of Material.
HOVER = 0.08
DISABLED = 0.38


def blend(over: str, base: str, opacity: float) -> str:
    """Return `over` laid on `base` at that opacity, as #rrggbb.

    It is how Material paints a state layer: the color of the content,
    faint, on its container.
    """
    mixed = (
        round(int(over[i : i + 2], 16) * opacity + int(base[i : i + 2], 16) * (1 - opacity))
        for i in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


class Colors:
    """The roles that are the same in every theme.

    By the names the style sheets of the widgets still give them.
    """

    INK = SCHEME["on_primary"]
    CHROME = SCHEME["primary_container"]
    BG = SCHEME["surface"]
    PANEL = SCHEME["surface_container_low"]
    SURFACE = SCHEME["surface_container"]
    SURFACE_HOVER = SCHEME["surface_container_high"]
    SURFACE_ALT = SCHEME["surface_container_highest"]
    BORDER = SCHEME["outline_variant"]
    BORDER_LIGHT = SCHEME["outline"]
    TEXT = SCHEME["on_surface"]
    TEXT_LABEL = SCHEME["on_surface"]
    TEXT_DIM = SCHEME["on_surface_variant"]
    TEXT_MUTED = SCHEME["on_surface_variant"]
    # Disabled text, on the body of a section.
    TEXT_DISABLED = blend(SCHEME["on_surface"], SCHEME["surface_container_low"], DISABLED)
    ACCENT = SCHEME["primary"]
    ACCENT_PURPLE = SCHEME["tertiary"]
    SUCCESS = SCHEME["success"]
    WARNING = SCHEME["warning"]
    ERROR = SCHEME["error"]
    ON_ERROR = SCHEME["on_error"]
    INACTIVE = SCHEME["outline"]


class Fonts:
    """The font families and sizes."""

    FAMILY = '"Inter", "Segoe UI", "Helvetica Neue", sans-serif'
    MONO = '"Cascadia Code", "Fira Code", "Consolas", monospace'
    SIZE_XS = 12
    SIZE_SM = 13
    SIZE_BASE = 15
    SIZE_LG = 17
    SIZE_XL = 21
    SIZE_XXL = 30
    SIZE_MONO = 15


class Spacing:
    """The spacing steps."""

    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


class Radius:
    """The corner radii."""

    SM = 4
    MD = 8
    LG = 12
    XL = 16


def tint(hex_color: str, alpha: float) -> str:
    """Return a #rrggbb at that opacity, as #aarrggbb, for halos."""
    return f"#{round(alpha * 255):02x}{hex_color[1:]}"


def mono(font: QFont) -> QFont:
    """Return `font` with the theme's fixed-width family (`Fonts.MONO`).

    All the families go, in order, with the kind as the last word: on a
    machine that has none of them, such as a Linux without Cascadia or
    Consolas, Qt picks another fixed-width font instead of falling back
    to the default proportional one.
    """
    families = [f.strip().strip('"') for f in Fonts.MONO.split(",")]
    font.setFamilies([f for f in families if f != "monospace"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def apply_theme(app: QApplication) -> None:
    """Set the font, the style sheet and the palette of the app."""
    font = QFont()
    font.setFamily("Inter")
    font.setPixelSize(Fonts.SIZE_BASE)
    app.setFont(font)

    app.setStyleSheet(global_stylesheet())
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, Colors.BG)
    palette.setColor(QPalette.ColorRole.WindowText, Colors.TEXT)
    palette.setColor(QPalette.ColorRole.Base, Colors.SURFACE)
    palette.setColor(QPalette.ColorRole.AlternateBase, Colors.SURFACE_ALT)
    palette.setColor(QPalette.ColorRole.ToolTipBase, Colors.SURFACE_ALT)
    palette.setColor(QPalette.ColorRole.ToolTipText, Colors.TEXT)
    palette.setColor(QPalette.ColorRole.Text, Colors.TEXT)
    palette.setColor(QPalette.ColorRole.Button, Colors.SURFACE)
    palette.setColor(QPalette.ColorRole.ButtonText, Colors.TEXT)
    palette.setColor(QPalette.ColorRole.Link, Colors.ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight, Colors.ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, Colors.BG)
    app.setPalette(palette)


def check_css(fill: str, border: str) -> str:
    """Return the rules of a marked check box, filled with `fill`.

    The global sheet uses it with the neutral accent; a panel of a repo
    repeats it with its palette's (`theme.py::CHECK`), and being
    closer to the box, it wins. The disabled one goes along: a closer
    `:checked` would also paint it, and disabled it is gray.
    """
    return f"""
    QCheckBox::indicator:checked {{
        background: {fill};
        border: 1px solid {border};
        image: none;
    }}
    QCheckBox::indicator:checked:disabled {{
        background: {Colors.TEXT_DISABLED};
        border: 1px solid {Colors.TEXT_DISABLED};
    }}
    """


def global_stylesheet() -> str:
    """Return the app's global style sheet."""
    return f"""
    QWidget {{
        background-color: {Colors.BG};
        color: {Colors.TEXT};
        font-family: {Fonts.FAMILY};
        font-size: {Fonts.SIZE_BASE}px;
    }}
    QScrollBar {{
        background: transparent;
        width: 8px;
        height: 8px;
    }}
    QScrollBar::handle {{
        background: {Colors.BORDER_LIGHT};
        border-radius: {Radius.SM}px;
    }}
    QScrollBar::handle:hover {{
        background: {Colors.TEXT_MUTED};
    }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none;
        border: none;
        width: 0px;
        height: 0px;
    }}
    QToolTip {{
        background-color: {Colors.SURFACE_ALT};
        color: {Colors.TEXT};
        border: 1px solid {Colors.ACCENT};
        border-radius: {Radius.SM}px;
        padding: {Spacing.SM}px;
        font-size: {Fonts.SIZE_SM}px;
    }}
    QMenu {{
        background-color: {Colors.SURFACE};
        color: {Colors.TEXT};
        border: 1px solid {Colors.BORDER};
        border-radius: {Radius.SM}px;
        padding: {Spacing.XS}px 0px;
        font-size: {Fonts.SIZE_BASE}px;
    }}
    QMenu::item {{
        padding: {Spacing.SM}px {Spacing.XL}px {Spacing.SM}px {Spacing.XL}px;
    }}
    QMenu::item:selected {{
        background-color: {Colors.SURFACE_HOVER};
        color: {Colors.ACCENT};
    }}
    QCheckBox {{
        background: transparent;
        color: {Colors.TEXT_LABEL};
        spacing: 9px;
        font-size: {Fonts.SIZE_SM}px;
    }}
    QCheckBox:hover {{
        color: {Colors.TEXT};
    }}
    QCheckBox:disabled {{
        color: {Colors.TEXT_DISABLED};
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border-radius: 4px;
        border: 1px solid {Colors.BORDER_LIGHT};
        background: {Colors.SURFACE_ALT};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {Colors.TEXT_DIM};
    }}
    {check_css(Colors.ACCENT, Colors.ACCENT)}
    QSplitter::handle {{
        background-color: {Colors.BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}
    """


# --- The parts of the window -----------------------------------------
#
# Which role of the color scheme paints each part of the window.
#
# The ONE place to change it. A widget never names a role: it asks for
# its part (`theme.SECTION_HEADER.on(pal)`) and reads the slot it paints
# (`.bg`, `.fg`, `.border`, `.hover`, `.focus`). To repaint a part,
# change the role here.
#
# The roles are those of the ColorScheme of Material, the names of
# `colors.py`, and a `Role` member and not a loose string: typing
# `Role.` the editor lists them, and a role that does not exist fails on
# import, not on screen. A slot can also take a `Layer`: a role laid
# faint on another, as Material paints the hover.
#
# Slots:
#
# - `bg`: the background.
# - `fg`: the text (or the glyph) over that background.
# - `border`: the outline or the dividing line.
# - `hover`: the background under the cursor (for a list, the selected
#   row).
# - `focus`: the border with focus (for the window, its outline while
#   active).
#
# A part declares only the slots it paints; asking for another raises.
# `tests/test_palettes.py` checks that every part resolves in every
# theme and that its text reads over its background.


class Role(Enum):
    """A role of the color scheme that the parts take.

    `primary` and the two containers change with the theme; the others
    are the same in all of them.
    """

    PRIMARY = "primary"
    ON_PRIMARY = "on_primary"
    PRIMARY_CONTAINER = "primary_container"
    ON_PRIMARY_CONTAINER = "on_primary_container"
    SECONDARY_CONTAINER = "secondary_container"
    ON_SECONDARY_CONTAINER = "on_secondary_container"
    SURFACE = "surface"
    SURFACE_CONTAINER_LOW = "surface_container_low"
    SURFACE_CONTAINER = "surface_container"
    SURFACE_CONTAINER_HIGH = "surface_container_high"
    SURFACE_CONTAINER_HIGHEST = "surface_container_highest"
    ON_SURFACE = "on_surface"
    ON_SURFACE_VARIANT = "on_surface_variant"
    OUTLINE = "outline"
    OUTLINE_VARIANT = "outline_variant"


@dataclass(frozen=True)
class Layer:
    """A role laid on another at an opacity, as a state layer."""

    over: Role
    base: Role
    opacity: float = HOVER


def color(slot: Role | Layer, pal: Palette) -> str:
    """Return the hex of that role, or that layer, in that palette."""
    if isinstance(slot, Layer):
        return blend(pal.colors[slot.over.value], pal.colors[slot.base.value], slot.opacity)
    return pal.colors[slot.value]


@dataclass(frozen=True)
class Look:
    """The roles of one part, slot by slot."""

    bg: Role | Layer | None = None
    fg: Role | Layer | None = None
    border: Role | Layer | None = None
    hover: Role | Layer | None = None
    focus: Role | Layer | None = None

    def on(self, pal: Palette) -> Paint:
        """Return this part's colors in that palette."""
        return Paint(self, pal)

    def slots(self) -> dict[str, Role | Layer]:
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


# Bands and headers carry the repo's color: the title bar, the menu row
# and the section headers. The bodies where one reads and types
# (console, section bodies, menus, fields, tables, footers, status bar)
# go in the surfaces, gray in every theme, so the window does not read
# as one tinted wash. A divider goes in `OUTLINE_VARIANT`, and the
# outline of a control, which has to show, in `OUTLINE`.

# --- top of the window ------------------------------------------------

# The whole first row: the brand, the window buttons.
TITLE_BAR = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY)
# The repo tabs that are not selected, painted with the ACTIVE repo's
# palette.
REPO_TAB = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY, border=Role.ON_PRIMARY)
# The selected repo tab, with its own palette: it joins the menu row
# (`MENU_BAR`, below).
REPO_TAB_SELECTED = Look(bg=Role.SECONDARY_CONTAINER, fg=Role.PRIMARY)
# The «+» that adds a repo.
ADD_TAB = Look(fg=Role.ON_PRIMARY, border=Role.ON_PRIMARY)

# What is behind everything, and the outline of the frameless window.
WINDOW = Look(bg=Role.SURFACE, border=Role.OUTLINE_VARIANT, focus=Role.PRIMARY)
# The menu row; `hover` is the title of the open menu, in the popup's
# color.
MENU_BAR = Look(
    bg=REPO_TAB_SELECTED.bg,
    fg=Role.ON_SECONDARY_CONTAINER,
    border=Role.OUTLINE_VARIANT,
    hover=Role.SURFACE_CONTAINER_LOW,
)
# A popup of the menu bar; `border` is also its separators.
MENU = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE, border=Role.OUTLINE)
# The item under the cursor in a menu.
MENU_ITEM = Look(bg=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_LOW), fg=Role.PRIMARY)
# The action search's field, on the menu row: in the repo's color, not
# in the gray of the other fields.
SEARCH_FIELD = Look(
    bg=Role.SECONDARY_CONTAINER,
    fg=Role.ON_SECONDARY_CONTAINER,
    border=Role.OUTLINE,
    focus=Role.PRIMARY,
)
# The action search's list; `border` is also its scroll bar.
SEARCH_LIST = Look(bg=Role.SURFACE_CONTAINER_LOW, border=Role.OUTLINE)

# --- headers ----------------------------------------------------------

# The clickable bar with a section's name. «CONSOLA» is the same part.
SECTION_HEADER = Look(
    bg=Role.PRIMARY_CONTAINER,
    fg=Role.ON_PRIMARY_CONTAINER,
    border=Role.OUTLINE_VARIANT,
    hover=Layer(Role.ON_PRIMARY_CONTAINER, Role.PRIMARY_CONTAINER),
)
# The bar under the run tabs that names the view («CONSOLA») and
# carries the endpoint the task published.
CONSOLE_HEADER = SECTION_HEADER

# --- left: runs -------------------------------------------------------

# The bar with the run tabs.
RUN_BAR = Look(bg=Role.SURFACE_CONTAINER_LOW, border=Role.OUTLINE_VARIANT)
# A run tab that is not active: its outline sets it apart from the bar.
RUN_TAB = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE_VARIANT, border=Role.OUTLINE)
# The active run tab, open into the header below it: the same `bg`.
RUN_TAB_ACTIVE = Look(
    bg=CONSOLE_HEADER.bg, fg=Role.ON_PRIMARY_CONTAINER, border=Role.OUTLINE_VARIANT
)
# Behind the console and the second view.
CANVAS = Look(bg=Role.SURFACE)
# The output of a run.
CONSOLE = Look(bg=Role.SURFACE, fg=Role.ON_SURFACE_VARIANT)
# The strip above the browser and the database.
TOOL_BAR = Look(bg=Role.SURFACE_CONTAINER, border=Role.OUTLINE_VARIANT)
# The small buttons of those bars.
CHIP = Look(bg=Role.SURFACE_CONTAINER_HIGHEST, fg=Role.ON_SURFACE_VARIANT)

# --- left: database ---------------------------------------------------

# The grid and the tree; `border` is the grid lines, `hover` the
# selected row.
TABLE = Look(
    bg=Role.SURFACE,
    fg=Role.ON_SURFACE,
    border=Role.SURFACE_CONTAINER,
    hover=Role.SECONDARY_CONTAINER,
)
# Every other row of the grid.
TABLE_ALT_ROW = Look(bg=Role.SURFACE_CONTAINER_LOW)
# The column titles.
TABLE_HEADER = Look(
    bg=Role.SURFACE_CONTAINER, fg=Role.ON_SURFACE_VARIANT, border=Role.OUTLINE_VARIANT
)
# The tree's column, left of the grid.
TABLE_TREE = Look(bg=Role.SURFACE, border=Role.OUTLINE_VARIANT)
# The tab of the explorer that is open (Datos, Columnas…).
TABLE_TAB = Look(fg=Role.ON_SURFACE, border=Role.PRIMARY)

# --- right: sections --------------------------------------------------

# What a section holds, with its scroll bar.
SECTION_BODY = Look(bg=Role.SURFACE_CONTAINER_LOW)
# The bar to drag between two open sections: the body's color, so it
# only shows on hover.
SECTION_GRIP = Look(
    bg=SECTION_BODY.bg,
    border=Role.OUTLINE_VARIANT,
    hover=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_LOW),
)
# The bottom strip of a panel: Limpiar · Ejecutar, Guardar · Recargar.
FOOTER = Look(bg=Role.SURFACE_CONTAINER, border=Role.OUTLINE_VARIANT)
# Text fields and closed lists.
FIELD = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    focus=Role.PRIMARY,
)
# A field of «Configuración del repo» whose key has no value: an outline
# lighter than a field's.
FIELD_EMPTY = Look(border=Role.ON_SURFACE_VARIANT)
# The open list of a combo; `hover` is the selected entry.
COMBO_LIST = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    hover=Role.PRIMARY,
)
# The fill of a marked check box.
CHECK = Look(bg=Role.PRIMARY, border=Role.PRIMARY)
# Ejecutar, when it can run.
RUN_BUTTON = Look(bg=Role.PRIMARY, fg=Role.ON_PRIMARY)
# Ejecutar, when it cannot: disabled text.
RUN_BUTTON_OFF = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_HIGHEST, DISABLED),
)
# Outlined buttons: Limpiar, Simulacro, Cancelar.
BUTTON = Look(
    fg=Role.ON_SURFACE_VARIANT,
    border=Role.OUTLINE,
    hover=Layer(Role.ON_SURFACE_VARIANT, Role.SURFACE_CONTAINER),
)
# Outlined buttons in the accent: Crear, Importar, Guardar, Recargar.
ACCENT_BUTTON = Look(
    fg=Role.PRIMARY,
    border=Role.PRIMARY,
    hover=Layer(Role.PRIMARY, Role.SURFACE_CONTAINER),
)
# Filled buttons: «Entendido», «Abrir en el navegador del sistema».
FILLED_BUTTON = Look(
    bg=Role.SURFACE_CONTAINER_HIGHEST,
    fg=Role.ON_SURFACE,
    border=Role.OUTLINE,
    hover=Layer(Role.ON_SURFACE, Role.SURFACE_CONTAINER_HIGHEST),
)

# --- bottom and dialogs -----------------------------------------------

# The bottom bar with padlocks, tools and RAM.
STATUS_BAR = Look(bg=Role.SURFACE_CONTAINER_HIGH, border=Role.OUTLINE_VARIANT)
# A closed padlock (the open one is red in every theme).
PADLOCK = Look(fg=Role.PRIMARY)
# The notices of the destructive guard.
DIALOG = Look(bg=Role.SURFACE_CONTAINER_LOW, fg=Role.ON_SURFACE)
# The repo's card in those notices: the one tinted plate in them.
REPO_CARD = Look(bg=Role.SECONDARY_CONTAINER, fg=Role.PRIMARY, border=Role.PRIMARY)
