"""The form of `.consola/config.env`."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import envfile, fields, palettes, params_store
from app.services.errors import TaskError
from app.services.palettes import Palette
from app.services.projects import Project
from app.services.settings import Setting, settings_by_group
from app.theme import Colors, Fonts
from app.widgets.env_row import EnvRow


class EnvPanel(QWidget):
    """View and editing of the active repo's `.consola/config.env`.

    It is per repo, not per tab: it stays the same while changing
    actions above. It writes the file regenerated from the schema
    (services/envfile).

    It holds DATA, what tasks need to work, and nothing else. The repo's
    guards went to `widgets/security_panel.py`: no task reads them, so
    they are no datum of this file (`services/settings.py`, at the end).

    The machine keys (`Setting.scope='machine'`) are not here: they are
    THIS machine's and not the project's, and they edit in their own
    section (`widgets/machine_panel.py`). `values` still carries them,
    from QSettings, so a step's check sees what the run will read.

    A key with `needs` shows only if the repo's `Settings` declares that
    field, or if it already holds a value: hidden, a leftover value
    could not be erased from here.

    The «Credenciales» group adds the repo's `Settings` fields
    (`services/fields.py`), read on opening the panel: a new field in
    `config.py` appears on reopening the repo.
    """

    saved = Signal(dict)
    values_changed = Signal(dict)
    # config.env's state: it goes to the section's label the whole file
    # was reread (Reload button), not one keystroke.
    file_status_changed = Signal()
    # What a button did to the file (saved, imported, erased) and its
    # console level: `widgets/tab_panel.py` writes it in the settings
    # tab, so it takes no height from the form.
    notice = Signal(str, str)
    # `widgets/tab_panel.py` listens to also reread the queried axes:
    # which VPS to ask comes from this file.
    reloaded = Signal()

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Build the form from the schema and the saved values."""
        super().__init__(parent)
        self.project = project
        self.pal = palettes.get(project.theme)
        self.rows: dict[str, EnvRow] = {}
        self._row_group: dict[str, QWidget] = {}
        self._filter: set[str] | None = None
        # The file's state for the section header: the short word, the
        # detail for its tooltip, and whether it asks for attention.
        self.file_status = ""
        self.file_detail = ""
        self.file_warn = False
        self.read_error = ""
        self.declared: set[str] = set()  # `_read_fields` fills it
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
        self.file_bar = self._build_file_bar()
        root.addWidget(self.file_bar)
        # Its natural height always: a short section takes it from the
        # form's scroll, and squeezed the buttons otherwise.
        self.file_bar.setFixedHeight(self.file_bar.sizeHint().height())
        self._restyle()

        self.reload()

    # --- building ---
    def _read_fields(self) -> tuple[tuple[Setting, ...], str]:
        """Return the `Settings` fields, or the error preventing it.

        The error does not bring the panel down: it shows above the
        form, and the file is not written while it lasts, since without
        the fields the save would erase the credentials.
        """
        server = Path(self.project.path) / envfile.Config.for_project(self.project.path).get(
            "SERVER_DIR"
        )
        try:
            self.declared = set(fields.settings_fields(server))
            return fields.field_settings(server), ""
        except TaskError as error:
            return (), str(error)

    def _build_file_bar(self) -> QWidget:
        """Build the footer with the actions on `config.env`.

        The file's state, existing or not, does not go here: it travels
        through `file_status_changed` to the section header's label.
        Order: import or create at left, Reload and Save at right. Save
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
        self.create_btn.clicked.connect(self.save)

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
        """Paint the «Configuración del repo» section's backgrounds.

        The body is `panel`, one step above its header, and the footer
        with Save and Reload rises to `surface`, like the other bars.
        """
        footer = theme.FOOTER.on(self.pal)
        self.setStyleSheet(f"EnvPanel {{ background: {theme.SECTION_BODY.on(self.pal).bg}; }}")
        self._scroll.setStyleSheet(self._scroll_style())
        self.file_bar.setStyleSheet(
            f"background: {footer.bg}; border-top: 1px solid {footer.border};"
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
        body = theme.SECTION_BODY.on(self.pal).bg
        return (
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {body}; width: 8px; }}"
        )

    def _restyle_create(self) -> None:
        button = theme.ACCENT_BUTTON.on(self.pal)
        button_css = f"""
            QPushButton {{
                background: transparent; border: 1px solid {button.border};
                color: {button.fg}; border-radius: 5px;
                padding: 4px 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {button.hover}; }}
        """
        self.create_btn.setStyleSheet(button_css)
        self.import_btn.setStyleSheet(button_css)
        self.reload_btn.setStyleSheet(button_css)
        self.save_btn.setStyleSheet(button_css)

    def _label_width(self) -> int:
        """Return the longest label's width, plus a margin.

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
        self._content = content  # `content_height` measures it
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Width of the labels column: what the longest of the WHOLE
        # schema asks for, not a fixed number. The Parameters section
        # takes it too, so its fields line up with these
        # (`widgets/params_panel.py::_labeled`).
        label_width = self.label_width = self._label_width()

        if self.fields_error:
            notice = QLabel(self.fields_error)
            notice.setWordWrap(True)
            notice.setStyleSheet(
                f"background: transparent; color: {Colors.ERROR}; font-size: {Fonts.SIZE_XS}px;"
            )
            lay.addWidget(notice)

        for group, every in settings_by_group(self.fields).items():
            settings = [s for s in every if s.scope != "machine"]
            if not settings:
                continue
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
        """Return the form's values, plus the machine keys' values."""
        return {
            **params_store.machine_env(),
            **{key: row.value() for key, row in self.rows.items()},
        }

    def reload(self) -> None:
        """Reread the file into the form."""
        text = self._read_file()
        saved = envfile.parse_env(text or "")
        for key, row in self.rows.items():
            row.blockSignals(True)
            row.set_value(saved.get(key, ""))
            row.blockSignals(False)

        # A key with `needs` can appear or go with what was reread.
        self.filter_for(self._filter)
        self._sync_file_bar(text)
        self._refresh_defaults()
        self.values_changed.emit(self.values())
        self.reloaded.emit()

    def content_height(self) -> int:
        """Return the height of the whole form and its footer.

        From the content, not the scroll wrapping it: a `QScrollArea`
        has no height of its own. It is what Settings asks for when the
        machine section, below, is the one taking the excess.
        """
        return self._content.sizeHint().height() + self.file_bar.sizeHint().height()

    def reload_machine(self) -> None:
        """Pass on the machine keys the machine section saved.

        They have no row here, but `values` carries them: the defaults
        and the steps' checks are recomputed with the new ones, keeping
        unsaved repo edits.
        """
        self._refresh_defaults()
        self.values_changed.emit(self.values())

    def _read_file(self) -> str | None:
        """Return the file's text, keeping why it cannot be read."""
        try:
            text = envfile.config_text(self.project.path)
        except TaskError as error:
            self.read_error = str(error)
            return None
        self.read_error = ""
        return text

    def _refresh_defaults(self) -> None:
        """Recompute each field's watermark: its default if left empty.

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

    def _sync_file_bar(self, text: str | None) -> None:
        """Show the file's state and the button that updates it.

        The button hides only when the file already has the schema's
        form; until then it says whether it creates or rewrites it, and
        import is not offered. Neither it nor Save is enabled when the
        file cannot be read or the repo's fields are unknown: writing
        then would leave blank what could not be read, or erase the
        credentials.
        """
        rel = os.path.join(envfile.CONSOLA_DIR, envfile.CONFIG_NAME).replace(os.sep, "/")
        blocked = bool(self.read_error or self.fields_error)
        current = text is not None and not blocked and envfile.is_current(text, self.fields)
        if self.read_error:
            state, detail = "ilegible", self.read_error
        elif text is None:
            state = "no existe"
            detail = (
                f"No hay {rel} todavía. Pulsa «Crear archivo» para generarlo con todas las claves."
            )
        elif current:
            state, detail = "listo", ""
        else:
            state = "desactualizado"
            detail = self._outdated_notice(rel, envfile.parse_env(text))
        if self.fields_error:
            state = "no se puede guardar"
            detail = f"No se escribe {rel} mientras config.py tenga el error de arriba."

        self.file_status = f"{rel} — {state}"
        self.file_detail = detail
        self.file_warn = bool(detail)
        self.file_status_changed.emit()

        self.create_btn.setText("Crear archivo" if text is None else "Actualizar archivo")
        self.create_btn.setToolTip(
            "Escribe el archivo con todas las claves del esquema, en su orden y con sus "
            "comentarios, conservando los valores"
        )
        # The two share the slot: importing fills the form of a file
        # that already has the schema's form, so until it has it the
        # place goes to the button that gives it that form.
        self.create_btn.setVisible(not current and not blocked)
        self.save_btn.setEnabled(not blocked)
        self.import_btn.setVisible(current)
        self.import_btn.setToolTip("Importa claves conocidas desde otro archivo .env")

    def _outdated_notice(self, rel: str, saved: dict[str, str]) -> str:
        """Say the file is outdated, and what writing it erases."""
        notice = f"{rel} no tiene la forma actual del esquema."
        removed = envfile.removed_keys(saved, self.fields)
        if removed:
            notice += f" Al escribirlo se borran: {', '.join(removed)}."
        return notice

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
            self.notice.emit(f"{os.path.basename(path)} no tiene claves reconocidas.", "warn")
            return
        for key, value in imported.items():
            row = self.rows.get(key)
            if row is not None and not row.value():
                row.set_value(value)
        self.notice.emit(
            f"Se importaron {len(imported)} claves de {os.path.basename(path)}. "
            f"Revisa y guarda para escribir el archivo.",
            "info",
        )

    def save(self) -> None:
        """Write the repo's file.

        Save and «Crear/Actualizar archivo» both land here: the file is
        always written whole, with all the schema's keys in its order,
        and the form's values. `save_config` discards the machine keys
        `values` carries (`services/envfile.render_config`), and the
        keys the schema no longer declares, which it names after
        writing.
        """
        text = self._read_file()
        if self.read_error:
            self._sync_file_bar(text)
            self.notice.emit(f"No se guardó: {self.read_error}", "error")
            return
        removed = envfile.removed_keys(envfile.parse_env(text or ""), self.fields)
        path = envfile.save_config(self.project.path, self.values(), self.fields)
        self._sync_file_bar(self._read_file())
        self.notice.emit(f"Guardado {path}", "ok")
        if removed:
            self.notice.emit(f"Se borraron de config.env: {', '.join(removed)}.", "warn")
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
            row = self.rows[key]
            needs = row.setting.needs
            applies = not needs or needs in self.declared or bool(row.value())
            visible = applies and (keys is None or key in keys)
            row.setVisible(visible)
            if visible:
                visible_groups.add(block)
        for group_widget in set(self._row_group.values()):
            group_widget.setVisible(group_widget in visible_groups)

    # --- internal ---
    def _on_row_changed(self) -> None:
        self._refresh_defaults()
        self.values_changed.emit(self.values())
