"""The parameters panel of one action."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, Signal, Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import envfile, favorites, palettes, params_store
from app.services.axes_loader import ERRORS, LIVE, PREVIEW, AxesLoader
from app.services.catalog import (
    PREVIEW_HINTS,
    PREVIEW_TITLES,
    for_project,
)
from app.services.palettes import Palette
from app.services.projects import Project
from app.services.registry import AxisDef, Capability, Step, registry
from app.services.settings import relevant_keys_for, required_keys_for
from app.theme import Colors, Fonts, check_css
from app.widgets.env_panel import EnvPanel
from app.widgets.favorite_star import FavoriteStar


class _SectionLabel(QLabel):
    """A section's small label."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        """Build the label."""
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; "
            f"font-size: {Fonts.SIZE_XS}px; font-weight: 700; letter-spacing: 1.2px;"
        )


# Minimum width of a closed list, in characters. It is not the real
# width but all the combo requires, so it then stretches with the row
# instead of pushing it (`_pick_combo`).
_COMBO_MIN_CHARS = 8

# The arrow of a closed list. Drawn by hand because styling the combo's
# border leaves the native drop-down box on top of it, cutting the right
# edge; styling `::drop-down` hides that box and its arrow with it.
_ARROW = ":/assets/chevron-down.svg"


