from __future__ import annotations
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt

from ui.rail import ActionRail
from ui.tab_panel import TabPanel
from ui.status_bar import StatusBar
from core.registry import registry
from core.projects import Project

class MainWindow(QMainWindow):
    """Consola main window: rail | tabs | status bar."""
    
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Consola — navetta")
        self.resize(1400, 900)
        self.setMinimumSize(900, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Top layout: rail + tabs
        self.top_layout = QHBoxLayout()
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(0)
        
        self.rail = ActionRail()
        self.tab_panel = TabPanel()
        
        self.top_layout.addWidget(self.rail)
        self.top_layout.addWidget(self.tab_panel, 1) # Expanding
        
        self.main_layout.addLayout(self.top_layout, 1)
        
        # Bottom: status bar
        self.status_bar = StatusBar()
        self.main_layout.addWidget(self.status_bar)
        
        # Connections
        self.rail.action_requested.connect(self._on_action_requested)
        self.rail.project_changed.connect(self._on_project_changed)
        
    def _on_action_requested(self, capability_id: str) -> None:
        capability = registry.get_capability(capability_id)
        if capability:
            self.tab_panel.open_tab(capability)
            console = self.tab_panel.get_console(self.tab_panel.content_area.currentIndex())
            if console:
                console.write_stub_message(capability.name)
                
    def _on_project_changed(self, project: Project) -> None:
        self.setWindowTitle(f"Consola — {project.name}")
        self.tab_panel.set_welcome_project(project.name)
