"""Measure in the window what can be measured of WCAG 2.2 AA.

From `desktop/`, after compiling the translations and the resources
(`docs/arquitectura/03_ejecucion_y_despliegue.md`, §1):
`uv run python scripts/aa.py`. It opens the window without a screen,
with a repo in a temporary folder and four action tabs, and writes what
fails of each criterion it measures. Nothing of the user is read or
written: the settings, the caches and the repo go in that folder.

It measures 1.4.3, 1.4.4, 2.1.1, 2.1.2, 2.2.2, 2.4.3, 2.4.7, 2.5.8 and
4.1.3. What it cannot see, such as what a screen reader says, is
checked by hand. With `--shot <file.png>` it also saves the window as
it is at 200 %.

Without a screen Qt only finds the fonts of `QT_QPA_FONTDIR`: in
Windows it points it at the system's, or each text measures twice its
width and every size is wrong.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QCoreApplication,
    QEvent,
    QPoint,
    QRect,
    QSettings,
    Qt,
    QTimer,
)
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
    QSplitterHandle,
    QToolButton,
    QWidget,
)

# 1920 × 1080 at 200 %, without the 40 px of the Windows taskbar.
SCREEN_200 = (960, 500)
# What a screen reader receives: the announcements, recorded.
ANNOUNCED: list[str] = []


def main() -> None:
    """Open the window, measure it and write the result."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shot", type=Path, help="where to save the window at 200 %%")
    args = parser.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="consola-aa-"))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if sys.platform == "win32":
        os.environ["QT_QPA_FONTDIR"] = str(Path(os.environ["WINDIR"]) / "Fonts")
    for variable in ("APPDATA", "LOCALAPPDATA", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        os.environ[variable] = str(scratch / variable.lower())
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("Consola")
    qapp.setOrganizationName("Equipaggio")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
        QSettings.setPath(QSettings.Format.IniFormat, scope, str(scratch / "settings"))
    _record_announcements()

    import app.rc_resources  # noqa: F401
    from app import theme
    from app.api import http
    from app.services import language
    from app.services.catalog import load_catalog
    from app.services.tasks import bind_all
    from app.windows.main_window import MainWindow

    language.install(qapp)
    http.start()
    load_catalog()
    bind_all()
    theme.apply(qapp)

    window = MainWindow()
    window.resize(1400, 860)
    window.show()
    repo = scratch / "repo"
    repo.mkdir()
    window.project_tabs.open_path(str(repo))
    _open_tabs(window)
    window.activateWindow()
    _settle()

    report: list[tuple[str, list[str]]] = [
        ("1.4.3, texto por debajo de 4.5:1", contrast(window)),
        ("2.5.8, objetivos menores de 24 × 24", targets(window)),
        ("2.1.1, funciones sin teclado", keyboard(window)),
    ]
    order, unseen, stuck = walk(window)
    report += [
        ("2.4.7, foco sin cambio visible", unseen),
        ("2.1.2, Tab no sale", stuck),
        ("2.4.3, orden del foco fuera del orden de lectura", reading_order(window, order)),
        ("2.2.2, lo que se mueve o se actualiza solo", motion(window)),
        ("2.2.2, lo mismo después de detenerlo desde Ver", motion(window, stop=True)),
        ("4.1.3, mensajes de estado que no se anuncian", announcements(window)),
        ("1.4.4, texto al 200 % en 1920 × 1080", text_200(window, args.shot)),
        ("2.5.8, lo mismo a 200 %", targets(window)),
        ("1.4.11, glifos e iconos por debajo de 3:1 a 200 %", glyphs(window)),
    ]
    out = sys.stdout
    out.reconfigure(encoding="utf-8")  # pyrefly: ignore[missing-attribute]
    out.write(f"Controles que Tab recorre: {len(order)}\n")
    for title, failures in report:
        out.write(f"\n== {title}: {len(failures)}\n")
        for failure in failures:
            out.write(f"   {failure}\n")
    window.close()


def _record_announcements() -> None:
    """Keep each announcement the app sends to assistive technology."""
    send = QAccessible.updateAccessibility

    def record(event: QAccessibleEvent) -> None:
        if isinstance(event, QAccessibleAnnouncementEvent):
            ANNOUNCED.append(event.message())
        send(event)

    QAccessible.updateAccessibility = staticmethod(record)


def _settle(rounds: int = 20) -> None:
    """Let the posted events and the deferred deletes run."""
    for _ in range(rounds):
        QApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _open_tabs(window: QWidget) -> None:
    """Open four action tabs that are not destructive."""
    from app.services.catalog import applicable_ids
    from app.services.registry import registry

    workspace = window.current_workspace
    opened = 0
    for capability_id in sorted(applicable_ids(workspace.project.path)):
        capability = registry.get_capability(capability_id)
        if capability is None or capability.kind == "destructive":
            continue
        workspace.open_tab(capability)
        opened += 1
        if opened == 4:
            return


def _shown(window: QWidget) -> Iterator[QWidget]:
    """Yield the visible widgets of the window, not of other windows."""
    for widget in window.findChildren(QWidget):
        if widget.isVisible() and widget.window() is window and widget.width() > 0:
            yield widget


def _name(widget: QWidget) -> str:
    """Return the class of a widget and its name or text, short."""
    text = widget.accessibleName()
    if not text and isinstance(widget, (QLabel, QAbstractButton, QLineEdit)):
        text = widget.text()
    return f"{type(widget).__name__} «{text[:28]}»"


def _luminance(color: QColor) -> float:
    """Return the relative luminance of WCAG."""

    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(c) for c in (color.redF(), color.greenF(), color.blueF()))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _ratio(first: QColor, second: QColor) -> float:
    """Return the contrast ratio of two colors."""
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _drawn(widget: QWidget) -> QImage:
    """Return the widget as the window draws it, with what is below.

    `QWidget.grab()` leaves transparent what the widget does not paint,
    and a glyph over its parent's band would measure against black.
    """
    window = widget.window()
    corner = widget.mapTo(window, QPoint(0, 0))
    return window.grab(QRect(corner, widget.size())).toImage()


