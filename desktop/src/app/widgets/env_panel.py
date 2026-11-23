"""The form of `.consola/config.env`."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import envfile, fields, palettes, params_store
from app.services.errors import TaskError
from app.services.palettes import Palette
from app.services.projects import Project
from app.services.settings import Setting, settings_by_group
from app.theme import Fonts
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

    def _build_file_bar(self) -> QFrame:
        """Build the footer with the actions on `config.env`.

        The file's state, existing or not, does not go here: it travels
        through `file_status_changed` to the section header's label.
        Order: import or create at left, Reload and Save at right. Save
        is the only way to persist edits, because row changes only emit
        in memory.
        """
        bar = QFrame()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 16)
        lay.setSpacing(8)

        self.import_btn = QPushButton(
            QCoreApplication.translate("EnvPanel", "Importar desde archivo…")
        )
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.clicked.connect(self.browse_import)

        self.create_btn = QPushButton(QCoreApplication.translate("EnvPanel", "Crear archivo"))
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.clicked.connect(self.save)

        self.reload_btn = QPushButton(QCoreApplication.translate("EnvPanel", "Recargar"))
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setToolTip(
            QCoreApplication.translate(
                "EnvPanel",
                "Descarta los cambios sin guardar, relee el archivo\ny vuelve a consultar "
                "los catálogos de los parámetros",
            )
        )
        self.reload_btn.clicked.connect(self.reload)

        self.save_btn = QPushButton(QCoreApplication.translate("EnvPanel", "Guardar"))
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setToolTip(
            QCoreApplication.translate(
                "EnvPanel", "Escribe .consola/config.env con los valores actuales"
            )
        )
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
        # The scroll's viewport fills with Base, the body's color.
        theme.SECTION_BODY.on(self.pal).dress(self)
        # No band of its own: the buttons sit on the section's body.
        theme.SECTION_BODY.on(self.pal).dress(self.file_bar)
        self._restyle_create()

    def _restyle_create(self) -> None:
        button = theme.ACCENT_BUTTON.on(self.pal)
        for each in (self.create_btn, self.import_btn, self.reload_btn, self.save_btn):
            button.dress(each, fill=False)
            each.setFont(theme.font(Fonts.SIZE_XS))

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
        content = QWidget()
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
            notice.setFont(theme.font(Fonts.SIZE_XS))
            theme.ERROR_TEXT.on(self.pal).dress(notice)
            lay.addWidget(notice)

        for group, every in settings_by_group(self.fields).items():
            settings = [s for s in every if s.scope != "machine"]
            if not settings:
                continue
            block_widget = QWidget()
            block = QVBoxLayout(block_widget)
            block.setContentsMargins(0, 0, 0, 0)
            block.setSpacing(6)
            # The group is a key: settings.py declares it untranslated.
            header = QLabel(QCoreApplication.translate("settings", group).upper())
            header.setFont(theme.caption())
            theme.HINT.on(self.pal).dress(header)
            block.addWidget(header)
            for setting in settings:
                row = EnvRow(setting, "", self.pal, label_width=label_width)
                row.changed.connect(self._on_row_changed)
                self.rows[setting.key] = row
                self._row_group[setting.key] = block_widget
                block.addWidget(row)
            lay.addWidget(block_widget)

        return content

    # --- API ---
    def values(self) -> dict[str, str]:
        """Return the form's values, plus the machine keys' values."""
        return {
            **params_store.machine_env(),
            **{key: row.value() for key, row in self.rows.items()},
        }

    @Slot()
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
        rel = f"{envfile.CONSOLA_DIR}/{envfile.CONFIG_NAME}"
        blocked = bool(self.read_error or self.fields_error)
        current = text is not None and not blocked and envfile.is_current(text, self.fields)
        if self.read_error:
            state, detail = QCoreApplication.translate("EnvPanel", "ilegible"), self.read_error
        elif text is None:
            state = QCoreApplication.translate("EnvPanel", "no existe")
            detail = QCoreApplication.translate(
                "EnvPanel",
                "No hay {0} todavía. Pulsa «Crear archivo» para generarlo con todas las claves.",
            ).format(rel)
        elif current:
            state, detail = QCoreApplication.translate("EnvPanel", "listo"), ""
        else:
            state = QCoreApplication.translate("EnvPanel", "desactualizado")
            detail = self._outdated_notice(rel, envfile.parse_env(text))
        if self.fields_error:
            state = QCoreApplication.translate("EnvPanel", "no se puede guardar")
            detail = QCoreApplication.translate(
                "EnvPanel", "No se escribe {0} mientras config.py tenga el error de arriba."
            ).format(rel)

        self.file_status = f"{rel} — {state}"
        self.file_detail = detail
        self.file_warn = bool(detail)
        self.file_status_changed.emit()

        self.create_btn.setText(
            QCoreApplication.translate("EnvPanel", "Crear archivo")
            if text is None
            else QCoreApplication.translate("EnvPanel", "Actualizar archivo")
        )
        self.create_btn.setToolTip(
            QCoreApplication.translate(
                "EnvPanel",
                "Escribe el archivo con todas las claves del esquema, en su orden y con "
                "sus comentarios, conservando los valores",
            )
        )
        # The two share the slot: importing fills the form of a file
        # that already has the schema's form, so until it has it the
        # place goes to the button that gives it that form.
        self.create_btn.setVisible(not current and not blocked)
        self.save_btn.setEnabled(not blocked)
        self.import_btn.setVisible(current)
        self.import_btn.setToolTip(
            QCoreApplication.translate(
                "EnvPanel", "Importa claves conocidas desde otro archivo .env"
            )
        )

    def _outdated_notice(self, rel: str, saved: dict[str, str]) -> str:
        """Say the file is outdated, and what writing it erases."""
        notice = QCoreApplication.translate(
            "EnvPanel", "{0} no tiene la forma actual del esquema."
        ).format(rel)
        removed = envfile.removed_keys(saved, self.fields)
        if removed:
            notice += QCoreApplication.translate(
                "EnvPanel", " Al escribirlo se borran: {0}."
            ).format(", ".join(removed))
        return notice

    @Slot()
    def browse_import(self) -> None:
        """Import known keys from any .env file the user chooses.

        It assumes no conventions of other projects: the user chooses
        the file, and only Save writes anything. The dialog opens with
        `open()`, and `import_file` reads what it chooses.
        """
        dialog = QFileDialog(
            self,
            QCoreApplication.translate("EnvPanel", "Importar variables desde…"),
            self.project.path,
            QCoreApplication.translate(
                "EnvPanel", "Archivos .env (*.env);;Todos los archivos (*)"
            ),
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.fileSelected.connect(self.import_file)
        dialog.open()

    @Slot(str)
    def import_file(self, path: str) -> None:
        """Fill the empty fields with the known keys of that file."""
        imported = envfile.import_from(path)
        if not imported:
            self.notice.emit(
                QCoreApplication.translate("EnvPanel", "{0} no tiene claves reconocidas.").format(
                    Path(path).name
                ),
                "warn",
            )
            return
        for key, value in imported.items():
            row = self.rows.get(key)
            if row is not None and not row.value():
                row.set_value(value)
        self.notice.emit(
            QCoreApplication.translate(
                "EnvPanel",
                "Se importaron {0} claves de {1}. Revisa y guarda para escribir el archivo.",
            ).format(len(imported), Path(path).name),
            "info",
        )

    @Slot()
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
            self.notice.emit(
                QCoreApplication.translate("EnvPanel", "No se guardó: {0}").format(
                    self.read_error
                ),
                "error",
            )
            return
        removed = envfile.removed_keys(envfile.parse_env(text or ""), self.fields)
        path = envfile.save_config(self.project.path, self.values(), self.fields)
        self._sync_file_bar(self._read_file())
        self.notice.emit(QCoreApplication.translate("EnvPanel", "Guardado {0}").format(path), "ok")
        if removed:
            self.notice.emit(
                QCoreApplication.translate("EnvPanel", "Se borraron de config.env: {0}.").format(
                    ", ".join(removed)
                ),
                "warn",
            )
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
    @Slot()
    def _on_row_changed(self) -> None:
        self._refresh_defaults()
        self.values_changed.emit(self.values())
