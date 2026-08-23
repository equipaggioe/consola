from __future__ import annotations
from PySide6.QtWidgets import QPushButton, QHBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt, QEvent
from PySide6.QtGui import QCursor
from .led import LedIndicator
from ..theme import Colors, Fonts

class ActionButton(QPushButton):
    """Flat button with LED indicator, icon, label, hover glow."""
    action_triggered = Signal(str)
    
    def __init__(self, capability_id: str, label: str, icon: str = '',
                 kind: str = 'once', danger: bool = False, parent=None):
        super().__init__(parent)
        self.capability_id = capability_id
        self.kind = kind
        self.danger = danger
        self._running = False
        self._hovered = False
        
        self.setFixedHeight(36)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setObjectName("ActionButton")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)
        
        self.led = LedIndicator(size=8)
        self.led.set_state('off')
        
        self.icon_label = QLabel(icon)
        self.icon_label.setFixedWidth(18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.text_label = QLabel(label)
        font = self.text_label.font()
        font.setPixelSize(Fonts.SIZE_SM)
        self.text_label.setFont(font)
        
        self.menu_indicator = QLabel("▸")
        self.menu_indicator.setStyleSheet(f"color: {Colors.TEXT_MUTED}; background: transparent;")
        
        layout.addWidget(self.led)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        layout.addWidget(self.menu_indicator)
        
        self.update_style()
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self.action_triggered.emit(self.capability_id)
        
    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self.led.set_state('green')
        else:
            self.led.set_state('off')
        self.update_style()
            
    def update_style(self):
        bg_color = "transparent"
        text_color = Colors.TEXT_DIM
        
        if self._hovered:
            bg_color = Colors.SURFACE_HOVER
            if self.danger:
                text_color = Colors.ERROR
                if not self._running:
                    self.led.set_state('red')
            else:
                text_color = Colors.TEXT
        else:
            if not self._running:
                self.led.set_state('off')
        
        self.setStyleSheet(f"""
            QPushButton#ActionButton {{
                background-color: {bg_color};
                border-radius: 6px;
                border: none;
            }}
        """)
        self.text_label.setStyleSheet(f"color: {text_color}; background: transparent;")

    def enterEvent(self, event: QEvent):
        self._hovered = True
        self.update_style()
        super().enterEvent(event)
        
    def leaveEvent(self, event: QEvent):
        self._hovered = False
        self.update_style()
        super().leaveEvent(event)
