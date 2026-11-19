"""The log view of a task tab."""

from __future__ import annotations

import re
from typing import override

from PySide6.QtCore import QDateTime, QLocale, Qt, QTimer, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QFont,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QTextCharFormat,
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
        self.setAccessibleName("Consola")
        self.pal = NEUTRAL
        font = mono(QFont())
        font.setPixelSize(Fonts.SIZE_MONO)
        self.setFont(font)

        self.cursor_visible = False
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._toggle_cursor)
        self.cursor_timer.start(600)

        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.setAccessibleName("Buscar en la consola")
        self.search_bar.hide()
        find = QShortcut(QKeySequence("Ctrl+F"), self)
        find.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        find.activated.connect(self._toggle_search)
        self._restyle()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        console = theme.CONSOLE.on(self.pal)
        field = theme.FIELD.on(self.pal)
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
                color: {field.fg};
                border: 1px solid {field.border};
                border-radius: 4px;
                padding: 6px;
                font-size: 14px;
            }}
        """)

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        w = 200
        h = 28
        self.search_bar.setGeometry(self.width() - w - 20, 10, w, h)

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

        fmt.setForeground(QColor(Colors.TEXT_MUTED))
        self.setCurrentCharFormat(fmt)
        self.insertPlainText(f"[{now}] ")

        fmt.setForeground(QColor(level_color))
        self.setCurrentCharFormat(fmt)
        level_str = f"[{level.upper()}]".ljust(7)
        self.insertPlainText(level_str)

        fmt.setForeground(QColor(Colors.TEXT_DIM))
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
        self.append_log("Esta capacidad aún no está implementada.", "info")
        self.append_log("El esqueleto de UI está funcionando correctamente.", "info")
        self.append_log("Stub ejecutado", "ok")

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
            fmt.setForeground(QColor(Colors.ACCENT))
            cursor.insertText("▍", fmt)
            self.cursor_visible = True

    @Slot()
    def _toggle_search(self) -> None:
        # Show the search bar and focus it, or hide it.
        self.search_bar.setVisible(not self.search_bar.isVisible())
        if self.search_bar.isVisible():
            self.search_bar.setFocus()

    @override
    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.copy)
        select_all_action = QAction("Select All", self)
        select_all_action.triggered.connect(self.selectAll)
        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear_console)

        menu.addAction(copy_action)
        menu.addAction(select_all_action)
        menu.addSeparator()
        menu.addAction(clear_action)

        menu.exec(event.globalPos())
