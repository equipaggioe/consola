"""The neutral colors, sizes, style sheet and parts of the app."""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    # Only for the annotations: `services/palettes.py` imports this
    # module.
    from app.services.palettes import Palette


class Colors:
    """The neutral colors, tinted per repo by `services/palettes.py`."""

    # dark ink over a light background (`on_color`); never a background
    INK = "#0a0b10"
    CHROME = "#262d3d"  # section headers and the console's
    BG = "#0d1117"  # content canvas: console and left canvas
    PANEL = "#1c212b"  # body of the right column's sections
    SURFACE = "#232935"  # tool bars, table headers and footers
    SURFACE_HOVER = "#2b3240"
    # input fields and chips: the lightest surface
    SURFACE_ALT = "#2f3745"
    BORDER = "#3d4657"
    BORDER_LIGHT = "#4e586a"
    TEXT = "#f0f4f8"
    TEXT_DIM = "#9aa4b2"
    # a field's label and a check box's: lighter than TEXT_DIM, short of
    # TEXT's white
    TEXT_LABEL = "#c6cfdb"
    TEXT_MUTED = "#6b7484"
    ACCENT = "#58a6ff"
    ACCENT_PURPLE = "#bc8cff"
    SUCCESS = "#3fb950"
    WARNING = "#d29922"
    ERROR = "#f85149"
    INACTIVE = "#4e586a"


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
    """Return rgba(...) from a hex, for halos and tinted backgrounds."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.2f})"


def on_color(hex_color: str) -> str:
    """Return legible text over that color (WCAG relative luminance)."""
    c = QColor(hex_color)

    def lin(channel: int) -> float:
        v = channel / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())
    return Colors.INK if lum > 0.18 else Colors.TEXT


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
    palette.setColor(QPalette.ColorRole.Window, QColor(Colors.BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(Colors.SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(Colors.SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(Colors.SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(Colors.SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Colors.TEXT))
    palette.setColor(QPalette.ColorRole.Link, QColor(Colors.ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Colors.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Colors.BG))
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
        background: {Colors.TEXT_MUTED};
        border: 1px solid {Colors.TEXT_MUTED};
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
        color: {Colors.TEXT_MUTED};
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border-radius: 4px;
        border: 1px solid {Colors.BORDER};
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
# Which role of the palette paints each part of the window.
#
# The ONE place to change it. A widget never names a role (`pal.bg`,
# `Colors.TEXT_DIM`): it asks for its part
# (`theme.SECTION_HEADER.on(pal)`) and reads the slot it paints
# (`.bg`, `.fg`, `.border`, `.hover`, `.focus`). To repaint a part,
# change the role here.
#
# Roles are a `Role` member and not a loose string: typing `Role.` the
# editor lists them all, and a role that does not exist fails on import,
# not on screen.
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
# `tests/test_palettes.py` checks that every part resolves in the eight
# themes and that its text reads over its background.


class Role(Enum):
    """A color the parts can take.

    The first ten come from the repo's palette (`services/palettes.py`):
    the accent and the ladder of backgrounds tinted with it. The
    `GRAY_*` are the same steps without the tint, the neutrals of
    `theme.py`: same luminance, so swapping one for the other moves no
    contrast. The four `TEXT*` are the grays of the text. Neither
    changes with the theme.
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
    GRAY_BG = "gray_bg"
    GRAY_PANEL = "gray_panel"
    GRAY_SURFACE = "gray_surface"
    GRAY_SURFACE_HOVER = "gray_surface_hover"
    GRAY_SURFACE_ALT = "gray_surface_alt"
    GRAY_BORDER = "gray_border"
    GRAY_BORDER_LIGHT = "gray_border_light"
    TEXT = "TEXT"
    TEXT_LABEL = "TEXT_LABEL"
    TEXT_DIM = "TEXT_DIM"
    TEXT_MUTED = "TEXT_MUTED"


