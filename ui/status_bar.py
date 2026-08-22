from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from .theme import Colors
from .widgets.led import LedIndicator

class StatusBar(QWidget):
    """Bottom bar with background service indicators and elapsed time."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            StatusBar {{
                background-color: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
            QLabel {{
                color: {Colors.TEXT_DIM};
                font-size: 11px;
            }}
        """)
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 0, 12, 0)
        self.layout.setSpacing(12)
        
        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(8)
        self.layout.addLayout(self.services_layout)
        
        self.layout.addStretch()
        
        self.stats_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.layout.addWidget(self.stats_label)
        
        self.add_service("Túnel Postgres")

    def add_service(self, name: str, icon: str = '') -> None:
        container = QWidget()
        container.setObjectName(f"service_{name}")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(4)
        
        led = LedIndicator(size=8)
        led.set_state('green')
        clayout.addWidget(led)
        
        label = QLabel(name)
        clayout.addWidget(label)
        
        self.services_layout.addWidget(container)

    def remove_service(self, name: str) -> None:
        for i in range(self.services_layout.count()):
            item = self.services_layout.itemAt(i)
            if item and item.widget() and item.widget().objectName() == f"service_{name}":
                item.widget().deleteLater()
                break

    def update_elapsed(self, seconds: int) -> None:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        self.stats_label.setText(f"● 2 tareas activas  ·  {h:02d}:{m:02d}:{s:02d}")
