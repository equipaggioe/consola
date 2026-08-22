from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, Property, QEvent
from PySide6.QtGui import QPainter, QColor
from ..theme import Colors

class ChevronWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._angle = 0.0

    def get_angle(self) -> float:
        return self._angle

    def set_angle(self, value: float) -> None:
        self._angle = value
        self.update()

    angle = Property(float, get_angle, set_angle)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.translate(-self.width() / 2, -self.height() / 2)
        
        painter.setPen(QColor(Colors.TEXT_MUTED))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▸")
        painter.end()


class SectionHeader(QWidget):
    """Collapsible section with title, collapse chevron, optional scope selector."""
    toggled = Signal(bool)
    
    def __init__(self, title: str, icon: str = '', parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setContentsMargins(0, 12, 0, 0)
        self._expanded = True
        self._hovered = False
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        
        if icon:
            self.icon_label = QLabel(icon)
            layout.addWidget(self.icon_label)
            
        self.title_label = QLabel(title.upper())
        font = self.title_label.font()
        font.setPixelSize(11)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        self.scope_container = QHBoxLayout()
        layout.addLayout(self.scope_container)
        
        self.chevron = ChevronWidget()
        self.chevron.set_angle(90.0)
        layout.addWidget(self.chevron)
        
        self.anim = QPropertyAnimation(self.chevron, b"angle")
        self.anim.setDuration(150)
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._expanded == (not collapsed):
            return
        self._expanded = not collapsed
        
        self.anim.stop()
        self.anim.setStartValue(self.chevron.get_angle())
        self.anim.setEndValue(0.0 if collapsed else 90.0)
        self.anim.start()
        
        self.toggled.emit(self._expanded)

    def add_scope_selector(self, values: list[str]) -> QWidget:
        container = QWidget()
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(2, 2, 2, 2)
        clayout.setSpacing(0)
        container.setStyleSheet(f"""
            QWidget {{
                background: {Colors.SURFACE_ALT};
                border-radius: 4px;
            }}
            QLabel {{
                color: {Colors.TEXT_DIM};
                padding: 2px 6px;
                font-size: 10px;
            }}
            QLabel[active="true"] {{
                background: {Colors.ACCENT};
                color: {Colors.BG};
                border-radius: 3px;
            }}
        """)
        
        for i, val in enumerate(values):
            lbl = QLabel(val)
            lbl.setProperty("active", str(i == 0).lower())
            clayout.addWidget(lbl)
            
        self.scope_container.addWidget(container)
        return container

    def mouseReleaseEvent(self, event):
        self.set_collapsed(self._expanded)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event: QEvent):
        self._hovered = True
        self.update()
        super().enterEvent(event)
        
    def leaveEvent(self, event: QEvent):
        self._hovered = False
        self.update()
        super().leaveEvent(event)
        
    def paintEvent(self, event):
        if self._hovered:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(Colors.SURFACE_HOVER))
            painter.end()
        super().paintEvent(event)
