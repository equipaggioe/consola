"""What moves or refreshes by itself, and whether the user stopped it.

WCAG 2.2.2 asks that what moves for more than five seconds, and what
refreshes by itself, can be paused, stopped or hidden. In Consola that
is the cursor of the console and the pulse of a green LED, which stop
with «Animaciones» in the Ver menu, and the available RAM of the status
bar, which hides with «RAM disponible». Both are preferences of the app,
not of the repo, in QSettings like «Solo favoritos»
(`services/favorites.py`), and start on.

Who moves listens to `notifier.changed` and stops or starts at once.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

_ANIMATIONS_KEY = "ui/animations"
_RAM_KEY = "ui/ram"


class _Notifier(QObject):
    """Tell who moves that a preference changed."""

    changed = Signal()


notifier = _Notifier()


def _read(key: str) -> bool:
    raw = QSettings().value(key, True)
    return raw in (True, "true", "True", 1, "1")


def animated() -> bool:
    """Return whether the cursor blinks and the green LED pulses."""
    return _read(_ANIMATIONS_KEY)


def set_animated(value: bool) -> None:
    """Save whether things move, and tell who moves."""
    QSettings().setValue(_ANIMATIONS_KEY, bool(value))
    notifier.changed.emit()


def ram_shown() -> bool:
    """Return whether the status bar shows the available RAM."""
    return _read(_RAM_KEY)


def set_ram_shown(value: bool) -> None:
    """Save whether the RAM shows, and tell the status bar."""
    QSettings().setValue(_RAM_KEY, bool(value))
    notifier.changed.emit()
