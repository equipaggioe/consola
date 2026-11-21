"""What WCAG asks of the keyboard, of motion and of status messages.

The whole window is measured by `scripts/aa.py`; here, each piece.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import override

import pytest
from PySide6.QtCore import QAbstractAnimation, QRect, QSettings, Qt
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent, QAccessibleEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from pytestqt.qtbot import QtBot

from app.services import motion
from app.services.announce import announce
from app.theme import Metrics
from app.widgets.accordion_section import AccordionSection
from app.widgets.console_view import ConsoleView
from app.widgets.led_indicator import LedIndicator
from app.widgets.reorderable_bar import ReorderableBar
from app.widgets.reorderable_tab import ReorderableTab
from app.widgets.window_menu import WindowMenu
from app.windows.main_window import _lines


@pytest.fixture(autouse=True)
def settings(tmp_path: Path) -> Iterator[None]:
    """Keep the preferences in a temporary INI, not the user's."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    yield
    motion.set_animated(True)


def test_animations_off_stops_the_led_and_the_cursor(qtbot: QtBot) -> None:
    """Unchecking «Animaciones» stops both; checking it starts them."""
    led = LedIndicator()
    console = ConsoleView()
    qtbot.addWidget(led)
    qtbot.addWidget(console)
    led.set_state("green")
    assert led.animation.state() == QAbstractAnimation.State.Running
    assert console.cursor_timer.isActive()

    motion.set_animated(False)
    assert led.animation.state() == QAbstractAnimation.State.Stopped
    assert not console.cursor_timer.isActive()
    assert "▍" not in console.toPlainText()

    motion.set_animated(True)
    assert led.animation.state() == QAbstractAnimation.State.Running
    assert console.cursor_timer.isActive()


def test_a_led_born_with_animations_off_does_not_pulse(qtbot: QtBot) -> None:
    """The preference holds for a LED built after it was saved."""
    motion.set_animated(False)
    led = LedIndicator()
    qtbot.addWidget(led)
    led.set_state("green")
    assert led.animation.state() == QAbstractAnimation.State.Stopped


def _placed(parent: QWidget, name: str, x: int, y: int, w: int, h: int) -> QWidget:
    widget = QLabel(name, parent)
    widget.setGeometry(QRect(x, y, w, h))
    return widget


def test_siblings_read_by_lines_then_rightward(qtbot: QtBot) -> None:
    """A short button centered beside a tall field reads in its line."""
    parent = QWidget()
    qtbot.addWidget(parent)
    tall = _placed(parent, "tall", 0, 0, 100, 40)
    right = _placed(parent, "right", 200, 0, 50, 40)
    short = _placed(parent, "short", 120, 10, 30, 20)
    below = _placed(parent, "below", 0, 50, 300, 30)
    assert _lines([below, right, short, tall]) == [tall, short, right, below]


def test_a_column_reads_top_down(qtbot: QtBot) -> None:
    """Stacked siblings go one below the other."""
    parent = QWidget()
    qtbot.addWidget(parent)
    first = _placed(parent, "a", 0, 0, 100, 30)
    second = _placed(parent, "b", 0, 30, 100, 30)
    third = _placed(parent, "c", 0, 60, 100, 30)
    assert _lines([third, first, second]) == [first, second, third]


def test_space_and_enter_fold_a_section(qtbot: QtBot) -> None:
    """The header takes Tab and folds with the keyboard, as a click."""
    section = AccordionSection("Parámetros", QWidget(), expanded=True)
    qtbot.addWidget(section)
    header = section.header
    assert header.focusPolicy() & Qt.FocusPolicy.TabFocus
    QTest.keyClick(header, Qt.Key.Key_Space)
    assert not section.is_expanded()
    QTest.keyClick(header, Qt.Key.Key_Return)
    assert section.is_expanded()
    interface = QAccessible.queryAccessibleInterface(header)
    assert interface is not None
    assert interface.role() == QAccessible.Role.Button
    assert interface.text(QAccessible.Text.Name) == "Parámetros"
    assert interface.state().expanded


class _Bar(ReorderableBar):
    def __init__(self) -> None:
        super().__init__()
        self.row = QHBoxLayout(self)
        self.tabs = []

    @override
    def _tab_layout(self) -> QHBoxLayout:
        return self.row


class _Tab(ReorderableTab):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.setAccessibleName(name)
        self._init_reorder()


def test_a_tab_moves_and_selects_with_the_keyboard(qtbot: QtBot) -> None:
    """Ctrl+Shift+PgDown moves it one place, and Space selects it."""
    bar = _Bar()
    qtbot.addWidget(bar)
    first, second = _Tab("a"), _Tab("b")
    for tab in (first, second):
        bar.tabs.append(tab)
        bar.row.addWidget(tab)
    with qtbot.waitActive(bar):
        bar.show()
        bar.activateWindow()
    first.setFocus(Qt.FocusReason.TabFocusReason)
    assert first.hasFocus()
    QTest.keyClick(
        first,
        Qt.Key.Key_PageDown,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert bar.tabs == [second, first]
    with qtbot.waitSignal(first.clicked, timeout=1000):
        QTest.keyClick(first, Qt.Key.Key_Space)


def test_an_error_interrupts_the_screen_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """An urgent message is assertive, the others wait."""
    sent: list[QAccessibleAnnouncementEvent] = []

    def record(event: QAccessibleEvent) -> None:
        assert isinstance(event, QAccessibleAnnouncementEvent)
        sent.append(event)

    monkeypatch.setattr(QAccessible, "updateAccessibility", staticmethod(record))
    source = QWidget()
    announce(source, "Hecho")
    announce(source, "Falló", urgent=True)
    assert [e.message() for e in sent] == ["Hecho", "Falló"]
    assert sent[0].politeness() == QAccessible.AnnouncementPoliteness.Polite
    assert sent[1].politeness() == QAccessible.AnnouncementPoliteness.Assertive


def test_the_window_menu_moves_with_the_arrows(qtbot: QtBot) -> None:
    """«Mover» moves the window with the arrows; Escape puts it back."""
    window = QWidget()
    qtbot.addWidget(window)
    window.setGeometry(100, 100, 400, 300)
    window.show()
    menu = WindowMenu(window)
    start = window.pos()
    next(a for a in menu.actions() if a.text() == "Mover").trigger()
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert window.pos().x() == start.x() + Metrics.KEY_STEP
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.pos() == start


def test_the_window_menu_sizes_with_the_arrows(qtbot: QtBot) -> None:
    """«Tamaño» grows the window with the arrows; Enter leaves it."""
    window = QWidget()
    qtbot.addWidget(window)
    window.setGeometry(100, 100, 400, 300)
    window.show()
    menu = WindowMenu(window)
    next(a for a in menu.actions() if a.text() == "Tamaño").trigger()
    QTest.keyClick(window, Qt.Key.Key_Down)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert window.height() == 300 + Metrics.KEY_STEP
    QTest.keyClick(window, Qt.Key.Key_Down)
    assert window.height() == 300 + Metrics.KEY_STEP
