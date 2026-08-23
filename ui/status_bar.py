from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from .theme import Colors, Fonts
from .widgets.led import LedIndicator

class StatusBar(QWidget):
    """Barra inferior: repo activo, servicios en segundo plano y tiempo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.accent = Colors.ACCENT
        self._restyle()

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 0, 14, 0)
        self.layout.setSpacing(14)

        self.project_label = QLabel("—")
        self.layout.addWidget(self.project_label)

        sep = QLabel("│")
        sep.setStyleSheet(f"color: {Colors.BORDER}; background: transparent;")
        self.layout.addWidget(sep)

        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(10)
        self.layout.addLayout(self.services_layout)

        self.layout.addStretch()

        self.stats_label = QLabel("● 0 tareas activas  ·  00:00:00")
        self.layout.addWidget(self.stats_label)

        self.add_service("Tunel Postgres")
        self.set_accent(self.accent)

    def _restyle(self) -> None:
        self.setStyleSheet(f"""
            StatusBar {{
                background-color: {Colors.SURFACE};
                border-top: 1px solid {Colors.BORDER};
            }}
            QLabel {{
                color: {Colors.TEXT_DIM};
                background: transparent;
                font-size: {Fonts.SIZE_XS}px;
            }}
        """)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()
        self.project_label.setStyleSheet(
            f"color: {accent}; background: transparent; font-size: {Fonts.SIZE_SM}px; font-weight: 600;"
        )

    def set_project(self, name: str) -> None:
        self.project_label.setText(f"◇ {name}")

    def add_service(self, name: str, icon: str = '') -> None:
        container = QWidget()
        container.setObjectName(f"service_{name}")
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=9)
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

    def update_elapsed(self, seconds: int, tasks: int = 0) -> None:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        self.stats_label.setText(f"● {tasks} tareas activas  ·  {h:02d}:{m:02d}:{s:02d}")