class ParamsPanel(QWidget):
    """The parameters of ONE run: variants, steps and options.

    It lives inside the action's tab, so its state survives changing
    tabs and coming back, and from there one can run again.
    """

    execute_requested = Signal(dict)
    # what is saved changed: check what can run at once
    params_changed = Signal()
    # stop something running (an emulator's serial)
    stop_requested = Signal(str)
    # the footer's Clear: empty the tab's log
    clear_requested = Signal()
    # the footer's star marked or unmarked the action; already saved
    favorite_changed = Signal()

    def __init__(
        self,
        capability: Capability,
        project: Project,
        env_panel: EnvPanel,
        parent: QWidget | None = None,
    ) -> None:
        """Build the panel from the capability and what is saved."""
        super().__init__(parent)
        # Discovered axes resolve against THIS repo, not the catalog:
        # the list of apps comes from looking at the folders (ADR-0006).
        # A copy of the axes of its own: discovered and machine axes
        # fill on this capability, and the global catalog stays
        # untouched.
        base = for_project(capability, project.path)
        self.capability = replace(base, axes=[replace(a) for a in base.axes])
        self.project = project
        self.pal = palettes.get(project.theme)
        self.env_panel = env_panel
        # On the copy resolved for THIS repo, not the catalog's: it is
        # the one already left without the steps that do not exist here
        # (migrations in a repo without them).
        self.steps: list[Step] = registry.resolve_steps(self.capability)
        self._env: dict[str, str] = {}

        # axis -> value -> check
        self._checks: dict[str, dict[str, QCheckBox]] = {}
        # axis -> value -> check (exclusive)
        self._options: dict[str, dict[str, QCheckBox]] = {}
        # axis -> written value; axis -> long list with search; axis ->
        # feature -> its short list. It is the same `pick` axis as
        # above, drawn in several lists trimming each other
        # (`services/registry.py::Facet`); its value is still the whole
        # id, so it travels in the payload's same `picks` bucket.
        self._fields: dict[str, QLineEdit | QPlainTextEdit] = {}
        self._picks: dict[str, QComboBox] = {}
        self._facets: dict[str, dict[str, QComboBox]] = {}
        # axis -> where its checkboxes go
        self._multi_layouts: dict[str, QVBoxLayout] = {}
        # axis -> where its exclusive options go
        self._option_layouts: dict[str, QVBoxLayout] = {}
        # axis -> «there is none here» label
        self._empty_notes: dict[str, QLabel] = {}
        self._loader: AxesLoader | None = None
        self._loading = any(a.is_queried for a in self.capability.axes)
        # axis -> its live exclusive group. A dict and not a list
        # because a queried axis refills each time the tab shows, and
        # the group it replaces has to be let go.
        self._option_groups: dict[str, QButtonGroup] = {}
        self._step_checks: dict[str, QCheckBox] = {}
        self._step_rows: dict[str, QWidget] = {}
        self._restoring = True  # while building, no change saves
        # Without this, a QWidget subclass ignores its own sheet's
        # background and shows the global sheet's gray (`theme.py`): the
        # section's body did not take the repo's color.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._body_widget = self._build_body()
        # The footer with Run and Dry run does not live inside the
        # panel: `TabPanel` takes it to a fixed bar at the column's
        # bottom, so the button does not fold with the parameters
        # section or need scrolling to. It builds here anyway, since all
        # the blocking logic is this class's, and the container
        # reparents it.
        self.footer = self._build_footer()
        self._restyle()

        root.addWidget(self._body_widget, 1)

        # What was chosen last time for this button IN THIS repo wins
        # over the defaults; with nothing saved, those above stay.
        self.apply_state(params_store.load(self.project.path, self.capability.id))
        self._restoring = False
        self._refresh_summary()
        if self._asks():
            self._load_machine()

    # --- queried catalogs ----------------------------------------
    def _asks(self) -> bool:
        """Return whether something of the panel comes from asking."""
        cap = self.capability
        return any(a.is_queried for a in cap.axes) or bool(cap.live_state or cap.preview)

    def _load_machine(self, refresh: bool = False) -> None:
        """Ask for the SDK and VPS catalogs, not blocking the window."""
        if self._loader is not None and self._loader.isRunning():
            return
        self._loading = any(a.is_queried for a in self.capability.axes)
        self._refresh_summary()
        self._loader = AxesLoader(
            self.capability,
            params_store.task_config(self.project.path),
            self.project.path,
            refresh,
            self,
        )
        self._loader.ready.connect(self._on_machine_ready)
        self._loader.start()

    @Slot(dict)
    def _on_machine_ready(self, resolved: dict[str, Any]) -> None:
        """Fill the lists the query feeds, keeping what was chosen."""
        saved = params_store.load(self.project.path, self.capability.id)
        self._restoring = True
        try:
            for axis in self.capability.axes:
                if axis.name not in resolved:
                    continue
                axis.values, axis.labels = resolved[axis.name]
                axis.query_error = resolved[ERRORS].get(axis.name, "")
                if axis.name in self._facets:
                    self._fill_facets(axis)
                elif axis.name in self._picks:
                    self._fill_pick(axis)
                elif axis.name in self._multi_layouts:
                    self._fill_multi(axis)
                elif axis.name in self._option_layouts:
                    self._fill_options(axis)
            self._fill_live(resolved.get(LIVE, ([], {})), resolved[ERRORS].get(LIVE, ""))
            self._fill_preview(resolved.get(PREVIEW, ([], [])), resolved[ERRORS].get(PREVIEW, ""))
        finally:
            self._restoring = False
        self._loading = False
        self.apply_state(saved)
        self._refresh_summary()

    def refresh_machine(self) -> None:
        """Ask again, skipping the cache.

        It is the forced path: the Settings Reload button uses it, since
        besides rereading `config.env` it may have changed WHICH VPS is
        asked, and so does the end of a task that just touched the
        machine.
        """
        self._load_machine(refresh=True)

    def reload_catalogs(self) -> None:
        """Reread what is queried on showing the tab.

        Opening the tab is when the list is looked at, so that is when
        it has to be up to date; asking also for a click on a reload
        button asks twice for the same. It respects the cache on
        purpose: what expires in a minute (AVDs, the VPS's services) is
        truly asked again, and the SDK's two large catalogs, which only
        change when the SDK updates, are not reread on each click.
        """
        if self._asks():
            self._load_machine()

    # --- building -------------------------------------------------
    def _build_body(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll  # `_restyle` repaints it

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # What is already running goes on top: it is the first thing to
        # know before choosing anything, and where an orphan emulator
        # stops from.
        self._live_box = self._build_live()
        lay.addWidget(self._live_box)

        picks = self.capability.pick_axes
        if picks:
            lay.addWidget(self._build_picks(picks))

        for axis in self.capability.multi_axes:
            lay.addWidget(self._build_multi_axis(axis))

        if len(self.steps) > 1:
            lay.addWidget(self._build_steps())

        # What running will do, under the steps that run it.
        self._preview_box = self._build_preview()
        lay.addWidget(self._preview_box)

        # A single-valued axis is not chosen either, but it shows:
        # checked and disabled, so WHICH one is seen (which mobile app,
        # which target) without letting it be removed. `_build_options`
        # draws it so.
        #
        # A QUERIED axis enters even if empty: when the panel builds
        # nobody has been asked yet, and discarding it here left it
        # nowhere to appear when the answer came.
        singles = [a for a in self.capability.single_axes if a.values or a.is_queried]
        if singles:
            lay.addWidget(self._build_options(singles))

        # The written fields go last, under the choices: «Otra IP» reads
        # below the option that asks for it.
        fields = self.capability.field_axes
        if fields:
            lay.addWidget(self._build_fields(fields))

        self._content = content
        scroll.setWidget(content)
        return scroll

    def _build_picks(self, axes: list[AxisDef]) -> QWidget:
        """Build the long, closed lists: type to filter and choose.

        It is the panel's fourth form, and exists for the SDK's
        catalogs: a hundred devices and several hundred system images
        fit no checkboxes or segment, but they are no free text either,
        since the valid values are exactly those. The saved value is the
        id (`pixel_4`, `system-images;android-36;google_apis;x86_64`)
        and what reads is its label.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)

        for axis in axes:
            if axis.facets:
                lay.addWidget(self._build_facets(axis))
                continue
            combo = self._pick_combo(searchable=True)
            combo.currentIndexChanged.connect(self._refresh_summary)
            self._picks[axis.name] = combo
            self._fill_pick(axis)
            lay.addLayout(self._labeled(axis.display, combo))
        return box

    def _labeled(self, text: str, field: QWidget, *, top: bool = False) -> QHBoxLayout:
        """Return a row with the label at left and the field at right.

        The labels column is as wide as that of «Configuración del
        repo» (`EnvPanel.label_width`), and both bodies have the same
        margins: the fields of the two sections start at the same x and
        are as wide. `top` raises the label to the first line of a field
        taller than one.
        """
        label = QLabel(text)
        # The label names the field for assistive technology.
        label.setBuddy(field)
        label.setFixedWidth(self.env_panel.label_width)
        # With `wordWrap` a label longer than the column breaks in two
        # instead of pushing the field to the right.
        label.setWordWrap(True)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;"
        )
        row = QHBoxLayout()
        row.setSpacing(8)
        align = Qt.AlignmentFlag.AlignTop if top else Qt.AlignmentFlag.AlignVCenter
        row.addWidget(label, 0, align)
        row.addWidget(field, 1)
        return row

    def _pick_combo(self, *, searchable: bool) -> QComboBox:
        """Return the panel's closed list.

        `searchable` makes it editable, and editable is only to be able
        to type and filter: in a catalog of a hundred devices it is the
        only way to get there, and in a list of six variants it would be
        a cursor inviting to type what cannot be typed.
        """
        combo = QComboBox()
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumHeight(30)
        combo.setMaxVisibleItems(18)
        # The column rules the width, not the longest item. By default a
        # QComboBox asks at minimum for its longest entry, and here some
        # have 50 characters, so the whole panel could not narrow below
        # that and scrollbars appeared in a tight column. With this the
        # combo settles for `_COMBO_MIN_CHARS` and takes what the row
        # gives. The open list keeps that same width, under the field,
        # so a long entry is cut there too.
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(_COMBO_MIN_CHARS)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if searchable:
            combo.setEditable(True)
            completer = QCompleter(combo.model(), combo)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.setCompleter(completer)
        # The default delegate of a combo ignores `::item` in the
        # stylesheet: without this one, the entries would not take the
        # field's padding and their text would not line up with it.
        combo.setItemDelegate(QStyledItemDelegate(combo))
        combo.setStyleSheet(self._combo_style())
        return combo

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

    def _combo_style(self) -> str:
        field = theme.FIELD.on(self.pal)
        listing = theme.COMBO_LIST.on(self.pal)
        return f"""
            QComboBox {{
                background: {field.bg}; border: 1px solid {field.border};
                border-radius: 5px; padding: 0 8px;
                color: {field.fg}; font-size: {Fonts.SIZE_SM}px;
            }}
            QComboBox:focus {{ border: 1px solid {field.focus}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 18px; right: 6px; border: none; background: transparent;
            }}
            QComboBox::down-arrow {{ image: url({_ARROW}); width: 10px; height: 6px; }}
            QComboBox QAbstractItemView {{
                background: {listing.bg}; color: {listing.fg};
                selection-background-color: {listing.hover};
                border: 1px solid {listing.border}; outline: 0;
            }}
            QComboBox QAbstractItemView::item {{ padding: 0 8px; min-height: 26px; }}
        """

    def _build_facets(self, axis: AxisDef) -> QWidget:
        """Build a `pick` axis: one short list per part of the value.

        They all trim each other. The system image catalog is several
        hundred packages that are at bottom three questions, Android
        version, variant and architecture, already permuted. In one list
        one reads three hundred almost equal labels to find the one that
        changes in a field; worse, one cannot see what exists: that
        there is no Wear OS for 36 only shows by not finding it.

        Here each list offers *only what exists given the rest chosen*
        (`AxisDef.facet_values`), and changing one recomposes the others
        (`AxisDef.resolve_facets`). What saves does not change: it is
        still the whole package sdkmanager understands.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        lay.addWidget(_SectionLabel(axis.display))

        self._facets[axis.name] = {}
        for facet in axis.facets:
            combo = self._pick_combo(searchable=False)

            def on_facet(_index: int, a: AxisDef = axis) -> None:
                self._on_facet_changed(a)

            combo.currentIndexChanged.connect(on_facet)
            self._facets[axis.name][facet.name] = combo
            lay.addLayout(self._labeled(facet.label, combo))
        self._fill_facets(axis)
        return box

    def _on_facet_changed(self, axis: AxisDef) -> None:
        self._fill_facets(axis)
        self._refresh_summary()

    def _fill_facets(self, axis: AxisDef) -> None:
        """Reload the lists of an axis by feature.

        All are redone and not only those below: it costs the same and
        avoids tracking which changed. The cascade decides what moves
        (`AxisDef.resolve_facets`), not what fired.
        """
        combos = self._facets.get(axis.name) or {}
        if not combos:
            return
        current = {name: (c.currentData() or "") for name, c in combos.items()}
        resolved = axis.resolve_facets(current)
        for facet in axis.facets:
            combo = combos[facet.name]
            combo.blockSignals(True)
            combo.clear()
            options = axis.facet_values(facet, resolved)
            for value in options:
                combo.addItem(axis.text_of(value), value)
            if not options:
                combo.addItem(
                    QCoreApplication.translate("ParamsPanel", "leyendo el catálogo…")
                    if self._loading
                    else QCoreApplication.translate("ParamsPanel", "no hay ninguna {0}").format(
                        axis.query_place
                    ),
                    "",
                )
            index = combo.findData(resolved.get(facet.name, ""))
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)

    def _fill_pick(self, axis: AxisDef) -> None:
        """Reload a long list's options, keeping what was chosen."""
        combo = self._picks.get(axis.name)
        if combo is None:
            return
        previous = self.pick_value(axis.name)
        combo.blockSignals(True)
        combo.clear()
        if axis.allow_empty:
            # First entry and empty value: «I do not choose, let the
            # function decide». It is no more a value of the catalog, so
            # it goes here and not in `values`: the machine's catalog
            # overwrites that on each refresh.
            combo.addItem(
                axis.text_of("") or QCoreApplication.translate("ParamsPanel", "automático"), ""
            )
        for value in axis.values:
            combo.addItem(axis.text_of(value), value)
        if not axis.values:
            line = combo.lineEdit()
            assert line is not None
            line.setPlaceholderText(
                QCoreApplication.translate("ParamsPanel", "leyendo el catálogo…")
                if self._loading
                else QCoreApplication.translate("ParamsPanel", "no hay ninguno {0}").format(
                    axis.query_place
                )
            )
        index = combo.findData(previous)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _fill_multi(self, axis: AxisDef) -> None:
        """Recreate the checkboxes of a machine-filled axis."""
        lay = self._multi_layouts.get(axis.name)
        if lay is None:
            return
        for check in self._checks.get(axis.name, {}).values():
            lay.removeWidget(check)
            check.deleteLater()
        note = self._empty_notes.pop(axis.name, None)
        if note is not None:
            lay.removeWidget(note)
            note.deleteLater()
        self._checks[axis.name] = {}
        for value in axis.values:
            check = QCheckBox(axis.text_of(value))
            check.setChecked(axis.starts_checked(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._checks[axis.name][value] = check
            lay.addWidget(check)
        text = axis.query_error or QCoreApplication.translate(
            "ParamsPanel", "no hay ninguno {0}"
        ).format(axis.query_place)
        # The camera's axes fail together with the same message: the
        # first says it and the others stay empty.
        repeated = any(n.text() == text for n in self._empty_notes.values())
        if not axis.values and not repeated:
            # As on button axes: the gap says why it is empty. If the
            # source failed, what it said, which is what has to be
            # fixed.
            note = QLabel(text)
            note.setWordWrap(True)
            note.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )
            self._empty_notes[axis.name] = note
            lay.addWidget(note)

    def _build_live(self) -> QWidget:
        """Build the header with what is running now and its ✕."""
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        lay.addWidget(_SectionLabel(QCoreApplication.translate("ParamsPanel", "Corriendo ahora")))
        self._live_layout = lay
        box.setVisible(False)
        return box

    def _fill_live(self, inventory: tuple[Any, ...], error: str = "") -> None:
        """Rebuild the list of what is alive.

        Empty, the whole header goes.
        """
        values, labels = inventory
        while self._live_layout.count() > 1:
            item = self._live_layout.takeAt(1)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()

        for value in values:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            flay = QHBoxLayout(row)
            flay.setContentsMargins(0, 0, 0, 0)
            flay.setSpacing(6)

            text = QLabel(f"● {labels.get(value, value)}")
            text.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: "
                f"{Fonts.SIZE_SM}px;"
            )
            stop = QPushButton("✕")
            stop.setFixedSize(20, 20)
            stop.setCursor(Qt.CursorShape.PointingHandCursor)
            stop.setToolTip(QCoreApplication.translate("ParamsPanel", "Apagar"))
            stop.setAccessibleName(
                QCoreApplication.translate("ParamsPanel", "Apagar {0}").format(
                    labels.get(value, value)
                )
            )
            stop.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: none;
                               color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_SM}px; }}
                QPushButton:hover {{ color: {Colors.ERROR}; }}
            """)
            stop.clicked.connect(lambda _=False, v=value: self.stop_requested.emit(v))

            flay.addWidget(text)
            flay.addStretch()
            flay.addWidget(stop)
            self._live_layout.addWidget(row)

        if error:
            reason = QLabel(error)
            reason.setWordWrap(True)
            reason.setStyleSheet(
                f"background: transparent; color: {Colors.ERROR}; font-size: {Fonts.SIZE_SM}px;"
            )
            self._live_layout.addWidget(reason)
        self._live_box.setVisible(bool(values) or bool(error))

    def _build_preview(self) -> QWidget:
        """Build the header with what running will do.

        Hidden until the answer comes.
        """
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        title = PREVIEW_TITLES.get(self.capability.preview, "")
        lay.addWidget(_SectionLabel(QCoreApplication.translate("catalog", title)))
        self._preview_layout = lay
        box.setVisible(False)
        return box

    def _fill_preview(self, checks: tuple[list[str], list[str]], error: str = "") -> None:
        """Show what running will do, or why it could not be asked.

        One disabled check per value, in alphabetical order, marked if
        running does it: they are not chosen here, `config.env` decides
        them. The marked ones keep the blue of a marked check and not
        the gray of a disabled one, so what will run reads at a glance.
        """
        every, marked = checks
        while self._preview_layout.count() > 1:
            item = self._preview_layout.takeAt(1)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()
        for value in sorted(every):
            check = QCheckBox(value)
            check.setChecked(value in marked)
            check.setEnabled(False)
            # Marked like an enabled check (`_restyle`): it shows what
            # the run will take, not a choice that is off.
            check.setObjectName("previewCheck")
            hint = PREVIEW_HINTS.get(self.capability.preview, "")
            check.setToolTip(QCoreApplication.translate("catalog", hint))
            self._preview_layout.addWidget(check)
        if error:
            reason = QLabel(error)
            reason.setWordWrap(True)
            reason.setStyleSheet(
                f"background: transparent; color: {Colors.ERROR}; font-size: {Fonts.SIZE_SM}px;"
            )
            self._preview_layout.addWidget(reason)
        self._preview_box.setVisible(bool(every) or bool(error))

    def _build_fields(self, axes: list[AxisDef]) -> QWidget:
        """Build the written axes: an install folder, an API level."""
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)

        for axis in axes:
            # `values[0]` is the default, written in the field and not
            # left as a watermark: so one sees what will be used.
            default = axis.values[0] if axis.values else ""
            if axis.multiline:
                field = QPlainTextEdit(default)
                # about 4 lines: the typical list fits whole
                field.setFixedHeight(88)
                field.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                field.textChanged.connect(self._refresh_summary)
            else:
                field = QLineEdit(default)
                field.setFixedHeight(30)
                if axis.cast == "int":
                    # An axis declaring `cast='int'` accepts nothing
                    # else: not letting a letter be typed is cheaper
                    # than explaining later why the port returned to
                    # 8000.
                    field.setValidator(QIntValidator(0, 2_147_483_647, field))
                field.textChanged.connect(self._refresh_summary)
            # The watermark repeats the default and nothing else: if the
            # field empties, what shows is what will run. Text
            # explaining what goes in the field would take this same
            # place and read as a value; that goes in the label.
            field.setPlaceholderText(default)
            field.setStyleSheet(self._field_style(axis.multiline))
            self._fields[axis.name] = field
            lay.addLayout(self._labeled(axis.display, field, top=axis.multiline))
        return box

    def _build_multi_axis(self, axis: AxisDef) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)

        lay.addWidget(_SectionLabel(axis.display))

        self._multi_layouts[axis.name] = lay
        self._checks[axis.name] = {}
        for value in axis.values:
            check = QCheckBox(axis.text_of(value))
            check.setChecked(axis.starts_checked(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._checks[axis.name][value] = check
            lay.addWidget(check)
        return box

    def _build_steps(self) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        lay.addWidget(_SectionLabel(QCoreApplication.translate("ParamsPanel", "Pasos")))

        for step in self.steps:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(6)

            check = QCheckBox(step.label)
            check.setChecked(step.default or not step.optional)
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.stateChanged.connect(self._refresh_summary)
            self._step_checks[step.id] = check
            self._step_rows[step.id] = row

            row_lay.addWidget(check)
            row_lay.addStretch()
            lay.addWidget(row)
        return box

    def _build_options(self, axes: list[AxisDef]) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)
        lay.addWidget(_SectionLabel(QCoreApplication.translate("ParamsPanel", "Opciones")))

        for axis in axes:
            row = QVBoxLayout()
            row.setSpacing(4)
            label = QLabel(axis.display)
            label.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: "
                f"{Fonts.SIZE_SM}px;"
            )
            row.addWidget(label)

            # The checkboxes do not hang from `row` but from their own
            # container, because a queried axis draws TWICE: empty while
            # asking, and again with the values that came. Without this
            # container there would be nowhere to put them back, which
            # is why the VPS services axis never appeared.
            holder = QWidget()
            holder.setStyleSheet("background: transparent;")
            hlay = QVBoxLayout(holder)
            hlay.setContentsMargins(0, 0, 0, 0)
            hlay.setSpacing(4)
            self._option_layouts[axis.name] = hlay
            self._fill_options(axis)
            row.addWidget(holder)
            lay.addLayout(row)
        return box

    def _fill_options(self, axis: AxisDef) -> None:
        """Recreate an axis's exclusive options.

        It serves both cases: drawing it the first time, and redoing it
        when the catalog filling it finished answering.
        """
        lay = self._option_layouts.get(axis.name)
        if lay is None:
            return
        for check in self._options.get(axis.name, {}).values():
            lay.removeWidget(check)
            check.deleteLater()
        note = self._empty_notes.pop(axis.name, None)
        if note is not None:
            lay.removeWidget(note)
            note.deleteLater()
        # The old group goes with its buttons: a queried axis refills
        # each time the tab shows, and leaving them stacked is one dead
        # group per click.
        previous = self._option_groups.pop(axis.name, None)
        if previous is not None:
            previous.deleteLater()

        group = QButtonGroup(self)
        group.setExclusive(True)
        self._option_groups[axis.name] = group
        self._options[axis.name] = {}
        # An axis with one exclusive value is not chosen: it shows
        # fixed.
        locked = len(axis.exclusive_values) <= 1 and not axis.combine
        for value in axis.values:
            # `text_of` and not the bare value: an exclusive axis can
            # also have a value that does not read (`0.0.0.0`, the `''`
            # of «all priorities»). The label is of the same class as a
            # long list's, declared in the same place.
            check = QCheckBox(axis.text_of(value))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            if value in axis.danger:
                check.setStyleSheet(f"QCheckBox {{ color: {Colors.ERROR}; }}")
            if value in axis.combine:
                # An independent toggle: outside the group, it starts
                # off.
                check.setChecked(False)
            else:
                group.addButton(check)
                check.setChecked(value == axis.initial)
                if locked:
                    # Only option: shown checked with the selected
                    # color, but it cannot be unchecked: the exclusive
                    # group already prevents releasing the only button,
                    # and there is no other to jump to. It stays
                    # enabled, not gray, so it reads as a live choice,
                    # not a dead one.
                    check.setChecked(True)
                    check.setToolTip(
                        QCoreApplication.translate("ParamsPanel", "Única opción disponible")
                    )
            check.toggled.connect(self._refresh_summary)
            self._options[axis.name][value] = check
            lay.addWidget(check)

        if not axis.values:
            # The same text as an empty long list's watermark: the gap
            # has to say why it is empty, not stay mute.
            note = QLabel(
                QCoreApplication.translate("ParamsPanel", "leyendo el catálogo…")
                if self._loading
                else QCoreApplication.translate("ParamsPanel", "no hay ninguno {0}").format(
                    axis.query_place
                )
            )
            note.setStyleSheet(
                f"background: transparent; color: {Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )
            self._empty_notes[axis.name] = note
            lay.addWidget(note)

    def _field_style(self, multiline: bool) -> str:
        field = theme.FIELD.on(self.pal)
        return f"""
            QLineEdit, QPlainTextEdit {{
                background: {field.bg}; border: 1px solid {field.border};
                border-radius: 5px; padding: {"5px 8px" if multiline else "0 8px"};
                color: {field.fg}; font-size: {Fonts.SIZE_SM}px;
            }}
            QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {field.focus}; }}
        """

    @property
    def _dry_run_axis(self) -> AxisDef | None:
        """Return the exclusive axis that offers a dry run.

        Such as `clean_artifacts`, `sync_common_files` and deleting
        emulators. Its presence makes the Dry run button appear.
        """
        return next((a for a in self.capability.single_axes if "dry_run" in a.values), None)

    def _build_footer(self) -> QWidget:
        foot = QWidget()
        lay = QHBoxLayout(foot)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        # At left, away from Run: emptying the log runs nothing.
        clear_btn = QPushButton(QCoreApplication.translate("ParamsPanel", "Limpiar"))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFixedHeight(34)
        clear_btn.setToolTip(
            QCoreApplication.translate(
                "ParamsPanel", "Vaciar el log de esta pestaña y cerrar sus túneles SSH"
            )
        )
        clear_btn.clicked.connect(self.clear_requested.emit)
        self.clear_btn = clear_btn
        lay.addWidget(clear_btn)
        lay.addStretch()

        # Next to Run: it marks the action being looked at, the other
        # place being the search row's stripe.
        self.fav_star = FavoriteStar(self.pal.accent)
        self.fav_star.set_favorite(favorites.is_favorite(self.capability.id))
        self.fav_star.marked.connect(self._on_star_marked)
        lay.addWidget(self.fav_star, 0, Qt.AlignmentFlag.AlignVCenter)

        self.dry_btn: QPushButton | None = None
        if self._dry_run_axis is not None:
            self.dry_btn = QPushButton(QCoreApplication.translate("ParamsPanel", "Simulacro"))
            self.dry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.dry_btn.setFixedHeight(34)
            self.dry_btn.setToolTip(
                QCoreApplication.translate(
                    "ParamsPanel", "Corre sin tocar nada: solo muestra qué haría"
                )
            )
            self.dry_btn.clicked.connect(lambda: self._emit_execute(dry_run=True))
            lay.addWidget(self.dry_btn)

        self.run_btn = QPushButton(QCoreApplication.translate("ParamsPanel", "Ejecutar"))
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.setFixedHeight(34)
        self.run_btn.clicked.connect(self._emit_execute)

        lay.addWidget(self.run_btn)
        self._restyle_run()
        return foot

    @Slot(bool)
    def _on_star_marked(self, value: bool) -> None:
        favorites.set_favorite(self.capability.id, value)
        self.favorite_changed.emit()

    def refresh_favorite(self) -> None:
        """Catch the star up when another surface marked its action."""
        self.fav_star.set_favorite(favorites.is_favorite(self.capability.id))

    # --- state ---
    def selection(self, axis_name: str) -> list[str]:
        """Return the values checked on an axis."""
        return [v for v, c in self._checks.get(axis_name, {}).items() if c.isChecked()]

    def active_steps(self) -> list[Step]:
        """Return the steps that run: checked, and of this scope."""
        scope = self.option_value("scope")
        return [s for s in self._checked_steps() if s.applies(scope)]

    def _checked_steps(self) -> list[Step]:
        # With one required step the section does not draw: with no
        # checkbox, the step is active by definition.
        """Return the checked steps, whatever the scope.

        They are what is saved: switching to the other scope and back
        keeps the boxes as they were.
        """
        return [
            s
            for s in self.steps
            if s.id not in self._step_checks or self._step_checks[s.id].isChecked()
        ]

    def option_value(self, axis_name: str) -> str:
        """Return an axis's exclusive value."""
        for value, check in self._options.get(axis_name, {}).items():
            if check.isChecked():
                return value
        return ""

    def option_values(self, axis_name: str) -> list[str]:
        """Return an axis's exclusive value and its combined ones."""
        return [v for v, c in self._options.get(axis_name, {}).items() if c.isChecked()]

    def _axis(self, axis_name: str) -> AxisDef | None:
        return next((a for a in self.capability.axes if a.name == axis_name), None)

    def _option_payload(self, axis_name: str) -> list[str] | str:
        """Return a `combine` axis's value as a list, the rest as one.

        It can have two marks at once (`patch` + `build`).
        """
        axis = self._axis(axis_name)
        if axis and axis.combine:
            return self.option_values(axis_name)
        return self.option_value(axis_name)

    def pick_value(self, axis_name: str) -> str:
        """Return the id chosen in a long list (not its label).

        An axis by feature saves the id in no combo: the catalog builds
        it from what is checked in each list, because the id is all the
        tool understands (`AxisDef.value_for`).
        """
        combos = self._facets.get(axis_name)
        if combos is not None:
            axis = self._axis(axis_name)
            if axis is None:
                return ""
            return axis.value_for({n: (c.currentData() or "") for n, c in combos.items()})
        combo = self._picks.get(axis_name)
        if combo is None:
            return ""
        value = combo.currentData()
        return value if isinstance(value, str) else ""

    def _pick_names(self) -> list[str]:
        """Return the axes that save a loose id, in one list or several.

        Both cases travel in the same `picks` bucket.
        """
        return [*self._picks, *self._facets]

    def field_value(self, axis_name: str) -> str:
        """Return the text of a one-line field or a multi-line box.

        Both widgets save the same, text, but do not ask for it with the
        same method, and whoever reads the payload need not know which
        drew.
        """
        field = self._fields.get(axis_name)
        if field is None:
            return ""
        text = field.toPlainText() if isinstance(field, QPlainTextEdit) else field.text()
        return text.strip()

    def state(self) -> dict[str, Any]:
        """Return what is checked right now, in serializable form."""
        return {
            "variants": {name: self.selection(name) for name in self._checks},
            "steps": [s.id for s in self._checked_steps()],
            "options": {name: self._option_payload(name) for name in self._options},
            "fields": {name: self.field_value(name) for name in self._fields},
            "picks": {name: self.pick_value(name) for name in self._pick_names()},
        }

    def apply_state(self, state: dict[str, Any] | None) -> None:
        """Check again what was saved, tolerating a changed catalog.

        Values that no longer exist are ignored and new axes keep their
        default.
        """
        if not state:
            return
        previous, self._restoring = self._restoring, True
        try:
            variants = state.get("variants") or {}
            for axis_name, checks in self._checks.items():
                saved = variants.get(axis_name)
                if saved is None:
                    continue
                for value, check in checks.items():
                    check.setChecked(value in saved)

            steps = state.get("steps")
            if steps is not None:
                for step_id, check in self._step_checks.items():
                    check.setChecked(step_id in steps)

            options = state.get("options") or {}
            for axis_name, checks in self._options.items():
                saved = options.get(axis_name)
                if saved is None:
                    continue
                checked = set(saved) if isinstance(saved, list) else {saved}
                axis = self._axis(axis_name)
                combine = axis.combine if axis else set()
                for value, check in checks.items():
                    if not check.isEnabled():
                        continue  # fixed axis: its mark stays untouched
                    if value in combine:
                        # A save without this value = an unchecked
                        # toggle.
                        check.setChecked(value in checked)
                    elif value in checked:
                        # the exclusive group unchecks the rest
                        check.setChecked(True)

            picks = state.get("picks") or {}
            for axis_name, combo in self._picks.items():
                chosen = picks.get(axis_name)
                if not chosen:
                    continue
                index = combo.findData(chosen)
                # A value that no longer exists (a deleted AVD, an
                # uninstalled image) is not forced: the first of the
                # list stays.
                if index >= 0:
                    combo.setCurrentIndex(index)

            # An axis by feature saves the whole id like those above:
            # restoring it means breaking it down and leaving each list
            # on its part. `resolve_facets` by itself discards those
            # that no longer exist.
            for axis_name, combos in self._facets.items():
                chosen = picks.get(axis_name)
                axis = self._axis(axis_name)
                if not chosen or axis is None:
                    continue
                for name, part in axis.facets_of(chosen).items():
                    combo = combos.get(name)
                    if combo is None:
                        continue
                    index = combo.findData(part)
                    if index < 0:
                        combo.blockSignals(True)
                        combo.addItem(axis.text_of(part), part)
                        index = combo.count() - 1
                        combo.blockSignals(False)
                    combo.setCurrentIndex(index)
                self._fill_facets(axis)

            fields = state.get("fields") or {}
            for axis_name, field in self._fields.items():
                saved = fields.get(axis_name)
                # A saved empty string is a valid choice (it returns to
                # the function's default); a new axis is not.
                if saved is not None:
                    if isinstance(field, QPlainTextEdit):
                        field.setPlainText(saved)
                    else:
                        field.setText(saved)
        finally:
            self._restoring = previous

    def _persist(self) -> None:
        if self._restoring:
            return
        state = self.state()
        # A queried axis without values (still reading, or its source
        # failed) says nothing of what is chosen: what is saved stays.
        # Saving its emptiness erased it, and when values came nothing
        # was restored.
        saved = params_store.load(self.project.path, self.capability.id) or {}
        for axis in self.capability.axes:
            if not (axis.is_queried and not axis.values):
                continue
            for bucket in ("variants", "picks"):
                previous = saved.get(bucket) or {}
                if axis.name in previous:
                    state[bucket][axis.name] = previous[axis.name]
                else:
                    # With nothing saved, the default wins when its
                    # values arrive.
                    state[bucket].pop(axis.name, None)
        params_store.save(self.project.path, self.capability.id, state)
        self.params_changed.emit()

    def payload(self) -> dict[str, Any]:
        """Return what the run needs, grouped by control type."""
        return {
            "capability_id": self.capability.id,
            "project": self.project.name,
            "variants": {name: self.selection(name) for name in self._checks},
            "steps": [s.id for s in self.active_steps()],
            "options": {name: self._option_payload(name) for name in self._options},
            "fields": {name: self.field_value(name) for name in self._fields},
            "picks": {name: self.pick_value(name) for name in self._pick_names()},
            "missing_env": self._missing_keys(),
        }

    def set_env(self, values: dict[str, str]) -> None:
        """Take the settings panel's values, for the check."""
        self._env = values
        self._refresh_summary()

    def set_palette(self, pal: Palette) -> None:
        """Repaint the whole panel when the repo's color changes.

        Not only the Run button. Fields and lists kept the style sheet
        dictated when built, so it has to be dictated again one by one.
        """
        self.pal = pal
        self._restyle()
        self.fav_star.set_accent(pal.accent)

    def _restyle(self) -> None:
        # The panel is the BODY of the «Parámetros» section. The
        # scrollbar paints apart: its groove is not a sheet background
        # but Qt's palette color, and it stayed gray inside a tinted
        # panel. The checks go here, so they reach every one inside.
        check = theme.CHECK.on(self.pal)
        footer = theme.FOOTER.on(self.pal)
        self.setStyleSheet(
            f"ParamsPanel {{ background: {theme.SECTION_BODY.on(self.pal).bg}; }}"
            + check_css(check.bg, check.border)
            + "QCheckBox#previewCheck::indicator:checked:disabled "
            f"{{ background: {check.bg}; border: 1px solid {check.border}; }}"
        )
        self._scroll.setStyleSheet(self._scroll_style())
        self.footer.setStyleSheet(
            f"background: {footer.bg}; border-top: 1px solid {footer.border};"
        )
        for button in (self.clear_btn, self.dry_btn):
            if button is not None:
                button.setStyleSheet(self._secondary_style())
        for field in self._fields.values():
            field.setStyleSheet(self._field_style(isinstance(field, QPlainTextEdit)))
        combos = list(self._picks.values())
        combos += [c for facets in self._facets.values() for c in facets.values()]
        for combo in combos:
            combo.setStyleSheet(self._combo_style())
        self._restyle_run()

    def _secondary_style(self) -> str:
        """Clear and Dry run: outline, not fill.

        The only filled button of the footer is Run.
        """
        button = theme.BUTTON.on(self.pal)
        return f"""
            QPushButton {{
                background: transparent; border: 1px solid {button.border};
                color: {button.fg}; border-radius: 6px;
                padding: 0 16px; font-size: {Fonts.SIZE_SM}px;
            }}
            QPushButton:hover {{ background: {button.hover}; color: {Colors.TEXT}; }}
            QPushButton:disabled {{ color: {Colors.TEXT_MUTED}; }}
        """

    def refresh_run_state(self) -> None:
        """Restore the Run button according to the current blockers.

        Public for whoever disabled the button from outside while truly
        running (`widgets/tab_panel.py::_run_real`) and needs to return
        it to the state it should have, not simply enabled.
        """
        self._refresh_summary()

    def natural_height(self) -> int:
        """Return the height that shows all its content, unscrolled.

        So the `.env` panel keeps the rest of the vertical space.
        """
        return self._content.sizeHint().height() + 4

    def relevant_keys(self) -> set[str]:
        """Return the `.env` keys it may need WITH WHAT IS CHECKED NOW.

        It filters the settings panel. It follows the selection, not the
        whole catalog, in all three sources: the axis, its `uses_env`
        and the steps. Otherwise the form asked for data the run would
        never read: the VPS's IP and key with `Configurar base de datos`
        on `local`.

        It is exactly the set of `_missing_keys`, with `relevant`
        instead of `required`: that is the only difference there should
        be, since what shows and what blocks come from the same
        selection.
        """
        needed = set(relevant_keys_for(self.capability.id))
        for axis in self.capability.axes:
            chosen = self.selection(axis.name) + self.option_values(axis.name)
            needed |= axis.keys_for(chosen)
            for value in chosen:
                needed |= axis.uses_env.get(value, set())
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(relevant_keys_for(step.id))
        return needed

    # --- internal ---

    def _missing_keys(self) -> list[str]:
        """Return the keys without which the action truly cannot run.

        Not only those with no text in the field. A key with a fixed
        default (`ROOT_USER='root'`) or a dynamic one (`DB_USER` from
        the repo's name, resolved by `Config.get`) must not stay amber.
        Wrapping `self._env` in a `Config` asks the same question as at
        run time.
        """
        needed = set(required_keys_for(self.capability.id))
        for axis in self.capability.axes:
            needed |= axis.keys_for(self.selection(axis.name) + self.option_values(axis.name))
        for step in self.active_steps():
            needed |= step.requires_env
            needed |= set(required_keys_for(step.id))
        cfg = envfile.Config(self._env, repo_name=envfile.repo_name_of(self.project.path))
        return sorted(k for k in needed if not cfg.get(k))

    def blockers(self) -> list[str]:
        """Return why it cannot run without opening the tab.

        Public for `quick_run`, which reports it in the console
        (`widgets/tab_panel.py::quick_run`).
        """
        return self._blockers()

    def _blockers(self) -> list[str]:
        """Return the reasons «Ejecutar» cannot run."""
        reasons = []
        # A discovered axis without values is not «you forgot to
        # choose»: the repo does not have that. It says so, and does not
        # also ask to choose from an empty list.
        if self._loading:
            return [QCoreApplication.translate("ParamsPanel", "leyendo el catálogo…")]
        vacios = {a.name for a in self.capability.axes if a.is_discovered and not a.values}
        for axis in self.capability.axes:
            if axis.name not in vacios:
                continue
            if axis.query_error:
                # The camera's three axes fail with the same message:
                # once is enough.
                if axis.query_error not in reasons:
                    reasons.append(axis.query_error)
                continue
            donde = (
                axis.query_place
                if axis.is_queried
                else QCoreApplication.translate("ParamsPanel", "en este repo")
            )
            # An optional axis that also admits being empty (the two
            # lists of «Liberar disco») does not block: having no
            # created AVDs does not prevent deleting an image.
            if axis.allow_empty:
                continue
            reasons.append(
                QCoreApplication.translate("ParamsPanel", "no hay {0} {1}").format(
                    axis.display.lower(), donde
                )
            )
        for axis in self.capability.field_axes:
            if axis.required and not self.field_value(axis.name).strip():
                reasons.append(
                    QCoreApplication.translate("ParamsPanel", "escribe {0}").format(
                        axis.display.lower()
                    )
                )
        for axis in self.capability.pick_axes:
            if axis.values and not axis.allow_empty and not self.pick_value(axis.name):
                reasons.append(
                    QCoreApplication.translate("ParamsPanel", "elige {0}").format(
                        axis.display.lower()
                    )
                )
        for axis in self.capability.multi_axes:
            if axis.name in vacios:
                continue
            if not axis.allow_empty and not self.selection(axis.name):
                reasons.append(
                    QCoreApplication.translate(
                        "ParamsPanel", "selecciona al menos un valor en {0}"
                    ).format(axis.display.lower())
                )
        if not self.active_steps():
            reasons.append(
                QCoreApplication.translate("ParamsPanel", "selecciona al menos un paso")
            )
        missing = self._missing_keys()
        if missing:
            reasons.append(
                QCoreApplication.translate(
                    "ParamsPanel", "faltan claves de configuración: {0}"
                ).format(", ".join(missing))
            )
        return reasons

    @Slot()
    def _refresh_summary(self, *_args) -> None:
        scope = self.option_value("scope")
        for step in self.steps:
            row = self._step_rows.get(step.id)
            if row is not None:
                row.setVisible(step.applies(scope))
        self._persist()
        blockers = self._blockers()
        self.run_btn.setEnabled(not blockers)
        self.run_btn.setToolTip(blockers[0].capitalize() if blockers else "")
        if self.dry_btn is not None:
            self.dry_btn.setEnabled(not blockers)
            self.dry_btn.setToolTip(
                blockers[0].capitalize()
                if blockers
                else QCoreApplication.translate(
                    "ParamsPanel", "Corre sin tocar nada: solo muestra qué haría"
                )
            )
        self._restyle_run()

    def _restyle_run(self) -> None:
        run = (theme.RUN_BUTTON if self.run_btn.isEnabled() else theme.RUN_BUTTON_OFF).on(self.pal)
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: {run.bg};
                color: {run.fg};
                border: none; border-radius: 6px;
                padding: 0 22px;
                font-size: {Fonts.SIZE_SM}px; font-weight: 600;
            }}
            QPushButton:hover {{
                background: {run.bg};
            }}
        """)

    @Slot()
    def _emit_execute(self, *, dry_run: bool = False) -> bool:
        if self._blockers():
            return False
        payload = self.payload()
        if dry_run:
            axis = self._dry_run_axis
            if axis is not None:
                # It does not touch what is saved: it only forces the
                # safe mode in THIS run's payload.
                payload["options"] = {**payload["options"], axis.name: "dry_run"}
        self.execute_requested.emit(payload)
        return True

    def try_run(self) -> bool:
        """Run with the tab's parameters and return whether it ran.

        On opening they are those saved for this button in this repo, or
        the defaults if never touched. The search's ▶ button uses it.
        """
        return self._emit_execute()
