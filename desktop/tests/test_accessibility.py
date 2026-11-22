"""What a tool can measure of «Accesibilidad» of transversal.md.

Each repository gives, in its `tests/conftest.py`, the fixture `screen`:
the main window open with content and what only it knows (`Screen`).
The rest is the same in every Qt app, so it is copied unedited.

What a tool cannot see, such as what a screen reader says or whether an
order makes sense, is still checked by hand.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Protocol

import pytest
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAccessible,
    QAccessibleAnnouncementEvent,
    QAccessibleEvent,
    QColor,
    QImage,
    QPalette,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMenuBar,
    QToolButton,
    QWidget,
)

# Without a screen Qt only finds the fonts of `QT_QPA_FONTDIR`: in
# Windows each text would measure twice its width, and every size would
# be wrong.
if sys.platform == "win32" and QCoreApplication.instance() is None:
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ["WINDIR"]) / "Fonts"))

# 1920 × 1080 at 200 %, without the 40 px of the Windows taskbar.
SCREEN_200 = (960, 500)
# The smallest side of what one points at (WCAG 2.2 §2.5.8).
TARGET = 24
# The roles of what one presses, checks or writes in.
INTERACTIVE = {
    QAccessible.Role.Button,
    QAccessible.Role.CheckBox,
    QAccessible.Role.ComboBox,
    QAccessible.Role.EditableText,
    QAccessible.Role.PageTab,
    QAccessible.Role.RadioButton,
    QAccessible.Role.Grip,
}
# The cursors that say a widget answers the mouse.
POINTERS = {
    Qt.CursorShape.PointingHandCursor,
    Qt.CursorShape.SplitVCursor,
    Qt.CursorShape.SplitHCursor,
}


class Screen(Protocol):
    """What the repository's `screen` fixture gives.

    - `window`: the main window, shown, with the content one uses.
    - `bands`: its parts in reading order, top to bottom and left to
      right; Tab goes through them in that order.
    - `stop_motion`: stops what moves and what refreshes by itself.
    - `status_changes`: what changes a state while the focus is
      elsewhere, by name.
    """

    window: QWidget
    bands: Sequence[QWidget]
    status_changes: Sequence[tuple[str, Callable[[], None]]]

    def stop_motion(self) -> None:
        """Stop what moves and what refreshes by itself."""
        ...


def settle(rounds: int = 20) -> None:
    """Let the posted events and the deferred deletes run."""
    for _ in range(rounds):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def settled(screen: Screen) -> None:
    """Let the window lay itself out before it is measured."""
    settle()


def shown(window: QWidget) -> Iterator[QWidget]:
    """Yield the visible widgets of the window, not of other windows."""
    for widget in window.findChildren(QWidget):
        if widget.isVisible() and widget.window() is window and widget.width() > 0:
            yield widget


def name(widget: QWidget) -> str:
    """Return the class of a widget and its name or text, short."""
    text = widget.accessibleName()
    if not text and isinstance(widget, (QLabel, QAbstractButton, QLineEdit)):
        text = widget.text()
    return f"{type(widget).__name__} «{text[:28]}»"


def luminance(color: QColor) -> float:
    """Return the relative luminance of WCAG."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(c) for c in (color.redF(), color.greenF(), color.blueF()))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def ratio(first: QColor, second: QColor) -> float:
    """Return the contrast ratio of two colors."""
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def drawn(widget: QWidget) -> QImage:
    """Return the widget as the window draws it, with what is below.

    `QWidget.grab()` leaves transparent what the widget does not paint,
    and a glyph over its parent's band would measure against black.
    """
    window = widget.window()
    return window.grab(QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())).toImage()


def background(image: QImage) -> QColor | None:
    """Return the color that covers most of an image, if it has any."""
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return None
    count: Counter[int] = Counter()
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            count[image.pixel(x, y)] += 1
    return QColor(count.most_common(1)[0][0])


def interactive(window: QWidget) -> Iterator[QWidget]:
    """Yield what answers the mouse: by its role or by its cursor.

    A label with a hand cursor only focuses its field, which Tab
    reaches.
    """
    for widget in shown(window):
        interface = QAccessible.queryAccessibleInterface(widget)
        role = interface.role() if interface is not None else None
        pointer = (
            widget.testAttribute(Qt.WidgetAttribute.WA_SetCursor)
            and widget.cursor().shape() in POINTERS
            and not isinstance(widget, QLabel)
        )
        if widget.isEnabled() and (role in INTERACTIVE or pointer):
            yield widget


def clears(widget: QWidget) -> bool:
    """Return whether it is the clear button of a field.

    Its function has the keyboard: Ctrl+A and Delete empty the field.
    """
    field = widget.parentWidget()
    return (
        isinstance(widget, QToolButton)
        and isinstance(field, QLineEdit)
        and field.isClearButtonEnabled()
    )


