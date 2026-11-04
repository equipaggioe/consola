"""The form of `.consola/config.env`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import override

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core import envfile, fields
from app.core.errors import TaskError
from app.core.projects import Project
from app.core.settings import Setting, settings_by_group
from app.theme import Colors, Fonts
from app.ui import palettes, params_store
from app.ui.palettes import Palette


def _to_lines(value: str) -> str:
    """Return what is saved (commas) as it edits (a line per entry)."""
    return "\n".join(envfile.split_list(value or ""))


# Height of the multi-line field, in lines. It starts at three empty,
# since a list of paths tends to have two or three, and grows with what
# is written up to five; from there it scrolls.
LIST_MIN_ROWS = 3
LIST_MAX_ROWS = 5


class _ClickToSelectLabel(QLabel):
    """A label that focuses its field.

    On a click and selects what is written.

    It is then ready for the first key to replace it whole, as in most
    forms.
    """

    def __init__(
        self, text: str, field: QLineEdit | QPlainTextEdit, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self._field = field
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._field.setFocus()
            self._field.selectAll()
        super().mousePressEvent(event)


class EnvRow(QWidget):
    """A schema key: label and field."""

    changed = Signal()

    def __init__(
        self,
        setting: Setting,
        value: str,
        pal: Palette,
        default_display: str = "",
        label_width: int = 118,
        parent: QWidget | None = None,
    ) -> None:
        """Build the label and the field."""
        super().__init__(parent)
        self.setting = setting
        self.pal = pal
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # A list is written over several lines: three certificate paths
        # in a QLineEdit do not show where one ends and the next begins.
        # It saves separated by commas; see `Setting.kind`.
        if setting.kind == "list":
            self.field = QPlainTextEdit(_to_lines(value))
            self.field.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.field.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self.field = QLineEdit(value)

        self.label = _ClickToSelectLabel(setting.display, self.field)
        self.label.setFixedWidth(label_width)
        self.label.setToolTip(setting.key)
        self.label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_XS}px;"
        )
        if setting.kind == "list":
            self.label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # `default_display` is the default already resolved for THIS
        # repo, fixed or dynamic (DB_USER from the folder's name):
        # leaving the field empty is no error, it runs with the
        # watermark shown here.
        #
        # And only that, or the `default_hint` of those with no default
        # to resolve: with neither, the watermark stays empty. It used
        # to fall back to the key's name, which is no value but a
        # reminder of what goes in the field; in the same gray and place
        # as the next row's default, it read as if something were
        # loaded.
        self.field.setPlaceholderText(default_display or setting.default_hint)
        self.field.textChanged.connect(self._on_text)

        lay.addWidget(self.label)
        lay.addWidget(self.field, 1)

        self._restyle()
        if self._is_list:
            self._fit_list_height()

    def set_default_display(self, default_display: str) -> None:
        """Update the watermark with the recomputed default.

        `DOMAIN`'s changes with what is written in other keys, so it
        does not stay fixed since the row was built.
        """
        self.field.setPlaceholderText(default_display or self.setting.default_hint)

    @property
    def _is_list(self) -> bool:
        return self.setting.kind == "list"

    def value(self) -> str:
        """Return what the field holds."""
        if isinstance(self.field, QPlainTextEdit):
            return ", ".join(envfile.split_list(self.field.toPlainText()))
        return self.field.text().strip()

    def set_value(self, value: str) -> None:
        """Set what the field holds."""
        if isinstance(self.field, QPlainTextEdit):
            self.field.setPlainText(_to_lines(value))
            self._fit_list_height()
            return
        self.field.setText(value)

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    # QLineEdit's `textChanged` sends the text and QPlainTextEdit's
    # sends nothing: without the default, the multi-line field never
    # emitted `changed` and what was written did not get saved.
    def _on_text(self, _text: str = "") -> None:
        self._restyle()
        if self._is_list:
            self._fit_list_height()
        self.changed.emit()

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        # Narrowing the row changes where each long path breaks, and so
        # how many lines the same text takes.
        super().resizeEvent(event)
        if self._is_list:
            self._fit_list_height()

    def _fit_list_height(self) -> None:
        """Fit the field's height to what is written.

        With one spare empty line.

        That extra line says «this is all»: a field ending exactly on
        the last path cannot be told from one cutting off the rest, and
        the list of files to copy is where an entry out of view becomes
        a deploy without its secret.

        A QPlainTextEdit's `documentSize()` counts LINES, not pixels,
        and counts those visible: a long path broken in two takes two.
        """
        assert isinstance(self.field, QPlainTextEdit)
        doc = self.field.document()
        doc.setTextWidth(max(1, self.field.viewport().width()))
        written = max(1, int(doc.size().height()))
        rows = min(max(written + 1, LIST_MIN_ROWS), LIST_MAX_ROWS)
        # A QPlainTextEdit's `frameWidth` with a style sheet already
        # includes `padding` besides the border: adding it apart gave a
        # field taller than the lines it claimed to show.
        height = (
            rows * self.field.fontMetrics().lineSpacing()
            + 2 * int(doc.documentMargin())
            + 2 * self.field.frameWidth()
        )
        if self.field.height() != height:
            self.field.setFixedHeight(height)

    def _restyle(self) -> None:
        # Lighter border = key without a value. The same signal, now in
        # the repo's tinted borders.
        border = self.pal.border if self.value() else self.pal.border_light
        widget = "QPlainTextEdit" if self._is_list else "QLineEdit"
        self.field.setStyleSheet(f"""
            {widget} {{
                background: {self.pal.surface_alt};
                color: {Colors.TEXT};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            {widget}:focus {{ border: 1px solid {self.pal.accent}; }}
        """)


class EnvPanel(QWidget):
    """View and editing of the active repo's `.consola/config.env`.

    It is per repo, not per tab: it stays the same while changing
    actions above. It writes the file regenerated from the schema
    (core/envfile).

    It holds DATA, what tasks need to work, and nothing else. The repo's
    guards went to `ui/security_panel.py`: no task reads them, so they
    are no datum of this file (`core/settings.py`, at the end).

    One group does not go to the file: «Máquina»
    (`Setting.scope='machine'`). It is data too, since `build_binary`
    reads it, but of THIS machine and not the project, so it saves in
    QSettings (`ui/params_store.py::machine_env`). It edits here because
    that is where one looks for a value with a key's name; the group's
    name says it is not the repo's.

    The «Credenciales» group adds the repo's `Settings` fields
    (`core/fields.py`), read on opening the panel: a new field in
    `config.py` appears on reopening the repo.
    """

    saved = Signal(dict)
    values_changed = Signal(dict)
    # config.env's state: it goes to the section's label the whole file
    # was reread (Reload button), not one keystroke.
    file_status_changed = Signal(str)
    # `ui/tab_panel.py` listens to also reread the queried axes: which
    # VPS to ask comes from this file.
    reloaded = Signal()

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Build the form from the schema and the saved values."""
        super().__init__(parent)
        self.project = project
        self.pal = palettes.get(project.theme)
        self.rows: dict[str, EnvRow] = {}
        self._row_group: dict[str, QWidget] = {}
        self._filter: set[str] | None = None
        self.file_status = ""
        self.fields, self.fields_error = self._read_fields()
        # Without this, a QWidget subclass ignores its own sheet's
        # background and shows the global sheet's gray (`theme.py`): the
        # section's body did not take the repo's color.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # The form above and the actions below: the buttons fall right
        # on the section's edge, at hand and not competing with the
        # first key for attention.
        root.addWidget(self._build_body(), 1)
        self.banner = self._build_banner()
        root.addWidget(self.banner)
        self.file_bar = self._build_file_bar()
        root.addWidget(self.file_bar)
        self._restyle()

        self.reload()

    # --- building ---
    def _read_fields(self) -> tuple[tuple[Setting, ...], str]:
        """Return the repo's `Settings` fields.

        Or the error preventing it.

        The error does not bring the panel down: it shows above the
        form, and any keys in the file stay under «Otras claves».
        """
        server = Path(self.project.path) / envfile.Config.for_project(self.project.path).get(
            "SERVER_DIR"
        )
        try:
            return fields.field_settings(server), ""
        except TaskError as error:
            return (), str(error)

    def _build_banner(self) -> QWidget:
        box = QWidget()
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
        """Build the section's footer.

        With the actions on `.consola/config.env`.

        The file's state, existing or not, does not go here: it travels
        through `file_status_changed` to the section header's label.
        Order: import and create at left, Reload and Save at right. Save
        is the only way to persist edits, because row changes only emit
        in memory.
        """
        bar = QWidget()
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
        self.reload_btn.setToolTip(
            "Descarta los cambios sin guardar, relee el archivo\n"
            "y vuelve a consultar los catálogos de los parámetros"
        )
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

    def _restyle(self) -> None:
        """Paint the backgrounds.

        Of the «Configuración del repo» section.

        The body is `panel`, one step below its header, and the footer
        with Save and Reload rises to `surface`, like the other bars.
        """
        self.setStyleSheet(f"EnvPanel {{ background: {self.pal.panel}; }}")
        self._scroll.setStyleSheet(self._scroll_style())
        self.banner.setStyleSheet(
            f"background: transparent; border-top: 1px solid {self.pal.border};"
        )
        self.file_bar.setStyleSheet(
            f"background: {self.pal.surface}; border-top: 1px solid {self.pal.border};"
        )
        self._restyle_create()

    def _scroll_style(self) -> str:
        """Leave the scroll with no background, showing the panel's.

        The bar's groove does need one. It falls under the same
        `QScrollArea > QWidget > QWidget` that makes the viewport
        transparent, since the bar is a child of the viewport, and
        transparent painted Qt's palette gray instead of the panel's
        background: a gray stripe at the edge of a tinted column. It
        gets its color by hand in this same sheet, which is the closest
        and the one that wins.
        """
        return (
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {self.pal.panel}; width: 8px; }}"
        )

    def _restyle_create(self) -> None:
        button_css = f"""
            QPushButton {{
                background: transparent; border: 1px solid {self.pal.accent};
                color: {self.pal.accent}; border-radius: 5px;
                padding: 4px 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {self.pal.surface_hover}; }}
        """
        self.create_btn.setStyleSheet(button_css)
        self.import_btn.setStyleSheet(button_css)
        self.reload_btn.setStyleSheet(button_css)
        self.save_btn.setStyleSheet(button_css)

    def _label_width(self) -> int:
        """Return the width the schema's longest label needs.

        With a margin.

        With the pixel size of the label's stylesheet (`Fonts.SIZE_XS`)
        and not `self.font()`: that one is the window's default font,
        not what actually shows.
        """
        font = QFont()
        font.setPixelSize(Fonts.SIZE_XS)
        metrics = QFontMetrics(font)
        longest = max(
            (s.display for group in settings_by_group(self.fields).values() for s in group),
            key=len,
            default="",
        )
        return metrics.horizontalAdvance(longest) + 12

    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll  # `_restyle` repaints it

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Width of the labels column: what the longest of the WHOLE
        # schema asks for, not a fixed number.
        label_width = self._label_width()

        if self.fields_error:
            notice = QLabel(self.fields_error)
            notice.setWordWrap(True)
            notice.setStyleSheet(
                f"background: transparent; color: {Colors.ERROR}; font-size: {Fonts.SIZE_XS}px;"
            )
            lay.addWidget(notice)

        for group, settings in settings_by_group(self.fields).items():
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
                row = EnvRow(setting, "", self.pal, label_width=label_width)
                row.changed.connect(self._on_row_changed)
                self.rows[setting.key] = row
                self._row_group[setting.key] = block_widget
                block.addWidget(row)
            lay.addWidget(block_widget)

        scroll.setWidget(content)
        return scroll

    # --- API ---
    def values(self) -> dict[str, str]:
        """Return the form's values."""
        return {key: row.value() for key, row in self.rows.items()}

    def reload(self) -> None:
        """Reread the file into the form."""
        values = {**envfile.load_config(self.project.path), **params_store.machine_env()}
        for key, row in self.rows.items():
            row.blockSignals(True)
            row.set_value(values.get(key, ""))
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
        self._refresh_defaults()
        self.values_changed.emit(self.values())
        self.reloaded.emit()

    def _refresh_defaults(self) -> None:
        """Recompute each field's watermark.

        With its default if left empty.

        Resolving once on opening is not enough: `DOMAIN` comes from
        `CF_DOMAIN_NAME`, so its default changes with what is written
        there. Resolved against a blank `Config` it showed empty,
        instead of what will actually be used.

        It computes without the key's own value: `Config.get` returns
        what is written before the default, and what is wanted here is
        what would happen if it stayed empty.
        """
        current = self.values()
        for key, row in self.rows.items():
            without_this = {k: v for k, v in current.items() if k != key}
            cfg = envfile.Config(without_this, repo_name=envfile.repo_name_of(self.project.path))
            row.set_default_display(cfg.get(key))

    def _sync_file_bar(self, exists: bool) -> None:
        rel = os.path.join(envfile.CONSOLA_DIR, envfile.CONFIG_NAME).replace(os.sep, "/")
        self.file_status = f"{rel} — {'listo' if exists else 'no existe'}"
        self.file_status_changed.emit(self.file_status)
        self.create_btn.setVisible(not exists)
        self.import_btn.setVisible(exists)
        self.create_btn.setToolTip(
            "Crea el archivo con todas las claves del esquema, agrupadas y en blanco"
        )
        self.import_btn.setToolTip("Importa claves conocidas desde otro archivo .env")

    def browse_import(self) -> None:
        """Import known keys from any .env file the user chooses.

        It assumes no conventions of other projects: the user chooses
        the file, and only Save writes anything.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar variables desde…",
            self.project.path,
            "Archivos .env (*.env);;Todos los archivos (*)",
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
        """Create `.consola/config.env` with ALL the schema's keys.

        Those any control may come to ask for, grouped by category,
        commented and empty. It overwrites nothing: if the file exists
        or the form has values, written or imported, they stay and only
        missing keys add blank.
        """
        path = envfile.save_config(self.project.path, self.values(), self.fields)
        self.reload()
        self._notify(f"Archivo creado en {path}")
        self.saved.emit(self.values())

    def _notify(self, text: str) -> None:
        self.banner_label.setText(text)
        self.banner.setVisible(True)

    def save(self) -> None:
        """Send each value to its place: the repo's file or QSettings.

        `save_config` already discards machine keys, so the two writes
        do not clash (`core/envfile.render_config`).
        """
        params_store.save_machine_env(self.values())
        envfile.save_config(self.project.path, self.values(), self.fields)
        self.banner.setVisible(False)
        self.saved.emit(self.values())
        self.values_changed.emit(self.values())

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()
        for row in self.rows.values():
            row.set_palette(pal)
        self._restyle_create()

    def filter_for(self, keys: set[str] | None) -> None:
        """Show only the keys the active action claims.

        `None` = no filter: the full view, when no tab is open.

        The repo's guards need no exception to the filter: they live in
        another section and another file (`ADR-0018` §4).
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

    # --- internal ---
    def _on_row_changed(self) -> None:
        self._refresh_defaults()
        self.values_changed.emit(self.values())
