from __future__ import annotations
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QToolButton, QFileDialog, QPlainTextEdit
)
from PySide6.QtCore import Qt, Signal

from ui.theme import Colors, Fonts
from core.projects import Project
from core import envfile
from ui import params_store
from core.settings import settings_by_group, Setting


def _to_lines(value: str) -> str:
    """Lo guardado (comas) tal como se edita (un renglon por entrada)."""
    return '\n'.join(envfile.split_list(value or ''))


# Alto del campo multilinea, en renglones. Arranca en tres vacios —una lista de
# rutas suele tener dos o tres— y crece con lo escrito hasta cinco; de ahi en
# adelante scrollea.
LIST_MIN_ROWS = 3
LIST_MAX_ROWS = 5


class EnvRow(QWidget):
    """Una clave del esquema: etiqueta, campo y, si es secreta, ojo para revelar."""
    changed = Signal()

    def __init__(self, setting: Setting, value: str, accent: str, default_display: str = '', parent=None):
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

        # Una lista se escribe en varios renglones: tres rutas de certificados
        # en un QLineEdit no dejan ver donde termina una y empieza la otra.
        # Guarda separado por comas — ver `Setting.kind`.
        if setting.kind == 'list':
            self.field = QPlainTextEdit(_to_lines(value))
            self.field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.field.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        else:
            self.field = QLineEdit(value)
            if setting.secret:
                self.field.setEchoMode(QLineEdit.EchoMode.Password)
        # `default_display` es el default ya resuelto para ESTE repo (fijo o
        # dinamico, ej. VPS_USER -> nombre de carpeta): dejar el campo vacio
        # no es un error, corre con lo que se ve de marca de agua aca.
        self.field.setPlaceholderText(setting.placeholder or default_display or setting.key)
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
        if self._is_list:
            self._fit_list_height()

    @property
    def _is_list(self) -> bool:
        return self.setting.kind == 'list'

    def value(self) -> str:
        if self._is_list:
            return ', '.join(envfile.split_list(self.field.toPlainText()))
        return self.field.text().strip()

    def set_value(self, value: str) -> None:
        if self._is_list:
            self.field.setPlainText(_to_lines(value))
            self._fit_list_height()
            return
        self.field.setText(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def _toggle_echo(self, revealed: bool) -> None:
        self.field.setEchoMode(
            QLineEdit.EchoMode.Normal if revealed else QLineEdit.EchoMode.Password
        )

    # `textChanged` de QLineEdit manda el texto y el de QPlainTextEdit no manda
    # nada: sin el default, el campo multilinea nunca emitia `changed` y lo
    # escrito no llegaba a guardarse.
    def _on_text(self, _text: str = '') -> None:
        self._restyle()
        if self._is_list:
            self._fit_list_height()
        self.changed.emit()

    def resizeEvent(self, event):
        # Al angostarse la fila cambia donde parte cada ruta larga, y con eso
        # cuantos renglones ocupa lo mismo escrito.
        super().resizeEvent(event)
        if self._is_list:
            self._fit_list_height()

    def _fit_list_height(self) -> None:
        """Alto del campo segun lo escrito, con un renglon vacio de sobra.

        Ese renglon de mas es el que dice "esto es todo": un campo que termina
        justo en la ultima ruta no se distingue de uno que esta cortando el
        resto, y la lista de archivos a copiar es justamente donde una entrada
        que no se ve se convierte en un deploy sin su secreto.

        `documentSize()` de un QPlainTextEdit cuenta RENGLONES, no pixeles, y
        cuenta los que se ven: una ruta larga que se parte en dos ocupa dos.
        """
        doc = self.field.document()
        doc.setTextWidth(max(1, self.field.viewport().width()))
        escritos = max(1, int(doc.size().height()))
        filas = min(max(escritos + 1, LIST_MIN_ROWS), LIST_MAX_ROWS)
        # `frameWidth` de un QPlainTextEdit con hoja de estilos ya incluye el
        # `padding` ademas del borde: sumarlo aparte daba un campo mas alto de
        # los renglones que decia mostrar.
        alto = (filas * self.field.fontMetrics().lineSpacing()
                + 2 * int(doc.documentMargin())
                + 2 * self.field.frameWidth())
        if self.field.height() != alto:
            self.field.setFixedHeight(alto)

    def _restyle(self) -> None:
        border = Colors.BORDER if self.value() else Colors.BORDER_LIGHT
        widget = 'QPlainTextEdit' if self._is_list else 'QLineEdit'
        self.field.setStyleSheet(f"""
            {widget} {{
                background: {Colors.SURFACE_ALT};
                color: {Colors.TEXT};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            {widget}:focus {{ border: 1px solid {self.accent}; }}
        """)


class EnvPanel(QWidget):
    """Vista y edicion de `.consola/config.env` del repo activo.

    Es por repo, no por pestana: se queda igual mientras cambias de accion
    arriba. Escribe el archivo regenerado desde el esquema (core/envfile).

    Aca hay DATOS —lo que las tareas necesitan para trabajar—, y nada mas. Los
    seguros del repo estuvieron un tiempo en este formulario y se fueron a
    `ui/security_panel.py`: no los lee ninguna tarea, asi que no son un dato de
    este archivo (`core/settings.py`, al final).

    Un grupo no va al archivo: «Máquina» (`Setting.scope='machine'`). Es dato
    igual —`build_binary` lo lee— pero de ESTA maquina y no del proyecto, asi
    que se guarda en QSettings (`ui/params_store.py::machine_env`). Se edita
    aca porque es donde uno busca un valor con nombre de clave; que no sea del
    repo lo dice el nombre del grupo.
    """
    saved = Signal(dict)
    values_changed = Signal(dict)
    file_status_changed = Signal(str)  # estado de config.env: va al rotulo de la seccion

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
        self.file_status = ''

        self.setStyleSheet(f"EnvPanel {{ background: {Colors.SURFACE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # El formulario arriba y las acciones abajo: los botones caen justo
        # sobre el borde de la seccion, a la mano y sin competir con la primera
        # clave por la mirada.
        root.addWidget(self._build_body(), 1)
        self.banner = self._build_banner()
        root.addWidget(self.banner)
        root.addWidget(self._build_file_bar())

        self.reload()

    # --- construccion ---------------------------------------------------
    def _build_banner(self) -> QWidget:
        box = QWidget()
        box.setStyleSheet(f"background: transparent; border-top: 1px solid {Colors.BORDER};")
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
        """Pie de la seccion con las acciones sobre `.consola/config.env`.

        El estado del archivo (existe o no) no va aca: viaja por
        `file_status_changed` al rotulo de la cabecera de la seccion. Orden:
        importar/crear a la izquierda, y a la derecha Recargar y Guardar —
        Guardar es el unico camino para persistir lo editado, porque los
        cambios de fila solo emiten en memoria."""
        bar = QWidget()
        bar.setStyleSheet(f"background: {Colors.SURFACE}; border-top: 1px solid {Colors.BORDER};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)

        self.import_btn = QPushButton("Importar desde archivo…")
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.clicked.connect(self.browse_import)

        self.create_btn = QPushButton("Crear archivo")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self.create_file)

        self.reload_btn = QPushButton("Recargar")
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setToolTip("Descarta los cambios sin guardar y relee el archivo")
        self.reload_btn.clicked.connect(self.reload)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setToolTip("Escribe .consola/config.env con los valores actuales")
        self.save_btn.clicked.connect(self.save)

        lay.addWidget(self.import_btn)
        lay.addWidget(self.create_btn)
        lay.addStretch(1)
        lay.addWidget(self.reload_btn)
        lay.addWidget(self.save_btn)
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
        self.reload_btn.setStyleSheet(button_css)
        self.save_btn.setStyleSheet(button_css)

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
        values = {**envfile.load_config(self.project.path),
                  **params_store.machine_env()}
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
        self.file_status = f"{rel} — {'listo' if exists else 'no existe'}"
        self.file_status_changed.emit(self.file_status)
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
        """Cada valor a su sitio: el archivo del repo o QSettings.

        `save_config` ya descarta las claves de maquina, asi que las dos
        escrituras no se pisan (`core/envfile.render_config`).
        """
        params_store.save_machine_env(self.values())
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

        Los seguros del repo no necesitan la excepcion al filtro que tenian
        aca: viven en otra seccion y en otro archivo
        (`docs/seguro-destructivos.md` §4).
        """
        self._filter = keys
        visible_groups: set[QWidget] = set()
        for key, block in self._row_group.items():
            visible = keys is None or key in keys
            self.rows[key].setVisible(visible)
            if visible:
                visible_groups.add(block)
        for group_widget in set(self._row_group.values()):
            group_widget.setVisible(group_widget in visible_groups)

    # --- interno ------------------------------------------------------------
    def _on_row_changed(self) -> None:
        self.values_changed.emit(self.values())
