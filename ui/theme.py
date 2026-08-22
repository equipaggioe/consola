from __future__ import annotations
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

class Colors:
    BG            = '#0d1117'
    SURFACE       = '#161b22'
    SURFACE_HOVER = '#1c2128'
    SURFACE_ALT   = '#21262d'
    BORDER        = '#30363d'
    BORDER_LIGHT  = '#3d444d'
    TEXT          = '#e6edf3'
    TEXT_DIM      = '#8b949e'
    TEXT_MUTED    = '#484f58'
    ACCENT        = '#58a6ff'
    ACCENT_PURPLE = '#bc8cff'
    SUCCESS       = '#3fb950'
    WARNING       = '#d29922'
    ERROR         = '#f85149'
    INACTIVE      = '#484f58'

class Fonts:
    FAMILY    = '"Inter", "Segoe UI", "Helvetica Neue", sans-serif'
    MONO      = '"Cascadia Code", "Fira Code", "Consolas", monospace'
    SIZE_SM   = 11
    SIZE_BASE = 13
    SIZE_LG   = 15
    SIZE_XL   = 18
    SIZE_XXL  = 24

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

def apply_theme(app: QApplication) -> None:
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
        width: 6px;
        height: 6px;
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
    }}
    QMenu {{
        background-color: {Colors.SURFACE};
        color: {Colors.TEXT};
        border: 1px solid {Colors.BORDER};
        border-radius: {Radius.SM}px;
        padding: {Spacing.XS}px 0px;
    }}
    QMenu::item {{
        padding: {Spacing.SM}px {Spacing.XL}px {Spacing.SM}px {Spacing.XL}px;
    }}
    QMenu::item:selected {{
        background-color: {Colors.SURFACE_HOVER};
        color: {Colors.ACCENT};
    }}
    QComboBox {{
        background-color: {Colors.SURFACE};
        border: 1px solid {Colors.BORDER};
        border-radius: {Radius.SM}px;
        padding: {Spacing.XS}px {Spacing.SM}px;
        color: {Colors.TEXT};
    }}
    QComboBox:focus {{
        border: 1px solid {Colors.ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 4px solid {Colors.TEXT_DIM};
        margin-right: 8px;
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
    QTabBar {{
        background-color: transparent;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {Colors.TEXT_DIM};
        padding: {Spacing.SM}px {Spacing.LG}px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {Colors.TEXT};
        border-bottom: 2px solid {Colors.ACCENT};
    }}
    QTabBar::tab:hover {{
        background-color: {Colors.SURFACE_HOVER};
    }}
    """
