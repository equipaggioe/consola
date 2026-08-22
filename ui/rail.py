from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QComboBox, QScrollArea, QPushButton,
    QHBoxLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QIcon, QPixmap

from ui.theme import Colors, Fonts
from core.registry import registry
from core.projects import MOCK_PROJECTS, Project
from ui.widgets import SectionHeader, ActionButton

class ProjectComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QComboBox {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 14px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background: {Colors.SURFACE};
                color: {Colors.TEXT};
                selection-background-color: {Colors.SURFACE_HOVER};
                border: 1px solid {Colors.BORDER};
            }}
        """)
        
    def add_project(self, project: Project):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(project.color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        
        self.addItem(QIcon(pixmap), project.name, project)


class ActionRail(QWidget):
    """Left rail: project selector + grouped action buttons."""
    action_requested = Signal(str)  # capability_id
    project_changed = Signal(object)  # Project
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.setStyleSheet(f"""
            ActionRail {{
                background-color: {Colors.SURFACE};
                border-right: 1px solid {Colors.BORDER};
            }}
        """)
        
        # 1. Branding
        self.branding_widget = QWidget()
        self.branding_widget.setFixedHeight(56)
        self.branding_layout = QHBoxLayout(self.branding_widget)
        self.branding_layout.setContentsMargins(16, 0, 16, 0)
        self.branding_layout.setSpacing(8)
        
        self.diamond = QLabel("◇")
        self.diamond.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 20px;")
        
        self.title = QLabel("CONSOLA")
        self.title.setStyleSheet(f"""
            color: {Colors.TEXT};
            font-size: 18px;
            font-weight: 700;
            letter-spacing: 3px;
        """)
        
        self.branding_layout.addWidget(self.diamond)
        self.branding_layout.addWidget(self.title)
        self.branding_layout.addStretch()
        
        self.branding_line = QWidget()
        self.branding_line.setFixedHeight(1)
        self.branding_line.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Colors.ACCENT}, stop:1 {Colors.ACCENT_PURPLE});")
        
        branding_container = QWidget()
        branding_container.setFixedHeight(56)
        bc_layout = QVBoxLayout(branding_container)
        bc_layout.setContentsMargins(0, 0, 0, 0)
        bc_layout.setSpacing(0)
        bc_layout.addWidget(self.branding_widget)
        bc_layout.addWidget(self.branding_line)
        
        self.layout.addWidget(branding_container)
        
        # 2. Project selector
        selector_container = QWidget()
        selector_layout = QVBoxLayout(selector_container)
        selector_layout.setContentsMargins(12, 12, 12, 12)
        
        self.project_combo = ProjectComboBox()
        for p in MOCK_PROJECTS:
            self.project_combo.add_project(p)
            
        self.project_combo.currentIndexChanged.connect(self._on_project_combo_changed)
        selector_layout.addWidget(self.project_combo)
        
        self.layout.addWidget(selector_container)
        
        # 3. Action list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {Colors.SURFACE};
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {Colors.BORDER_LIGHT};
                border-radius: 4px;
            }}
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(12, 0, 12, 12)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area, 1)
        
        # 4. Database entry
        db_container = QWidget()
        db_layout = QVBoxLayout(db_container)
        db_layout.setContentsMargins(12, 12, 12, 12)
        db_container.setStyleSheet(f"border-top: 1px solid {Colors.BORDER};")
        
        self.db_btn = QPushButton("🗄️ Base de datos")
        self.db_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Colors.TEXT};
                text-align: left;
                padding: 8px 12px;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {Colors.SURFACE_HOVER};
            }}
        """)
        self.db_btn.clicked.connect(lambda: self.action_requested.emit("db"))
        db_layout.addWidget(self.db_btn)
        
        self.layout.addWidget(db_container)
        
        self.populate()
        
        if MOCK_PROJECTS:
            self.project_changed.emit(MOCK_PROJECTS[0])
            
    def _on_project_combo_changed(self, index):
        if index >= 0:
            proj = self.project_combo.itemData(index)
            self.project_changed.emit(proj)
            
    def populate(self) -> None:
        groups = registry.get_groups()
        for group_name, capabilities in groups.items():
            icon = registry.get_group_icon(group_name)
            header = SectionHeader(group_name, icon, self)
            self.scroll_layout.addWidget(header)
            
            section_widget = QWidget()
            section_layout = QVBoxLayout(section_widget)
            section_layout.setContentsMargins(0, 0, 0, 8)
            section_layout.setSpacing(2)
            
            for cap in capabilities:
                if cap.axes:
                    expand_type = cap.axes[0].expand
                    if expand_type == 'buttons':
                        for val in cap.axes[0].values:
                            btn = ActionButton(cap.id, f"{cap.name} {val}", cap.icon, cap.kind, cap.axes[0].danger, self)
                            btn.action_triggered.connect(self._emit_action)
                            section_layout.addWidget(btn)
                    elif expand_type == 'scope':
                        header.add_scope_selector(cap.axes[0].values)
                        btn = ActionButton(cap.id, cap.name, cap.icon, cap.kind, False, self)
                        btn.action_triggered.connect(self._emit_action)
                        section_layout.addWidget(btn)
                    elif expand_type == 'menu':
                        btn = ActionButton(cap.id, cap.name, cap.icon, cap.kind, False, self)
                        btn.action_triggered.connect(self._emit_action)
                        section_layout.addWidget(btn)
                    else:
                        btn = ActionButton(cap.id, cap.name, cap.icon, cap.kind, False, self)
                        btn.action_triggered.connect(self._emit_action)
                        section_layout.addWidget(btn)
                else:
                    btn = ActionButton(cap.id, cap.name, cap.icon, cap.kind, False, self)
                    btn.action_triggered.connect(self._emit_action)
                    section_layout.addWidget(btn)
                    
            self.scroll_layout.addWidget(section_widget)
            header.toggled.connect(section_widget.setVisible)
            
    def _emit_action(self, cap_id: str):
        self.action_requested.emit(cap_id)
        
    def set_active_action(self, cap_id: str) -> None:
        pass
