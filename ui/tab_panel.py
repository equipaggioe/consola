from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, 
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation
from PySide6.QtGui import QColor

from ui.theme import Colors, Fonts
from core.registry import Capability
from ui.console_view import ConsoleView
from ui.widgets import LedIndicator

class TabButton(QWidget):
    close_requested = Signal()
    tab_clicked = Signal()
    
    def __init__(self, title: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.title = title
        self.is_active = False
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 0, 8, 0)
        self.layout.setSpacing(8)
        
        self.led = LedIndicator(self, size=8)
        self.led.set_state('green')
        
        self.icon_label = QLabel(icon_name)
        self.icon_label.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        
        self.title_label = QLabel(title)
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Colors.ERROR};
            }}
        """)
        self.close_btn.clicked.connect(self.close_requested.emit)
        self.close_btn.hide()
        
        self.layout.addWidget(self.led)
        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.close_btn)
        
        self.update_style()
        
    def enterEvent(self, event):
        self.close_btn.show()
        if not self.is_active:
            self.setStyleSheet(f"""
                QWidget {{
                    background: {Colors.SURFACE_HOVER};
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                }}
            """)
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.close_btn.hide()
        self.update_style()
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.tab_clicked.emit()
        super().mousePressEvent(event)
        
    def set_active(self, active: bool):
        self.is_active = active
        self.update_style()
        
    def update_style(self):
        if self.is_active:
            self.setStyleSheet(f"""
                QWidget {{
                    background: {Colors.BG};
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    border-bottom: 2px solid {Colors.ACCENT};
                }}
                QLabel {{
                    color: {Colors.TEXT};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QWidget {{
                    background: transparent;
                }}
                QLabel {{
                    color: {Colors.TEXT_DIM};
                }}
            """)

class TabPanel(QWidget):
    """Center panel: tab bar + console/view + sub-tab bar."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Tab bar
        self.tab_bar_container = QWidget()
        self.tab_bar_container.setFixedHeight(36)
        self.tab_bar_container.setStyleSheet(f"background: {Colors.SURFACE};")
        self.tab_bar_layout = QHBoxLayout(self.tab_bar_container)
        self.tab_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_bar_layout.setSpacing(0)
        
        self.tabs_layout = QHBoxLayout()
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(0)
        self.tab_bar_layout.addLayout(self.tabs_layout)
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(36, 36)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                color: {Colors.TEXT_MUTED};
                background: transparent;
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{
                color: {Colors.TEXT};
            }}
        """)
        self.tab_bar_layout.addWidget(self.add_btn)
        self.tab_bar_layout.addStretch()
        
        # Content Area
        self.content_area = QStackedWidget()
        self.content_area.setStyleSheet(f"background: {Colors.BG};")
        
        # Welcome screen
        self.welcome_widget = QWidget()
        self.welcome_layout = QVBoxLayout(self.welcome_widget)
        self.welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.diamond_label = QLabel("◇")
        self.diamond_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 48px;")
        self.diamond_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title = QLabel("CONSOLA")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 24px; font-weight: 300; letter-spacing: 6px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Selecciona una acción del panel izquierdo")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.project_label = QLabel("── navetta ──")
        self.project_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px;")
        self.project_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.welcome_layout.addWidget(self.diamond_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.welcome_layout.addWidget(title, 0, Qt.AlignmentFlag.AlignHCenter)
        self.welcome_layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignHCenter)
        self.welcome_layout.addSpacing(20)
        self.welcome_layout.addWidget(self.project_label, 0, Qt.AlignmentFlag.AlignHCenter)
        
        self.content_area.addWidget(self.welcome_widget)
        
        # Sub-tab bar
        self.sub_tab_bar = QWidget()
        self.sub_tab_bar.setFixedHeight(32)
        self.sub_tab_bar.setStyleSheet(f"""
            QWidget {{
                background: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
        """)
        self.sub_tab_layout = QHBoxLayout(self.sub_tab_bar)
        self.sub_tab_layout.setContentsMargins(16, 0, 16, 0)
        self.sub_tab_layout.setSpacing(24)
        
        for name in ["Consola", "Bitácora", "Historial", "Configuración"]:
            lbl = QLabel(name)
            if name == "Consola":
                lbl.setStyleSheet(f"color: {Colors.ACCENT}; border-bottom: 2px solid {Colors.ACCENT};")
            else:
                lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
            self.sub_tab_layout.addWidget(lbl)
            
        self.sub_tab_layout.addStretch()
        
        status_lbl = QLabel("● N tareas activas  ·  00:00:00")
        status_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        self.sub_tab_layout.addWidget(status_lbl)
        
        self.layout.addWidget(self.tab_bar_container)
        self.layout.addWidget(self.content_area, 1)
        self.layout.addWidget(self.sub_tab_bar)
        
        self.tabs = []
        
    def set_welcome_project(self, name: str):
        self.project_label.setText(f"── {name} ──")
        
    def open_tab(self, capability: Capability, axis_value: str = '') -> None:
        title = f"{capability.name} {axis_value}".strip()
        icon = capability.icon or "⚡"
        
        btn = TabButton(title, icon)
        self.tabs_layout.addWidget(btn)
        self.tabs.append(btn)
        
        index = len(self.tabs) # welcome widget is 0
        btn.tab_clicked.connect(lambda: self._switch_tab(index))
        btn.close_requested.connect(lambda: self.close_tab(index))
        
        console = ConsoleView(self.content_area)
        self.content_area.addWidget(console)
        
        self._switch_tab(index)
        
    def close_tab(self, index: int) -> None:
        if index < 1 or index > len(self.tabs):
            return
            
        btn = self.tabs.pop(index - 1)
        btn.setParent(None)
        btn.deleteLater()
        
        widget = self.content_area.widget(index)
        self.content_area.removeWidget(widget)
        widget.deleteLater()
        
        for i, t in enumerate(self.tabs):
            t.tab_clicked.disconnect()
            t.close_requested.disconnect()
            t.tab_clicked.connect(lambda idx=i+1: self._switch_tab(idx))
            t.close_requested.connect(lambda idx=i+1: self.close_tab(idx))
            
        if self.tabs:
            new_idx = min(index, len(self.tabs))
            self._switch_tab(new_idx)
        else:
            self._switch_tab(0)
            
    def _switch_tab(self, index: int):
        self.content_area.setCurrentIndex(index)
        for i, btn in enumerate(self.tabs):
            btn.set_active(i + 1 == index)
            
    def get_console(self, index: int) -> ConsoleView:
        widget = self.content_area.widget(index)
        if isinstance(widget, ConsoleView):
            return widget
        return None
