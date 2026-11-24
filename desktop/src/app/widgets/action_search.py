"""The menu bar's action search."""

from __future__ import annotations

from typing import cast, override

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QRect, Qt, Signal, Slot
from PySide6.QtGui import QAction, QFont, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import favorites
from app.services.palettes import NEUTRAL, Palette
from app.services.registry import registry
from app.theme import Colors, Fonts, Spacing
from app.widgets.action_row import ActionRow


class ActionSearch(QWidget):
    """The menu bar search: typing lists the matching actions below.

    They show in `ActionRow` rows, with the favorite stripe, level marks
    and ▶ to run at once.

    It searches ALL actions even with «only favorites» on: searching
    goes after something specific, and hiding what is being searched for
    because it is not marked would be a cruel joke. Opening emits the
    same signal as the menu, so `MainWindow` cannot tell where the click
    came from.

    Keyboard: arrows to move, Enter opens the tab, Ctrl+Enter runs it if
    ready, Esc closes.
    """

    action_requested = Signal(str)
    run_requested = Signal(str)
    favorites_changed = Signal(set)

    WIDTH = 240
    # that of a «Configuración del repo» field (`widgets/env_panel.py`)
    FIELD_HEIGHT = 24
    POPUP_WIDTH = 440
    POPUP_MAX_HEIGHT = 460

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the field; the list builds on first use."""
        super().__init__(parent)
        self.pal = NEUTRAL
        self._ready: set[str] = set()
        # What makes sense in the open repo. Search does show what is
        # not marked favorite (see the docstring), but not what this
        # repo cannot do: that is not hiding something that exists but
        # not offering a button that could only fail.
        self._applicable: set[str] | None = None
        self._current = -1

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(0)

        self.box = QLineEdit()
        self.box.setPlaceholderText(QCoreApplication.translate("ActionSearch", "Buscar acciones…"))
        self.box.setAccessibleName(QCoreApplication.translate("ActionSearch", "Buscar acciones"))
        self.box.setClearButtonEnabled(True)
        # Qt's clear action has no text, so its button reaches
        # assistive technology with no name. The object name is Qt's.
        clear = self.box.findChild(QAction, "_q_qlineeditclearaction")
        if clear is None:
            raise RuntimeError("QLineEdit has no clear action")
        clear.setText(QCoreApplication.translate("ActionSearch", "Borrar el texto"))
        self.box.setFixedWidth(self.WIDTH)
        # The same height as a «Configuración del repo» field
        # (`widgets/env_panel.py`): it is a text field like the others,
        # in the same window.
        self.box.setFixedHeight(self.FIELD_HEIGHT)
        self.box.textChanged.connect(self._on_text)
        self.box.installEventFilter(self)
        lay.addWidget(self.box)
        self._restyle_box()

        self._popup: QFrame | None = None
        self._rows: list[ActionRow] = []
        self._headers: list[tuple[QLabel, list[ActionRow]]] = []

    # --- state that comes from the window ---
    def set_palette(self, pal: Palette) -> None:
        """Repaint the field like a «Configuración del repo» field.

        Same border, height, radius, type size and focus
        (`widgets/env_panel.py`); the background is the repo's color and
        not the other fields' gray (`theme.SEARCH_FIELD`).
        """
        self.pal = pal
        self._restyle_box()
        self._restyle_popup()
        for row in self._rows:
            row.set_accent(pal.accent)

    def set_ready(self, ready: set[str]) -> None:
        """Set which actions can run at once."""
        self._ready = set(ready)
        for row in self._rows:
            row.set_ready(row.capability_id in self._ready)

    def set_favorites(self, ids: set[str]) -> None:
        """Set which actions are favorites."""
        for row in self._rows:
            row.set_favorite(row.capability_id in ids)

    def set_applicable(self, ids: set[str]) -> None:
        """Set which actions make sense in the open repo.

        They come from `services/catalog.py::applicable_ids`, and apply
        when filtering, along with the typed text.
        """
        self._applicable = set(ids)
        if self.box.text().strip():
            self._on_text(self.box.text())

    def set_project_active(self, active: bool) -> None:
        """With no repo in tabs there is nothing to run on.

        Like the group menus, the search turns off.
        """
        self.box.setEnabled(active)
        if not active:
            self.box.clear()

    def _restyle_box(self) -> None:
        theme.SEARCH_FIELD.on(self.pal).dress(self.box, fill=False)
        self.box.setFont(theme.font(Fonts.SIZE_SM))
        self.box.setTextMargins(Spacing.XS, 0, Spacing.XS, 0)

    def _restyle_popup(self) -> None:
        """Repaint the list when the repo changes.

        It builds only once and survives repo changes: painting it at
        birth is not enough.
        """
        if self._popup is not None:
            # Like a group menu's (`widgets/action_menu_bar.py`): the
            # list hangs from the menu row.
            theme.SEARCH_LIST.on(self.pal).dress(self._popup)

    # --- popup ---
    def _build_popup(self) -> QFrame:
        """Build the list once, with every action.

        A child of the window and not a `Qt.Popup` window: a real popup
        takes keyboard focus, and typing has to go on with the list
        open. The search only changes which rows show.
        """
        popup = QFrame(self.window())
        popup.setCursor(Qt.CursorShape.ArrowCursor)
        popup.setFrameShape(QFrame.Shape.StyledPanel)
        theme.SEARCH_LIST.on(self.pal).dress(popup)
        outer = QVBoxLayout(popup)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        theme.focus_frame(self._scroll)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(6, 6, 6, 6)
        self._content_layout.setSpacing(0)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        marked = favorites.favorite_ids()
        for group, capabilities in registry.get_groups().items():
            # The group is a key: the catalog declares it untranslated.
            title = QCoreApplication.translate("catalog", group).upper()
            header = QLabel(f"{registry.get_group_icon(group)}  {title}".strip())
            header.setFont(theme.font(Fonts.SIZE_XS, QFont.Weight.Bold))
            header.setContentsMargins(Spacing.SM + 2, Spacing.SM, Spacing.SM + 2, 3)
            theme.ink(header, Colors.ON_SURFACE_VARIANT)
            self._content_layout.addWidget(header)
            rows = []
            for cap in capabilities:
                row = ActionRow(
                    cap.id,
                    cap.name,
                    cap.icon,
                    danger=cap.kind == "destructive",
                    accent=self.pal.accent,
                    favorite=cap.id in marked,
                    composite=cap.is_composite,
                    description=cap.description,
                    machine=cap.is_machine_wide,
                )
                row.set_ready(cap.id in self._ready)
                row.triggered.connect(self._open)
                row.run_requested.connect(self._run)
                row.favorite_toggled.connect(self._on_favorite_toggled)
                self._content_layout.addWidget(row)
                rows.append(row)
            self._headers.append((header, rows))
            self._rows.extend(rows)

        self._empty = QLabel(QCoreApplication.translate("ActionSearch", "Sin resultados"))
        self._empty.setFont(theme.font(Fonts.SIZE_SM))
        self._empty.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        theme.ink(self._empty, Colors.ON_SURFACE_VARIANT)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content_layout.addWidget(self._empty)

        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)
        popup.hide()
        return popup

    def _visible_rows(self) -> list[ActionRow]:
        return [row for row in self._rows if not row.isHidden()]

    @Slot(str)
    def _on_text(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            self._hide_popup()
            return
        if self._popup is None:
            self._popup = self._build_popup()

        hits = 0
        for header, rows in self._headers:
            group_hits = 0
            for row in rows:
                match = row.matches(needle) and (
                    self._applicable is None or row.capability_id in self._applicable
                )
                row.setVisible(match)
                group_hits += int(match)
            header.setVisible(group_hits > 0)
            hits += group_hits
        self._empty.setVisible(hits == 0)
        self._set_current(0 if hits else -1)
        self._show_popup()

    def _show_popup(self) -> None:
        popup = self._popup
        assert popup is not None
        window = self.window()
        # Right-aligned with the field: the search lives near the row's
        # right edge, and the list is wider than the field.
        anchor = self.box.mapTo(window, QPoint(self.box.width(), self.box.height() + 4))
        width = max(self.POPUP_WIDTH, self.box.width())
        x = max(4, anchor.x() - width)
        self._content_layout.activate()
        content = self._scroll.widget()
        assert content is not None
        wanted = content.sizeHint().height() + 2
        room = window.height() - anchor.y() - 12
        height = max(60, min(wanted, self.POPUP_MAX_HEIGHT, room))
        popup.setGeometry(x, anchor.y(), width, height)
        if not popup.isVisible():
            popup.show()
            app = QApplication.instance()
            assert app is not None
            app.installEventFilter(self)
        popup.raise_()

    def _hide_popup(self) -> None:
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()
            app = QApplication.instance()
            assert app is not None
            app.removeEventFilter(self)
        self._set_current(-1)

    # --- keyboard selection ---
    def _set_current(self, index: int) -> None:
        visible = self._visible_rows()
        for row in self._rows:
            row.set_highlighted(False)
        self._current = index if 0 <= index < len(visible) else -1
        if self._current >= 0:
            row = visible[self._current]
            row.set_highlighted(True)
            self._scroll.ensureWidgetVisible(row, 0, 24)

    def _current_row(self) -> ActionRow | None:
        visible = self._visible_rows()
        return visible[self._current] if 0 <= self._current < len(visible) else None

    # --- firing ---
    @Slot(str)
    def _open(self, cap_id: str) -> None:
        self.box.clear()
        self.action_requested.emit(cap_id)

    @Slot(str)
    def _run(self, cap_id: str) -> None:
        self.box.clear()
        self.run_requested.emit(cap_id)

    @Slot(str, bool)
    def _on_favorite_toggled(self, cap_id: str, value: bool) -> None:
        """Save the mark from the list and tell the other surfaces.

        Marking from the list does not close it.
        """
        self.favorites_changed.emit(favorites.set_favorite(cap_id, value))

    # --- events ---
    @override
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        kind = event.type()
        if obj is self.box and kind == QEvent.Type.FocusIn and self.box.text().strip():
            # It closed with a click outside but the text stayed:
            # returning to the field reopens the list as it was.
            self._on_text(self.box.text())
        elif obj is self.box and kind == QEvent.Type.ShortcutOverride:
            key = cast(QKeyEvent, event).key()
            popup_open = self._popup is not None and self._popup.isVisible()
            if popup_open and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                # With the list open, Ctrl+Enter is the list's: it runs
                # the highlighted row, and the window's shortcut, which
                # runs the active tab, does not take it.
                event.accept()
                return True
        elif obj is self.box and kind == QEvent.Type.KeyPress:
            popup_open = self._popup is not None and self._popup.isVisible()
            key = cast(QKeyEvent, event).key()
            if key == Qt.Key.Key_Escape:
                self.box.clear()
                return True
            if popup_open and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                count = len(self._visible_rows())
                if count:
                    step = 1 if key == Qt.Key.Key_Down else -1
                    self._set_current((self._current + step) % count)
                return True
            if popup_open and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self._current_row()
                if row is not None:
                    ctrl = cast(QKeyEvent, event).modifiers() & Qt.KeyboardModifier.ControlModifier
                    if ctrl and row.capability_id in self._ready:
                        self._run(row.capability_id)
                    else:
                        self._open(row.capability_id)
                return True
        elif kind == QEvent.Type.MouseButtonPress and self._popup is not None:
            # A click outside the field and the list closes it, without
            # eating the click.
            pos = cast(QMouseEvent, event).globalPosition().toPoint()
            popup_rect = QRect(self._popup.mapToGlobal(QPoint(0, 0)), self._popup.size())
            box_rect = QRect(self.box.mapToGlobal(QPoint(0, 0)), self.box.size())
            if not popup_rect.contains(pos) and not box_rect.contains(pos):
                self._hide_popup()
        elif kind == QEvent.Type.WindowDeactivate and obj is self.window():
            self._hide_popup()
        return super().eventFilter(obj, event)