# The roles that are the same in every theme.
_FIXED = {
    Role.GRAY_BG: Colors.BG,
    Role.GRAY_PANEL: Colors.PANEL,
    Role.GRAY_SURFACE: Colors.SURFACE,
    Role.GRAY_SURFACE_HOVER: Colors.SURFACE_HOVER,
    Role.GRAY_SURFACE_ALT: Colors.SURFACE_ALT,
    Role.GRAY_BORDER: Colors.BORDER,
    Role.GRAY_BORDER_LIGHT: Colors.BORDER_LIGHT,
    Role.TEXT: Colors.TEXT,
    Role.TEXT_LABEL: Colors.TEXT_LABEL,
    Role.TEXT_DIM: Colors.TEXT_DIM,
    Role.TEXT_MUTED: Colors.TEXT_MUTED,
}


def color(role: Role, pal: Palette) -> str:
    """Return the hex of that role in that palette."""
    return _FIXED[role] if role in _FIXED else getattr(pal, role.value)


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


# Bands, headers and menus carry the repo's color: the title bar, the
# menu row and its popups, the run tabs and the section headers. The
# bodies where one reads and types (console, section bodies, fields,
# tables, footers, status bar) go in the gray steps, so the window does
# not read as one tinted wash.

# --- top of the window ------------------------------------------------

# The whole first row: the brand, the window buttons.
TITLE_BAR = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT)
# The repo tabs that are not selected, painted with the ACTIVE repo's
# palette.
REPO_TAB = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT, border=Role.ON_ACCENT)
# The selected repo tab, with its own palette: it joins the menu row
# (`MENU_BAR`, below).
REPO_TAB_SELECTED = Look(bg=Role.SURFACE_ALT, fg=Role.ACCENT)
# The «+» that adds a repo.
ADD_TAB = Look(fg=Role.ON_ACCENT, border=Role.ON_ACCENT)

# What is behind everything, and the outline of the frameless window.
WINDOW = Look(bg=Role.GRAY_BG, border=Role.BORDER, focus=Role.ACCENT)
# The menu row; `hover` is the title of the open menu.
MENU_BAR = Look(bg=REPO_TAB_SELECTED.bg, fg=Role.TEXT, border=Role.BORDER, hover=Role.PANEL)
# A popup of the menu bar; `border` is also its separators.
MENU = Look(bg=Role.PANEL, fg=Role.TEXT, border=Role.BORDER_LIGHT)
# The item under the cursor in a menu.
MENU_ITEM = Look(bg=Role.SURFACE_HOVER, fg=Role.ACCENT)
# The action search's field, on the menu row: in the repo's color, not
# in the gray of the other fields.
SEARCH_FIELD = Look(bg=Role.SURFACE_ALT, fg=Role.TEXT, border=Role.GRAY_BORDER, focus=Role.ACCENT)
# The action search's list; `border` is also its scroll bar.
SEARCH_LIST = Look(bg=Role.PANEL, border=Role.BORDER_LIGHT)

# --- headers ----------------------------------------------------------

# The clickable bar with a section's name. «CONSOLA» is the same part.
SECTION_HEADER = Look(bg=Role.CHROME, fg=Role.TEXT, border=Role.BORDER, hover=Role.SURFACE_HOVER)
# The bar under the run tabs that names the view («CONSOLA») and
# carries the endpoint the task published.
CONSOLE_HEADER = SECTION_HEADER

# --- left: runs -------------------------------------------------------

# The bar with the run tabs.
RUN_BAR = Look(bg=Role.GRAY_PANEL, border=Role.BORDER)
# A run tab that is not active: the bar's step in the repo's hue, so the
# tint is what sets it apart from the gray bar.
RUN_TAB = Look(bg=Role.PANEL, fg=Role.TEXT_DIM, border=Role.BORDER_LIGHT)
# The active run tab, open into the header below it: the same `bg`.
RUN_TAB_ACTIVE = Look(bg=CONSOLE_HEADER.bg, fg=Role.TEXT, border=Role.BORDER)
# Behind the console and the second view.
CANVAS = Look(bg=Role.GRAY_BG)
# The output of a run.
CONSOLE = Look(bg=Role.GRAY_BG, fg=Role.TEXT_DIM)
# The strip above the browser and the database.
TOOL_BAR = Look(bg=Role.GRAY_SURFACE, border=Role.GRAY_BORDER)
# The small buttons of those bars.
CHIP = Look(bg=Role.GRAY_SURFACE_ALT, fg=Role.TEXT_DIM)

