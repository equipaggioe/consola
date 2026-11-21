"""The theme rules of qt.md and the design tokens in canone."""

import re
from pathlib import Path

from PySide6.QtWidgets import QApplication, QProxyStyle

from app import theme

SRC = Path(__file__).parents[1] / "src"
PACKAGE = SRC / "app"
COLORS = PACKAGE / "colors.py"
# pyside6-rcc writes it from resources.qrc, and git ignores it: its
# bytes are images and translations, and can match a pattern by chance.
RESOURCES = PACKAGE / "rc_resources.py"
# A CSS rgb(), and not QColor.rgb().
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|(?<!\.)\brgba?\(|\bQColor\(")


def lines_outside(pattern: re.Pattern[str], allowed: set[Path]) -> list[str]:
    """List the lines outside some files that match a pattern."""
    return [
        f"{path.relative_to(SRC)}:{number}"
        for path in sorted(PACKAGE.rglob("*.py"))
        if path not in allowed | {RESOURCES}
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if pattern.search(line)
    ]


def test_colors_only_generated() -> None:
    """No color literal lives outside the generated schemes."""
    assert not lines_outside(COLOR, {COLORS})


def test_no_style_sheet() -> None:
    """The app has no style sheet: its look is the style of theme.py."""
    assert not lines_outside(re.compile(r"\.setStyleSheet\("), set())


def test_style_is_fusion() -> None:
    """theme.py sets a proxy style over Fusion."""
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    theme.apply(app)
    style = app.style()
    assert isinstance(style, QProxyStyle)
    assert style.baseStyle().name() == "fusion"