def _background(widget: QWidget) -> QColor | None:
    """Return the color that covers most of the widget once drawn."""
    image = _drawn(widget)
    if image.isNull() or image.width() == 0:
        return None
    count: Counter[int] = Counter()
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            count[image.pixel(x, y)] += 1
    return QColor(count.most_common(1)[0][0])


def contrast(window: QWidget) -> list[str]:
    """1.4.3: the text of each enabled control over its background."""
    failures = []
    for widget in _shown(window):
        if not widget.isEnabled():
            continue
        colors = widget.palette()
        text = None
        if isinstance(widget, QLabel) and widget.text().strip():
            text = colors.color(QPalette.ColorRole.WindowText)
        elif isinstance(widget, QCheckBox) and widget.text().strip():
            text = colors.color(QPalette.ColorRole.WindowText)
        elif isinstance(widget, QAbstractButton) and widget.text().strip():
            text = colors.color(QPalette.ColorRole.ButtonText)
        elif isinstance(widget, QLineEdit):
            text = colors.color(QPalette.ColorRole.Text)
        if text is None or text.alpha() == 0:
            continue
        background = _background(widget)
        if background is None or background.rgb() == text.rgb():
            continue
        ratio = _ratio(text, background)
        if ratio < 4.5:
            failures.append(
                f"{_name(widget)} {ratio:.2f} ({text.name()} sobre {background.name()})"
            )
    return failures


# The roles of what one presses, checks or writes in.
_INTERACTIVE = {
    QAccessible.Role.Button,
    QAccessible.Role.CheckBox,
    QAccessible.Role.ComboBox,
    QAccessible.Role.EditableText,
    QAccessible.Role.PageTab,
    QAccessible.Role.RadioButton,
    QAccessible.Role.Grip,
}
# The cursors that say a widget answers the mouse.
_POINTER = {
    Qt.CursorShape.PointingHandCursor,
    Qt.CursorShape.SplitVCursor,
    Qt.CursorShape.SplitHCursor,
}


