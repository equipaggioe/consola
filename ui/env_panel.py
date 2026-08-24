from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QToolButton, QFileDialog
)
from PySide6.QtCore import Qt, Signal

FOOTER_BTN_HEIGHT = 34

from ui.theme import Colors, Fonts
from core.projects import Project
from core import envfile
from core.settings import settings_by_group, Setting


class EnvRow(QWidget):
    """Una clave del esquema: etiqueta, campo y, si es secreta, ojo para revelar."""
    changed = Signal()

    def __init__(self, setting: Setting, value: str, accent: str, parent=None):
        super().__init__(parent)
        self.setting = setting
        self.accent = accent
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.label = QLabel(setting.display)
        self.label.setFixedWidth(118)
        self.label.setToolTip(setting.key)
        self.label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.field = QLineEdit(value)
        self.field.setPlaceholderText(setting.placeholder or setting.default or setting.key)
        if setting.secret:
            self.field.setEchoMode(QLineEdit.EchoMode.Password)
        self.field.textChanged.connect(self._on_text)

        lay.addWidget(self.label)
        lay.addWidget(self.field, 1)

        if setting.secret:
            self.eye = QToolButton()
            self.eye.setText("👁")
            self.eye.setCheckable(True)
            self.eye.setCursor(Qt.CursorShape.PointingHandCursor)
            self.eye.setStyleSheet(f"""
                QToolButton {{
                    background: transparent; border: none;
                    color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px; padding: 2px;
                }}
                QToolButton:hover {{ color: {Colors.TEXT}; }}
            """)
            self.eye.toggled.connect(self._toggle_echo)
            lay.addWidget(self.eye)

        self._restyle()

    def value(self) -> str:
        return self.field.text().strip()

    def set_value(self, value: str) -> None:
        self.field.setText(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()


    def _toggle_echo(self, revealed: bool) -> None:
        self.field.setEchoMode(
            QLineEdit.EchoMode.Normal if revealed else QLineEdit.EchoMode.Password
        )

    def _on_text(self, _text: str) -> None:
        self._restyle()
        self.changed.emit()

    def _restyle(self) -> None:
        border = Colors.BORDER if self.value() else Colors.BORDER_LIGHT
        self.field.setStyleSheet(f"""
            QLineEdit {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QLineEdit:focus {{ border: 1px solid {self.accent}; }}
        """)


class EnvPanel(QWidget):
    """Vista y edicion de `.consola/config.env` del repo activo.

    Es por repo, no por pestana: se queda igual mientras cambias de accion
    arriba. Escribe el archivo regenerado desde el esquema (core/envfile).
    """
    saved = Signal(dict)
    values_changed = Signal(dict)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.accent = project.color
        self.rows: dict[str, EnvRow] = {}
        self._row_group: dict[str, QWidget] = {}
        self._dirty = False
        self._filter: set[str] | None = None

        self.setStyleSheet(f"EnvPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        self.banner = self._build_banner()
        root.addWidget(self.banner)
        root.addWidget(self._build_body(), 1)
        root.addWidget(self._build_footer())

        self.reload()

    # --- construccion ---------------------------------------------------
    def _build_header(self) -> QWidget:
        head = QWidget()
        head.setStyleSheet(f"background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(16, 9, 16, 9)
        lay.setSpacing(8)

        title = QLabel("CONFIGURACIÓN DEL REPO")
        title.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )
        self.path_label = QLabel("")
        self.path_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        lay.addWidget(title)
        lay.addStretch()
        lay.addWidget(self.path_label)
        return head

    def _build_banner(self) -> QWidget:
        box = QWidget()
        box.setStyleSheet(f"background: transparent; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(box)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)

        self.banner_label = QLabel("")
        self.banner_label.setWordWrap(True)
        self.banner_label.setStyleSheet(
            f"background: transparent; color: {Colors.WARNING}; font-size: {Fonts.SIZE_XS}px;"
        )
        self.banner_btn = QPushButton("Importar desde archivo…")
        self.banner_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.banner_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.WARNING};
                color: {Colors.WARNING}; border-radius: 4px;
                padding: 3px 10px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; }}
        """)
        self.banner_btn.clicked.connect(self.browse_import)

        lay.addWidget(self.banner_label, 1)
        lay.addWidget(self.banner_btn)
        box.setVisible(False)
        return box

    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        for group, settings in settings_by_group().items():
            block_widget = QWidget()
            block_widget.setStyleSheet("background: transparent;")
            block = QVBoxLayout(block_widget)
            block.setContentsMargins(0, 0, 0, 0)
            block.setSpacing(6)
            header = QLabel(group.upper())
            header.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
            )
            block.addWidget(header)
            for setting in settings:
                row = EnvRow(setting, '', self.accent)
                row.changed.connect(self._on_row_changed)
                self.rows[setting.key] = row
                self._row_group[setting.key] = block_widget
                block.addWidget(row)
            lay.addWidget(block_widget)

        scroll.setWidget(content)
        return scroll

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        foot.setStyleSheet(f"background: {Colors.SURFACE}; border-top: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 9, 16, 9)
        lay.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.reload_btn = QPushButton("Recargar")
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setFixedHeight(FOOTER_BTN_HEIGHT)
        self.reload_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_DIM}; border-radius: 5px;
                padding: 5px 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; color: {Colors.TEXT}; }}
        """)
        self.reload_btn.clicked.connect(self.reload)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setFixedHeight(FOOTER_BTN_HEIGHT)
        self.save_btn.clicked.connect(self.save)

        lay.addWidget(self.status_label, 1)
        lay.addWidget(self.reload_btn)
        lay.addWidget(self.save_btn)
        self._restyle_save()
        return foot

    # --- API --------------------------------------------------------------
    def values(self) -> dict[str, str]:
        return {key: row.value() for key, row in self.rows.items()}

    def reload(self) -> None:
        values = envfile.load_config(self.project.path)
        for key, row in self.rows.items():
            row.blockSignals(True)
            row.set_value(values.get(key, ''))
            row.blockSignals(False)
        self._dirty = False

        path = envfile.config_path(self.project.path)
        exists = os.path.isfile(path)
        self.path_label.setText(f".consola/{envfile.CONFIG_NAME}" if exists else "sin archivo")

        if not exists:
            self.banner_label.setText(
                "No hay .consola/config.env todavía. Completa y guarda para crearlo, "
                "o impórtalo desde otro archivo .env."
            )
            self.banner_btn.setVisible(True)
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

        self._update_status()
        self.values_changed.emit(self.values())

    def browse_import(self) -> None:
        """Importa claves conocidas desde cualquier archivo .env que el usuario elija.

        No asume convenciones de otros proyectos (nada de rutas fijas):
        el usuario elige el archivo, y recien Guardar escribe algo.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar variables desde…", self.project.path,
            "Archivos .env (*.env);;Todos los archivos (*)"
        )
        if not path:
            return
        imported = envfile.import_from(path)
        if not imported:
            self.banner_label.setText(f"{os.path.basename(path)} no tiene claves reconocidas.")
            return
        for key, value in imported.items():
            row = self.rows.get(key)
            if row is not None and not row.value():
                row.set_value(value)
        self.banner_label.setText(
            f"Se importaron {len(imported)} claves de {os.path.basename(path)}. "
            f"Revisa y guarda para escribir el archivo."
        )

    def save(self) -> None:
        path = envfile.save_config(self.project.path, self.values())
        self._dirty = False
        self.banner.setVisible(False)
        self.path_label.setText(f".consola/{envfile.CONFIG_NAME}")
        self._update_status(f"Guardado en {os.path.basename(path)}")
        self.saved.emit(self.values())
        self.values_changed.emit(self.values())

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        for row in self.rows.values():
            row.set_accent(accent)
        self._restyle_save()

    def filter_for(self, keys: set[str] | None) -> None:
        """Muestra solo las claves que la accion activa reclama.

        `None` = sin filtro (vista completa, cuando no hay pestana abierta).
        """
        self._filter = keys
        visible_groups: set[QWidget] = set()
        for key, row in self.rows.items():
            visible = keys is None or key in keys
            row.setVisible(visible)
            if visible:
                visible_groups.add(self._row_group[key])
        for group_widget in set(self._row_group.values()):
            group_widget.setVisible(group_widget in visible_groups)

    # --- interno ------------------------------------------------------------
    def _on_row_changed(self) -> None:
        self._dirty = True
        self._update_status()
        self.values_changed.emit(self.values())

    def _update_status(self, message: str = '') -> None:
        if message:
            self.status_label.setText(message)
        else:
            filled = sum(1 for v in self.values().values() if v)
            total = len(self.rows)
            suffix = " · sin guardar" if self._dirty else ""
            self.status_label.setText(f"{filled}/{total} claves con valor{suffix}")
        self._restyle_save()

    def _restyle_save(self) -> None:
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {self.accent if self._dirty else Colors.SURFACE_ALT};
                color: {Colors.BG if self._dirty else Colors.TEXT_MUTED};
                border: none; border-radius: 5px;
                padding: 5px 14px; font-size: {Fonts.SIZE_XS}px; font-weight: 600;
            }}
        """)