def text_color(widget: QWidget) -> QColor | None:
    """Return the color of the text a control shows, if it shows one."""
    colors = widget.palette()
    if isinstance(widget, (QLabel, QCheckBox)) and widget.text().strip():
        return colors.color(QPalette.ColorRole.WindowText)
    if isinstance(widget, QAbstractButton) and widget.text().strip():
        return colors.color(QPalette.ColorRole.ButtonText)
    if isinstance(widget, QLineEdit):
        return colors.color(QPalette.ColorRole.Text)
    return None


def test_text_contrasts(screen: Screen) -> None:
    """1.4.3: the text of each enabled control over its background."""
    failures = []
    for widget in shown(screen.window):
        text = text_color(widget)
        if not widget.isEnabled() or text is None or text.alpha() == 0:
            continue
        under = background(drawn(widget))
        if under is not None and under.rgb() != text.rgb() and ratio(text, under) < 4.5:
            failures.append(f"{name(widget)} {ratio(text, under):.2f}")
    assert not failures


def both_sizes(window: QWidget) -> Iterator[QWidget]:
    """Yield the controls as they are, and again at 200 %.

    Some appear only in a narrow window, such as the «»» of a menu bar.
    """
    yield from interactive(window)
    window.showNormal()
    window.resize(*SCREEN_200)
    settle()
    yield from interactive(window)


def test_glyphs_contrast(screen: Screen) -> None:
    """1.4.11: a control drawn as a glyph or an icon shows at 3:1.

    The color that covers most of it is its background, and the one of
    its pixels that contrasts most with it, the glyph. A field's outline
    is `outline`, which `tokens.py --check` checks.
    """
    failures = []
    for widget in both_sizes(screen.window):
        text = widget.text() if isinstance(widget, QAbstractButton) else ""
        if isinstance(widget, QLineEdit) or len(text.strip()) > 2:
            continue
        image = drawn(widget)
        under = background(image)
        if under is None:
            continue
        pixels = (
            QColor(image.pixel(x, y)) for y in range(image.height()) for x in range(image.width())
        )
        best = max((ratio(pixel, under) for pixel in pixels), default=1.0)
        if best < 3:
            failures.append(f"{name(widget)} {best:.2f}")
    assert not failures


def test_targets_measure_24(screen: Screen) -> None:
    """2.5.8: what one points at measures 24 × 24 or more."""
    small = [
        f"{name(w)} {w.width()} × {w.height()}"
        for w in both_sizes(screen.window)
        if w.width() < TARGET or w.height() < TARGET
    ]
    assert not small


def test_keyboard_reaches_everything(screen: Screen) -> None:
    """2.1.1: what answers the mouse takes the focus of Tab.

    A menu bar, if there is one, opens with Alt.
    """
    failures = [
        f"{name(w)} no recibe el foco"
        for w in interactive(screen.window)
        if not (w.focusPolicy() & Qt.FocusPolicy.TabFocus) and not clears(w)
    ]
    bars = [bar for bar in screen.window.findChildren(QMenuBar) if bar.isVisible()]
    if bars:
        QTest.keyClick(QApplication.focusWidget() or screen.window, Qt.Key.Key_Alt)
        settle(4)
        if all(bar.activeAction() is None for bar in bars):
            failures.append("Alt no lleva a la barra de menú")
        QTest.keyClick(QApplication.focusWidget() or screen.window, Qt.Key.Key_Escape)
    assert not failures


def tabbable(widget: QWidget, window: QWidget) -> bool:
    """Return whether Tab can stop at the widget."""
    return (
        widget.isVisible()
        and widget.isEnabled()
        and widget.window() is window
        and bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus)
    )


def following(widget: QWidget, window: QWidget) -> QWidget:
    """Return the next widget of the focus chain where Tab can stop."""
    candidate = widget.nextInFocusChain()
    while candidate is not None and not tabbable(candidate, window):
        candidate = candidate.nextInFocusChain()
    assert candidate is not None
    return candidate


def walk(window: QWidget) -> tuple[list[QWidget], list[str], list[str]]:
    """Go around the window with Tab from its first control.

    Return what Tab reached in order, what looks the same with the
    focus and where Tab did not move.
    """
    focused = QApplication.focusWidget()
    if focused is not None:
        focused.clearFocus()
    settle(4)
    looks = {id(w): w.grab().toImage() for w in shown(window)}
    start = next(w for w in window.findChildren(QWidget) if tabbable(w, window))
    start.setFocus(Qt.FocusReason.TabFocusReason)
    settle(4)
    order: list[QWidget] = [start]
    unseen = [name(start)] if start.grab().toImage() == looks.get(id(start)) else []
    stuck: list[str] = []
    for _ in range(500):
        current = QApplication.focusWidget()
        assert current is not None
        QTest.keyClick(current, Qt.Key.Key_Tab)
        settle(2)
        reached = QApplication.focusWidget()
        if reached is current:
            stuck.append(name(current))
            reached = following(current, window)
            reached.setFocus(Qt.FocusReason.TabFocusReason)
            settle(2)
        assert reached is not None
        if reached in order:
            break
        order.append(reached)
        before = looks.get(id(reached))
        if before is not None and reached.grab().toImage() == before:
            unseen.append(name(reached))
    return order, unseen, stuck


