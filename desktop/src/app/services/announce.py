"""Status messages for assistive technology, without moving the focus.

WCAG 4.1.3: a screen reader reads a changed name or description only
of the widget with the focus. What ends, fails or changes state while
the focus is elsewhere is announced: the end of a task, the state of
an endpoint and what Save or import did in «Configuración del repo».
"""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent


def announce(source: QObject, message: str, *, urgent: bool = False) -> None:
    """Have assistive technology read `message`.

    `urgent` interrupts what it is reading, for an error; otherwise it
    waits for it to finish.
    """
    event = QAccessibleAnnouncementEvent(source, message)
    if urgent:
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive)
    QAccessible.updateAccessibility(event)