# --- left: database ---------------------------------------------------

# The grid and the tree; `border` is the grid lines, `hover` the
# selected row.
TABLE = Look(bg=Role.GRAY_BG, fg=Role.TEXT, border=Role.GRAY_SURFACE, hover=Role.SURFACE_HOVER)
# Every other row of the grid.
TABLE_ALT_ROW = Look(bg=Role.GRAY_PANEL)
# The column titles.
TABLE_HEADER = Look(bg=Role.GRAY_SURFACE, fg=Role.TEXT_DIM, border=Role.GRAY_BORDER)
# The tree's column, left of the grid.
TABLE_TREE = Look(bg=Role.GRAY_BG, border=Role.GRAY_BORDER)
# The tab of the explorer that is open (Datos, Columnas…).
TABLE_TAB = Look(fg=Role.TEXT, border=Role.ACCENT)

# --- right: sections --------------------------------------------------

# What a section holds, with its scroll bar.
SECTION_BODY = Look(bg=Role.GRAY_PANEL)
# The bar to drag between two open sections: the body's color, so it
# only shows on hover.
SECTION_GRIP = Look(bg=SECTION_BODY.bg, border=Role.BORDER, hover=Role.GRAY_SURFACE_HOVER)
# The bottom strip of a panel: Limpiar · Ejecutar, Guardar · Recargar.
FOOTER = Look(bg=Role.GRAY_SURFACE, border=Role.GRAY_BORDER)
# Text fields and closed lists.
FIELD = Look(bg=Role.GRAY_SURFACE_ALT, fg=Role.TEXT, border=Role.GRAY_BORDER, focus=Role.ACCENT)
# A field of «Configuración del repo» whose key has no value.
FIELD_EMPTY = Look(border=Role.GRAY_BORDER_LIGHT)
# The open list of a combo; `hover` is the selected entry.
COMBO_LIST = Look(
    bg=Role.GRAY_SURFACE_ALT, fg=Role.TEXT, border=Role.GRAY_BORDER, hover=Role.ACCENT
)
# The fill of a marked check box.
CHECK = Look(bg=Role.ACCENT, border=Role.ACCENT)
# Ejecutar, when it can run.
RUN_BUTTON = Look(bg=Role.ACCENT, fg=Role.ON_ACCENT)
# Ejecutar, when it cannot.
RUN_BUTTON_OFF = Look(bg=Role.GRAY_SURFACE_ALT, fg=Role.TEXT_MUTED)
# Outlined buttons: Limpiar, Simulacro, Cancelar.
BUTTON = Look(fg=Role.TEXT_DIM, border=Role.GRAY_BORDER, hover=Role.GRAY_SURFACE_HOVER)
# Outlined buttons in the accent: Crear, Importar, Guardar, Recargar.
ACCENT_BUTTON = Look(fg=Role.ACCENT, border=Role.ACCENT, hover=Role.GRAY_SURFACE_HOVER)
# Filled buttons: «Entendido», «Abrir en el navegador del sistema».
FILLED_BUTTON = Look(
    bg=Role.GRAY_SURFACE_ALT,
    fg=Role.TEXT,
    border=Role.GRAY_BORDER,
    hover=Role.GRAY_SURFACE_HOVER,
)

# --- bottom and dialogs -----------------------------------------------

# The bottom bar with padlocks, tools and RAM.
STATUS_BAR = Look(bg=Role.GRAY_SURFACE_HOVER, border=Role.BORDER)
# A closed padlock (the open one is red in every theme).
PADLOCK = Look(fg=Role.ACCENT)
# The notices of the destructive guard.
DIALOG = Look(bg=Role.GRAY_PANEL, fg=Role.TEXT)
# The repo's card in those notices: the one tinted plate in them.
REPO_CARD = Look(bg=Role.SURFACE_ALT, fg=Role.ACCENT, border=Role.ACCENT)