def test_tab_leaves_every_control(screen: Screen) -> None:
    """2.1.2: Tab gets out of every control it gets into."""
    assert not walk(screen.window)[2]


def test_focus_shows(screen: Screen) -> None:
    """2.4.7: each control looks different with the focus of Tab."""
    assert not walk(screen.window)[1]


def band(screen: Screen, widget: QWidget) -> int | None:
    """Return in which band of the screen a widget is, if in one."""
    for index, part in enumerate(screen.bands):
        if part is widget or part.isAncestorOf(widget):
            return index
    return None


def test_tab_follows_reading(screen: Screen) -> None:
    """2.4.3: Tab goes band by band, and in each one as one reads.

    In a band, the next one is on a lower line, or on the same line
    further right, or inside the one before. The tour starts where Tab
    comes back from the last band to the first; what is in no band,
    such as a splitter between two, does not count.
    """
    window = screen.window
    order = [(w, b) for w in walk(window)[0] if (b := band(screen, w)) is not None]
    turn = next((i for i in range(1, len(order)) if order[i][1] < order[i - 1][1]), 0)
    order = order[turn:] + order[:turn]
    failures = []
    for (before, here), (after, there) in zip(order, order[1:], strict=False):
        if there < here:
            failures.append(f"{name(before)} → {name(after)}: vuelve a una banda de arriba")
        if there != here or before.isAncestorOf(after):
            continue
        first, second = before.mapTo(window, QPoint(0, 0)), after.mapTo(window, QPoint(0, 0))
        same_line = second.y() < first.y() + before.height() and first.y() < (
            second.y() + after.height()
        )
        backwards = second.x() < first.x() if same_line else second.y() < first.y()
        if backwards:
            failures.append(f"{name(before)} → {name(after)}: va hacia atrás")
    assert not failures


def test_motion_stops(screen: Screen) -> None:
    """2.2.2: nothing moves nor refreshes by itself once stopped."""
    screen.stop_motion()
    settle()
    window = screen.window
    moving = [
        f"QTimer de {type(t.parent()).__name__} cada {t.interval()} ms"
        for t in window.findChildren(QTimer)
        if t.isActive() and not t.isSingleShot()
    ] + [
        f"animación sin fin de {type(a.parent()).__name__}"
        for a in window.findChildren(QAbstractAnimation)
        if a.state() == QAbstractAnimation.State.Running and a.loopCount() == -1
    ]
    assert not moving


def test_status_messages_announced(screen: Screen, monkeypatch: pytest.MonkeyPatch) -> None:
    """4.1.3: each change of state reaches assistive technology."""
    heard: list[str] = []
    send = QAccessible.updateAccessibility

    def record(event: QAccessibleEvent) -> None:
        if isinstance(event, QAccessibleAnnouncementEvent):
            heard.append(event.message())
        send(event)

    monkeypatch.setattr(QAccessible, "updateAccessibility", staticmethod(record))
    silent = []
    for what, change in screen.status_changes:
        before = len(heard)
        change()
        settle()
        if len(heard) == before:
            silent.append(what)
    assert not silent


def scrolled(widget: QWidget) -> bool:
    """Return whether the widget is inside a scroll area."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def shortened(label: QLabel) -> bool:
    """Return whether a label shortened its text and keeps it whole.

    With «…» at the end and the whole text in its tooltip: what does
    not show is still there.
    """
    text = label.text()
    return text.endswith("…") and label.toolTip().startswith(text[:-1])


def cut(widget: QWidget) -> bool:
    """Return whether the text of a control does not fit in it."""
    if isinstance(widget, QAbstractButton):
        # What the text draws, without the padding of the style.
        hint = widget.fontMetrics().tightBoundingRect(widget.text()).size()
    else:
        hint = widget.sizeHint()
    return hint.width() > widget.width() + 1 or hint.height() > widget.height() + 1


def test_text_at_200(screen: Screen) -> None:
    """1.4.4: at 200 %, the window fits a 1920 × 1080 screen.

    At 200 % that screen has 960 × 540 pixels of Qt, which measure the
    same as at 100 %: so it is enough to size the window to that and
    look at what it cuts. What is inside a scroll area is reached by
    scrolling.
    """
    window = screen.window
    width, height = SCREEN_200
    window.showNormal()
    window.resize(width, height)
    settle()
    failures = []
    if window.width() > width or window.height() > height:
        failures.append(f"la ventana no baja de {window.width()} × {window.height()}")
    for widget in shown(window):
        if isinstance(widget, QLabel):
            if widget.wordWrap() or not widget.text().strip() or shortened(widget):
                continue
        elif isinstance(widget, QAbstractButton):
            if not widget.text().strip() or isinstance(widget, QToolButton):
                continue
        elif not isinstance(widget, QLineEdit):
            continue
        corner = widget.mapTo(window, widget.rect().bottomRight())
        if not window.rect().contains(corner) and not scrolled(widget):
            failures.append(f"{name(widget)} queda fuera de la ventana")
        elif not isinstance(widget, QLineEdit) and cut(widget):
            failures.append(f"{name(widget)} cortado")
    assert not failures