def _interactive(window: QWidget) -> Iterator[QWidget]:
    """Yield what answers the mouse: by its role or by its cursor.

    A label with a hand cursor only focuses its field, which Tab
    reaches. The window's edges do not count: Qt cannot move nor resize
    a window with the keyboard, and they are written apart.
    """
    for widget in _shown(window):
        interface = QAccessible.queryAccessibleInterface(widget)
        role = interface.role() if interface is not None else None
        pointer = (
            widget.testAttribute(Qt.WidgetAttribute.WA_SetCursor)
            and widget.cursor().shape() in _POINTER
            and not isinstance(widget, QLabel)
        )
        if role in _INTERACTIVE or pointer:
            yield widget


def targets(window: QWidget) -> list[str]:
    """2.5.8: what one points at measures 24 × 24 or more."""
    return [
        f"{_name(w)} {w.width()} × {w.height()}"
        for w in _interactive(window)
        if (w.width() < 24 or w.height() < 24) and w.isEnabled()
    ]


def _clears(widget: QWidget) -> bool:
    """Return whether it is the clear button of a field.

    Its function has the keyboard: Ctrl+A and Supr empty the field.
    """
    field = widget.parentWidget()
    return (
        isinstance(widget, QToolButton)
        and isinstance(field, QLineEdit)
        and (field.isClearButtonEnabled())
    )


def keyboard(window: QWidget) -> list[str]:
    """2.1.1: what answers the mouse also takes the focus of Tab.

    Besides, the menu bar has to open with the keyboard: «Ver» is the
    only place where a hidden section comes back. And the brand of the
    title bar opens the menu of the window, whose «Mover» moves it with
    the arrows and puts it back with Escape.
    """
    failures = [
        f"{_name(w)} no recibe el foco"
        for w in _interactive(window)
        if w.isEnabled() and not (w.focusPolicy() & Qt.FocusPolicy.TabFocus) and not _clears(w)
    ]
    focus = QApplication.focusWidget() or window
    QTest.keyClick(focus, Qt.Key.Key_Alt)
    _settle(4)
    if window.action_menu.activeAction() is None:
        failures.append("Alt no lleva a la barra de menú")
    QTest.keyClick(QApplication.focusWidget() or window, Qt.Key.Key_Escape)
    _settle(4)
    failures += _window_keys(window)
    return failures


def _window_keys(window: QWidget) -> list[str]:
    """Move the window with the brand, «Mover», → and Escape."""
    window.showNormal()
    _settle(4)
    brand = window.title_bar.brand
    brand.setFocus(Qt.FocusReason.TabFocusReason)
    QTest.keyClick(brand, Qt.Key.Key_Space)
    _settle(4)
    menu = QApplication.activePopupWidget()
    if menu is not window.window_menu:
        return ["la marca no abre el menú de la ventana"]
    menu.hide()
    start = window.pos()
    move = next(a for a in menu.actions() if a.text() == "Mover")
    move.trigger()
    QTest.keyClick(QApplication.focusWidget() or window, Qt.Key.Key_Right)
    _settle(4)
    failures = []
    if window.pos().x() <= start.x():
        failures.append("«Mover» no mueve la ventana con las flechas")
    QTest.keyClick(QApplication.focusWidget() or window, Qt.Key.Key_Escape)
    _settle(4)
    if window.pos() != start:
        failures.append("Escape no devuelve la ventana a su lugar")
    return failures


def _tabbable(widget: QWidget, window: QWidget) -> bool:
    return (
        widget.isVisible()
        and widget.isEnabled()
        and widget.window() is window
        and bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus)
    )


def walk(window: QWidget) -> tuple[list[QWidget], list[str], list[str]]:
    """2.4.7 and 2.1.2: go around the window with Tab.

    Return what Tab reached in order, what looks the same with the
    focus and where Tab did not move.
    """
    window.action_search.box.setFocus()
    _settle(4)
    start = QApplication.focusWidget()
    looks = {id(w): w.grab().toImage() for w in window.findChildren(QWidget) if w.isVisible()}
    order: list[QWidget] = [start]
    unseen: list[str] = []
    stuck: list[str] = []
    for _ in range(300):
        current = QApplication.focusWidget()
        QTest.keyClick(current, Qt.Key.Key_Tab)
        _settle(2)
        reached = QApplication.focusWidget()
        if reached is current:
            stuck.append(_name(current))
            reached = current.nextInFocusChain()
            while not _tabbable(reached, window):
                reached = reached.nextInFocusChain()
            reached.setFocus(Qt.FocusReason.TabFocusReason)
            _settle(2)
        if reached is start or reached in order:
            break
        order.append(reached)
        before = looks.get(id(reached))
        if before is not None and reached.grab().toImage() == before:
            unseen.append(_name(reached))
    return order, unseen, stuck


