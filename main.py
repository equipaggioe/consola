from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from core.catalog import load_catalog
from core.tasks import bind_all
from ui.theme import apply_theme
from ui.main_window import MainWindow

def main():
    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    app.setApplicationName('Consola')
    app.setOrganizationName('Consola')
    
    # El catalogo declara la forma de cada capacidad; core/tasks le da cuerpo.
    load_catalog()
    bind_all()
    
    # Apply premium dark theme
    apply_theme(app)
    
    # Show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
