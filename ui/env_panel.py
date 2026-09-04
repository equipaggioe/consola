from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QToolButton, QFileDialog
)
from PySide6.QtCore import Qt, Signal

from ui.theme import Colors, Fonts
from core.projects import Project
from core import envfile
from core.settings import settings_by_group, Setting
from ui.widgets import ToggleSwitch


_TRUE = {'1', 'true', 'yes', 'y', 'on', 'si', 'true'}


def _truthy(value: str) -> bool:
    return (value or '').strip().lower() in _TRUE


class EnvRow(QWidget):
    """Una clave del esquema: etiqueta, campo y, si es secreta, ojo para revelar.

    Con `kind='bool'` (los seguros de `core/protection.py`) es un interruptor en
    vez de un campo: `value()` devuelve '1'/'0' para que el resto del panel siga
    tratando todo como texto y `.consola/config.env` no cambie de forma.
    """
    changed = Signal()

    def __init__(self, setting: Setting, value: str, accent: str, default_display: str = '', parent=None):
        super().__init__(parent)
        self.setting = setting
        self.accent = accent
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Un seguro no es un campo de texto: se dibuja como interruptor, con la
        # explicacion al lado en vez de una etiqueta a la izquierda. Escribir
        # '1' a mano en una casilla de seguridad es pedir que se escriba mal.
        self.field = None
        self.toggle = None
        if setting.kind == 'bool':
            self.toggle = ToggleSwitch(setting.display, _truthy(value), accent)
            self.toggle.setToolTip(f'{setting.key} - {setting.placeholder}')
            self.toggle.toggled.connect(self._on_toggle)
            lay.addWidget(self.toggle)
            if setting.placeholder:
                nota = QLabel(setting.placeholder)
                nota.setWordWrap(True)
                nota.setStyleSheet(
                    f"background: transparent; color: {Colors.TEXT_MUTED}; "
                    f"font-size: {Fonts.SIZE_XS}px;"
                )
                lay.addWidget(nota, 1)
            return

        self.label = QLabel(setting.display)
        self.label.setFixedWidth(118)
        self.label.setToolTip(setting.key)
        self.label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.field = QLineEdit(value)
        # `default_display` es el default ya resuelto para ESTE repo (fijo o
        # dinamico, ej. VPS_USER -> nombre de carpeta): dejar el campo vacio
        # no es un error, corre con lo que se ve de marca de agua aca.
        self.field.setPlaceholderText(setting.placeholder or default_display or setting.key)
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
        if self.toggle is not None:
            return '1' if self.toggle.is_checked() else '0'
        return self.field.text().strip()

    def set_value(self, value: str) -> None:
        if self.toggle is not None:
            # Un repo que todavia no dice nada se queda con el default del
            # esquema, que para los seguros es "protegido".
            crudo = (value or '').strip()
            self.toggle.set_checked(_truthy(crudo) if crudo
                                    else _truthy(self.setting.default),
                                    announce=False)
            return
        self.field.setText(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        if self.toggle is not None:
            self.toggle.set_accent(accent)
            return
        self._restyle()

    def _on_toggle(self, _checked: bool) -> None:
        self.changed.emit()


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
        self._filter: set[str] | None = None
        # Config vacio (sin valores, solo el repo): sirve para preguntarle
        # "que usarias vos" y que conteste con el default fijo o dinamico
        # (VPS_USER, DB_NAME) sin mezclarlo con lo que haya escrito el usuario.
        self._defaults = envfile.Config(repo_name=envfile.repo_name_of(project.path))

        self.setStyleSheet(f"EnvPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_file_bar())
        self.banner = self._build_banner()
        root.addWidget(self.banner)
        root.addWidget(self._build_body(), 1)

        self.reload()

    # --- construccion ---------------------------------------------------
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
        lay.addWidget(self.banner_label, 1)
        box.setVisible(False)
        return box

    def _build_file_bar(self) -> QWidget:
        """Barra fija con el estado de `.consola/config.env` y sus dos
        acciones, mutuamente excluyentes: crear archivo si no existe,
        importar valores si ya existe uno donde ponerlos."""
        bar = QWidget()
        bar.setStyleSheet(f"background: {Colors.SURFACE}; border-bottom: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)

        self.file_label = QLabel("")
        self.file_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.import_btn = QPushButton("Importar desde archivo…")
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.clicked.connect(self.browse_import)

        self.create_btn = QPushButton("Crear archivo")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self.create_file)

        lay.addWidget(self.file_label, 1)
        lay.addWidget(self.import_btn)
        lay.addWidget(self.create_btn)
        self._restyle_create()
        return bar

    def _restyle_create(self) -> None:
        button_css = f"""
            QPushButton {{
                background: transparent; border: 1px solid {self.accent};
                color: {self.accent}; border-radius: 5px;
                padding: 4px 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {Colors.SURFACE_HOVER}; }}
        """
        self.create_btn.setStyleSheet(button_css)
        self.import_btn.setStyleSheet(button_css)

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
                row = EnvRow(setting, '', self.accent, default_display=self._defaults.get(setting.key))
                row.changed.connect(self._on_row_changed)
                self.rows[setting.key] = row
                self._row_group[setting.key] = block_widget
                block.addWidget(row)
            lay.addWidget(block_widget)

        scroll.setWidget(content)
        return scroll

    # --- API --------------------------------------------------------------
    def values(self) -> dict[str, str]:
        return {key: row.value() for key, row in self.rows.items()}

    def reload(self) -> None:
        values = envfile.load_config(self.project.path)
        for key, row in self.rows.items():
            row.blockSignals(True)
            row.set_value(values.get(key, ''))
            row.blockSignals(False)

        exists = os.path.isfile(envfile.config_path(self.project.path))
        if not exists:
            self.banner_label.setText(
                "No hay .consola/config.env todavía. Pulsa «Crear archivo» para "
                "generarlo en blanco con todas las claves."
            )
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

        self._sync_file_bar(exists)
        self.values_changed.emit(self.values())

    def _sync_file_bar(self, exists: bool) -> None:
        rel = os.path.join(envfile.CONSOLA_DIR, envfile.CONFIG_NAME).replace(os.sep, '/')
        self.file_label.setText(f"{rel} — {'listo' if exists else 'no existe'}")
        self.create_btn.setVisible(not exists)
        self.import_btn.setVisible(exists)
        self.create_btn.setToolTip(
            "Crea el archivo con todas las claves del esquema, agrupadas y en blanco"
        )
        self.import_btn.setToolTip(
            "Importa claves conocidas desde otro archivo .env"
        )

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
            self._notify(f"{os.path.basename(path)} no tiene claves reconocidas.")
            return
        for key, value in imported.items():
            row = self.rows.get(key)
            if row is not None and not row.value():
                row.set_value(value)
        self._notify(
            f"Se importaron {len(imported)} claves de {os.path.basename(path)}. "
            f"Revisa y guarda para escribir el archivo."
        )

    def create_file(self) -> None:
        """Crea `.consola/config.env` con TODAS las claves del esquema —
        las que cualquier control puede llegar a pedir — agrupadas por
        categoria, comentadas y vacias.

        No pisa nada: si el archivo ya existe o el formulario tiene valores
        (escritos o importados), se conservan y solo se agregan en blanco
        las claves que falten.
        """
        path = envfile.save_config(self.project.path, self.values())
        self.reload()
        self._notify(f"Archivo creado en {path}")
        self.saved.emit(self.values())

    def _notify(self, text: str) -> None:
        self.banner_label.setText(text)
        self.banner.setVisible(True)

    def save(self) -> None:
        envfile.save_config(self.project.path, self.values())
        self.banner.setVisible(False)
        self.saved.emit(self.values())
        self.values_changed.emit(self.values())

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        for row in self.rows.values():
            row.set_accent(accent)
        self._restyle_create()

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
        self.values_changed.emit(self.values())