def _region(window: QWidget, widget: QWidget) -> int:
    """Return in which band of the window a widget is, top to bottom.

    Left to right in the workspace: the tabs, the console, the right
    column and its footer.
    """
    workspace = window.current_workspace
    bands = [
        window.title_bar,
        window.menu_row,
        workspace.sub_bar,
        workspace.content_area,
        workspace.right_column,
        workspace.run_footer,
        window.status_bar,
    ]
    if isinstance(widget, QSplitterHandle) and widget.splitter() is workspace.splitter:
        # The border between the console and the right column.
        return bands.index(workspace.content_area)
    for index, band in enumerate(bands):
        if band is widget or band.isAncestorOf(widget):
            return index
    return len(bands)


def reading_order(window: QWidget, order: list[QWidget]) -> list[str]:
    """2.4.3: Tab goes band by band, and in each one as one reads.

    In a band, the next one is on a lower line, or on the same line
    further right, or inside the one before. The tour starts where Tab
    comes back from the last band to the first.
    """
    bands = [_region(window, w) for w in order]
    turn = next((i for i in range(1, len(order)) if bands[i] < bands[i - 1]), 0)
    order = order[turn:] + order[:turn]
    failures = []
    for before, after in zip(order, order[1:], strict=False):
        band, next_band = _region(window, before), _region(window, after)
        if before.isAncestorOf(after):
            continue
        if next_band < band:
            failures.append(f"{_name(before)} → {_name(after)}: vuelve a una banda de arriba")
            continue
        if next_band > band:
            continue
        top_left = before.mapTo(window, before.rect().topLeft())
        corner = after.mapTo(window, after.rect().topLeft())
        same_line = corner.y() < top_left.y() + before.height() and top_left.y() < (
            corner.y() + after.height()
        )
        if (same_line and corner.x() < top_left.x()) or (
            not same_line and corner.y() < top_left.y()
        ):
            failures.append(f"{_name(before)} → {_name(after)}: va hacia atrás")
    return failures


def motion(window: QWidget, *, stop: bool = False) -> list[str]:
    """2.2.2: what moves or refreshes by itself, with a green LED on.

    With `stop`, after unchecking «Animaciones» and «RAM» in Ver.
    """
    from app.services import session

    workspace = window.current_workspace
    for view in workspace._views.values():
        if not (view.capability.has_web_view or view.capability.has_db_view):
            view.set_endpoint("http://127.0.0.1:1", "Sonda", False, session.READY)
            break
    if stop:
        for action in (window.action_menu.animations_action, window.action_menu.ram_action):
            if action.isChecked():
                action.trigger()
    _settle()
    found = []
    for timer in window.findChildren(QTimer):
        if timer.isActive() and not timer.isSingleShot():
            found.append(f"QTimer de {type(timer.parent()).__name__} cada {timer.interval()} ms")
    for animation in window.findChildren(QAbstractAnimation):
        running = animation.state() == QAbstractAnimation.State.Running
        if running and animation.loopCount() == -1:
            found.append(f"animación sin fin de {type(animation.parent()).__name__}")
    return found


def _probe(fails: bool) -> Callable[..., None]:
    """Return a task that ends at once, well or with an error."""
    from app.services.context import TaskError

    def task(ctx: object) -> None:
        if fails:
            raise TaskError("sonda")

    return task


