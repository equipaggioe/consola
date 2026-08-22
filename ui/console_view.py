from __future__ import annotations
import datetime
from PySide6.QtWidgets import QPlainTextEdit, QLineEdit, QMenu
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QKeyEvent, QAction
from PySide6.QtCore import Qt, QTimer
from .theme import Colors, Fonts

class ConsoleView(QPlainTextEdit):
    """Terminal-like console with colored log levels and blinking cursor."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Colors.BG};
                color: {Colors.TEXT_DIM};
                selection-background-color: rgba(88, 166, 255, 0.3);
                border: none;
                padding: 8px;
            }}
        """)
        font = QFont()
        font.setFamily(Fonts.MONO.split(',')[0].strip('\'"'))
        font.setPixelSize(13)
        self.setFont(font)
        
        self.cursor_visible = False
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._toggle_cursor)
        self.cursor_timer.start(600)
        
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search...")
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        self.search_bar.hide()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = 200
        h = 28
        self.search_bar.setGeometry(self.width() - w - 20, 10, w, h)

    def append_log(self, text: str, level: str = 'info') -> None:
        fmt = QTextCharFormat()
        color_map = {
            'info': Colors.ACCENT,
            'ok': Colors.SUCCESS,
            'warn': Colors.WARNING,
            'error': Colors.ERROR
        }
        level = level.lower()
        level_color = color_map.get(level, Colors.TEXT_DIM)
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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

    def clear_console(self) -> None:
        self.clear()

    def write_stub_message(self, capability_name: str) -> None:
        self.append_log(f"─── {capability_name} ───", "info")
        self.append_log("Esta capacidad aún no está implementada.", "info")
        self.append_log("El esqueleto de UI está funcionando correctamente.", "info")
        self.append_log("Stub ejecutado", "ok")

    def _toggle_cursor(self):
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

    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.search_bar.setVisible(not self.search_bar.isVisible())
            if self.search_bar.isVisible():
                self.search_bar.setFocus()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
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
