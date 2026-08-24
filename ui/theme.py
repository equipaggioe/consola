from __future__ import annotations
from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication

class Colors:
    CHROME        = '#08090c'   # barra superior (nivel de repos) — la capa mas oscura
    BG            = '#0d1117'   # lienzo de contenido
    SURFACE       = '#1c212b'   # rail, sub-barra de pestanas, barra de estado
    SURFACE_HOVER = '#262d3a'
    SURFACE_ALT   = '#2f3745'   # campos de entrada, chips — la superficie mas clara
    BORDER        = '#3d4657'
    BORDER_LIGHT  = '#4e586a'
    TEXT          = '#f0f4f8'
    TEXT_DIM      = '#9aa4b2'
    TEXT_MUTED    = '#6b7484'
    ACCENT        = '#58a6ff'
    ACCENT_PURPLE = '#bc8cff'
    SUCCESS       = '#3fb950'
    WARNING       = '#d29922'
    ERROR         = '#f85149'
    INACTIVE      = '#4e586a'

class Fonts:
    FAMILY    = '"Inter", "Segoe UI", "Helvetica Neue", sans-serif'
    MONO      = '"Cascadia Code", "Fira Code", "Consolas", monospace'
    SIZE_XS   = 12
    SIZE_SM   = 13
    SIZE_BASE = 15
    SIZE_LG   = 17
    SIZE_XL   = 21
    SIZE_XXL  = 30
    SIZE_MONO = 15

class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32

class Radius:
    SM = 4
    MD = 8
    LG = 12
    XL = 16

def tint(hex_color: str, alpha: float) -> str:
    """rgba(...) a partir de un hex, para halos y fondos teñidos."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.2f})"

def apply_theme(app: QApplication) -> None:
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

def global_stylesheet() -> str:
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
        color: {Colors.TEXT_DIM};
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
        border: 1px solid {Colors.BORDER_LIGHT};
        background: {Colors.SURFACE_ALT};
    }}
    QCheckBox::indicator:hover {{
        border: 1px solid {Colors.TEXT_DIM};
    }}
    QCheckBox::indicator:checked {{
        background: {Colors.ACCENT};
        border: 1px solid {Colors.ACCENT};
        image: none;
    }}
    QCheckBox::indicator:checked:disabled {{
        background: {Colors.TEXT_MUTED};
        border: 1px solid {Colors.TEXT_MUTED};
    }}
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