def announcements(window: QWidget) -> list[str]:
    """4.1.3: each change of state reaches a screen reader.

    A task that ends well and one that fails, an endpoint that comes
    up and goes down, and what Save does in «Configuración del repo».
    """
    from app.services import session
    from app.services.registry import Capability

    workspace = window.current_workspace
    tab = workspace.tabs[0]
    view = workspace._views[tab]
    console = workspace._consoles[tab]
    cases: list[tuple[str, Callable[[], None]]] = [
        ("el notice de Guardar", lambda: workspace._on_env_notice("Guardado", "ok")),
        (
            "un endpoint que arranca",
            lambda: view.set_endpoint("http://127.0.0.1:1", "Sonda", False, session.STARTING),
        ),
        ("un endpoint que se cae", view.endpoint_down),
    ]
    for fails in (False, True):
        capability = Capability(
            id="aa_probe", name="Sonda", group="", kind="once", func=_probe(fails)
        )

        def run(c: Capability = capability) -> None:
            workspace._run_real(tab, console, c, {})
            deadline = time.monotonic() + 10
            while workspace._busy.get(tab) is not None and time.monotonic() < deadline:
                _settle(2)

        cases.append(("una tarea que falla" if fails else "una tarea que termina bien", run))
    failures = []
    for what, act in cases:
        before = len(ANNOUNCED)
        act()
        _settle()
        if len(ANNOUNCED) == before:
            failures.append(what)
    return failures


def glyphs(window: QWidget) -> list[str]:
    """1.4.11: a control drawn as a glyph or an icon shows at 3:1.

    It takes the color that covers most of the control as its
    background, and the one of its pixels that contrasts most with it as
    the glyph.
    """
    failures = []
    for widget in _interactive(window):
        if isinstance(widget, QLineEdit):
            # Its outline is `outline`: `tokens.py --check` checks it.
            continue
        text = widget.text() if isinstance(widget, QAbstractButton) else ""
        if len(text.strip()) > 2 or not widget.isEnabled():
            continue
        image = _drawn(widget)
        background = _background(widget)
        if background is None:
            continue
        best = max(
            (
                _ratio(QColor(image.pixel(x, y)), background)
                for y in range(image.height())
                for x in range(image.width())
            ),
            default=1.0,
        )
        if best < 3:
            failures.append(f"{_name(widget)} {best:.2f}")
    return failures


def _scrolled(widget: QWidget) -> bool:
    """Return whether the widget is inside a scroll area."""
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def _shortened(label: QLabel) -> bool:
    """Return whether a label shortened its text and keeps it whole.

    With «…» at the end and the whole text in its tooltip, as an action
    tab does: what does not show is still there.
    """
    text = label.text()
    return text.endswith("…") and label.toolTip().startswith(text[:-1])


def text_200(window: QWidget, shot: Path | None) -> list[str]:
    """1.4.4: at 200 %, the window fits and loses nothing.

    At 200 % a 1920 × 1080 screen has 960 × 540 pixels of Qt, which
    measure the same as at 100 %: so it is enough to size the window
    to that and look at what it cuts. What is inside a scroll area is
    not lost: it is reached by scrolling.
    """
    width, height = SCREEN_200
    window.showNormal()
    window.resize(width, height)
    _settle()
    if shot is not None:
        window.grab().save(str(shot))
    failures = []
    if window.width() > width or window.height() > height:
        failures.append(f"la ventana no baja de {window.width()} × {window.height()}")
    frame = window.rect()
    for widget in _shown(window):
        if isinstance(widget, QLabel):
            if widget.wordWrap() or not widget.text().strip() or _shortened(widget):
                continue
        elif isinstance(widget, QAbstractButton):
            if not widget.text().strip() or isinstance(widget, QToolButton):
                continue
        elif not isinstance(widget, QLineEdit):
            continue
        corner = widget.mapTo(window, widget.rect().bottomRight())
        if not frame.contains(corner) and not _scrolled(widget):
            failures.append(f"{_name(widget)} queda fuera de la ventana")
            continue
        if isinstance(widget, QLineEdit):
            continue
        if isinstance(widget, QAbstractButton):
            # What the text draws, without the padding of the style.
            hint = widget.fontMetrics().tightBoundingRect(widget.text()).size()
        else:
            hint = widget.sizeHint()
        if hint.width() > widget.width() + 1 or hint.height() > widget.height() + 1:
            failures.append(
                f"{_name(widget)} cortado: pide {hint.width()} × {hint.height()}, "
                f"tiene {widget.width()} × {widget.height()}"
            )
    return failures


if __name__ == "__main__":
    main()
