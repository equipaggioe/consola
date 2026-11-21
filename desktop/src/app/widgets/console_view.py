"""The log view of a task tab."""

from __future__ import annotations

import re
from typing import override

from PySide6.QtCore import QCoreApplication, QDateTime, QLocale, Qt, QTimer, Slot
from PySide6.QtGui import (
    QAction,
    QBrush,
    QContextMenuEvent,
    QFont,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QLineEdit, QMenu, QPlainTextEdit, QWidget

from app import theme
from app.services.palettes import NEUTRAL, Palette
from app.theme import Colors, Fonts, mono

# The time zone of a QLocale time format, with its parentheses.
_ZONE = re.compile(r"\s*\(?t+\)?")


class ConsoleView(QPlainTextEdit):
    """Console like a terminal: colored levels and a blinking cursor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the read-only view."""
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAccessibleName(QCoreApplication.translate("ConsoleView", "Consola"))
        self.pal = NEUTRAL
        font = mono(QFont())
        font.setPixelSize(Fonts.SIZE_MONO)
        self.setFont(font)

        self.cursor_visible = False
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._toggle_cursor)
        self.cursor_timer.start(600)

        # Ctrl+F opens it; it finds as one types, Enter goes to the next
        # match and Shift+Enter to the previous one, both wrapping
        # around, and Escape closes it.
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText(QCoreApplication.translate("ConsoleView", "Buscar…"))
        self.search_bar.setAccessibleName(
            QCoreApplication.translate("ConsoleView", "Buscar en la consola")
        )
        self.search_bar.hide()
        self.search_bar.textChanged.connect(self._find_typed)
        self.search_bar.returnPressed.connect(self._find_next)
        self._missing = False
        for keys, slot, owner, context in (
            ("Ctrl+F", self._toggle_search, self, Qt.ShortcutContext.WidgetWithChildrenShortcut),
            (
                "Shift+Return",
                self._find_previous,
                self.search_bar,
                Qt.ShortcutContext.WidgetShortcut,
            ),
            ("Escape", self._close_search, self.search_bar, Qt.ShortcutContext.WidgetShortcut),
        ):
            shortcut = QShortcut(QKeySequence(keys), owner)
            shortcut.setContext(context)
            shortcut.activated.connect(slot)
        self._restyle()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        console = theme.CONSOLE.on(self.pal)
        field = theme.FIELD.on(self.pal)
        # A search with no match turns its text red.
        text = Colors.ERROR if self._missing else field.fg
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {console.bg};
                color: {console.fg};
                selection-background-color: {self.pal.glow(0.30)};
                border: none;
                padding: 10px 12px;
            }}
        """)
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                background-color: {field.bg};
                color: {text};
                border: 1px solid {field.border};
                border-radius: 4px;
                padding: 6px;
                font-size: 14px;
            }}
        """)

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # It floats over the log: no layout places it, and its size
        # comes from its hint, so it grows with the text.
        hint = self.search_bar.sizeHint()
        w = max(200, hint.width())
        self.search_bar.setGeometry(self.width() - w - 20, 10, w, hint.height())

    @Slot(str, str)
    def append_log(self, text: str, level: str = "info") -> None:
        """Append one line, colored by its level."""
        fmt = QTextCharFormat()
        color_map = {
            "info": Colors.ACCENT,
            "ok": Colors.SUCCESS,
            "warn": Colors.WARNING,
            "error": Colors.ERROR,
        }
        level = level.lower()
        level_color = color_map.get(level, Colors.TEXT_DIM)

        now = self._stamp()

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.select(cursor.SelectionType.LineUnderCursor)
        if cursor.selectedText().endswith("▍"):
            cursor.deletePreviousChar()

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)

        fmt.setForeground(QBrush(Colors.TEXT_MUTED))
        self.setCurrentCharFormat(fmt)
        self.insertPlainText(f"[{now}] ")

        fmt.setForeground(QBrush(level_color))
        self.setCurrentCharFormat(fmt)
        level_str = f"[{level.upper()}]".ljust(7)
        self.insertPlainText(level_str)

        fmt.setForeground(QBrush(Colors.TEXT_DIM))
        self.setCurrentCharFormat(fmt)
        self.insertPlainText(f" {text}\n")

        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _stamp(self) -> str:
        """Return the date and time of now, in the widget's locale.

        The time takes the long format without its time zone: a log
        needs the seconds, which the short format leaves out.
        """
        locale = self.locale()
        now = QDateTime.currentDateTime()
        clock = _ZONE.sub("", locale.timeFormat(QLocale.FormatType.LongFormat))
        day = locale.toString(now.date(), QLocale.FormatType.ShortFormat)
        return f"{day} {locale.toString(now.time(), clock)}"

    @Slot()
    def clear_console(self) -> None:
        """Empty the view."""
        self.clear()

    def write_stub_message(self, capability_name: str) -> None:
        """Say that the capability has no body yet."""
        self.append_log(f"─── {capability_name} ───", "info")
        self.append_log(
            QCoreApplication.translate("ConsoleView", "Esta capacidad aún no está implementada."),
            "info",
        )
        self.append_log(
            QCoreApplication.translate(
                "ConsoleView", "El esqueleto de UI está funcionando correctamente."
            ),
            "info",
        )
        self.append_log(QCoreApplication.translate("ConsoleView", "Stub ejecutado"), "ok")

    @Slot()
    def _toggle_cursor(self) -> None:
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        if self.cursor_visible:
            cursor.select(cursor.SelectionType.LineUnderCursor)
            if cursor.selectedText().endswith("▍"):
                cursor.deletePreviousChar()
            self.cursor_visible = False
        else:
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(Colors.ACCENT))
            cursor.insertText("▍", fmt)
            self.cursor_visible = True

    @Slot()
    def _toggle_search(self) -> None:
        # Show the search bar and focus it, or hide it.
        if self.search_bar.isVisible():
            self._close_search()
            return
        self.search_bar.show()
        self.search_bar.setFocus()
        self.search_bar.selectAll()

    @Slot()
    def _close_search(self) -> None:
        # Hide the search bar and give the focus back to the log.
        self.search_bar.hide()
        self.setFocus()

    @Slot(str)
    def _find_typed(self, text: str) -> None:
        # Search again from where the current match starts, so the
        # match grows with each letter.
        cursor = self.textCursor()
        cursor.setPosition(cursor.selectionStart())
        self.setTextCursor(cursor)
        self._find(text, backward=False)

    @Slot()
    def _find_next(self) -> None:
        # Go to the next match.
        self._find(self.search_bar.text(), backward=False)

    @Slot()
    def _find_previous(self) -> None:
        # Go to the previous match.
        self._find(self.search_bar.text(), backward=True)

    def _find(self, text: str, *, backward: bool) -> None:
        """Select the next match of `text`, wrapping around the log."""
        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = not text or self.find(text, flags)
        if not found:
            cursor = self.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self.setTextCursor(cursor)
            found = self.find(text, flags)
        if self._missing == (not found):
            return
        self._missing = not found
        # The red says it to the eye; the description, to assistive
        # technology.
        self.search_bar.setAccessibleDescription(
            "" if found else QCoreApplication.translate("ConsoleView", "Sin resultados")
        )
        self._restyle()

    @override
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        copy_action = QAction(QCoreApplication.translate("ConsoleView", "Copy"), self)
        copy_action.triggered.connect(self.copy)
        select_all_action = QAction(QCoreApplication.translate("ConsoleView", "Select All"), self)
        select_all_action.triggered.connect(self.selectAll)
        clear_action = QAction(QCoreApplication.translate("ConsoleView", "Clear"), self)
        clear_action.triggered.connect(self.clear_console)

        menu.addAction(copy_action)
        menu.addAction(select_all_action)
        menu.addSeparator()
        menu.addAction(clear_action)

        menu.exec(event.globalPos())
