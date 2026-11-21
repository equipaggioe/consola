"""Consola's entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

# Registers resources.qrc, which pyside6-rcc compiles: icon.png, the
# images of assets/ and the translations.
import app.rc_resources  # noqa: F401
from app import theme
from app.api import http
from app.services import language
from app.services.catalog import load_catalog
from app.services.tasks import bind_all
from app.windows.main_window import MainWindow


def main() -> None:
    # Enable high-DPI scaling
    """Create the QApplication and open the main window."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Consola")
    app.setOrganizationName("Equipaggio")
    # An INI file in every system, and not the Windows registry: the
    # same format and keys in Windows and Linux. It lands in
    # `%APPDATA%/Equipaggio/Consola.ini` or in
    # `~/.config/Equipaggio/Consola.ini`.
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    # Before any widget or declaration reads its texts.
    language.install(app)
    # The app's one QNetworkAccessManager, in this thread (ADR-0089).
    http.start()

    # The catalog declares each capability's shape; services/tasks gives
    # it a body.
    load_catalog()
    bind_all()

    # Apply the theme
    theme.apply(app)

    # Show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
