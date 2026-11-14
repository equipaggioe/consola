"""The neutral colors, sizes and global style sheet of the app."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


class Colors:
    """The neutral colors. `ui/palettes.py` tints them per repo."""

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
    repeats it with its palette's (`ui/parts.py::CHECK`), and being
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
