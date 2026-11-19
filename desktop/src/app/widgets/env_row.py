"""One key of the configuration: its label, its field and its state."""

from __future__ import annotations

from typing import override

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from app import theme
from app.services import envfile
from app.services.palettes import Palette
from app.services.settings import Setting
from app.theme import Colors, Fonts


def _to_lines(value: str) -> str:
    """Return what is saved (commas) as it edits (a line per entry)."""
    return "\n".join(envfile.split_list(value or ""))


# Height of the multi-line field, in lines. It starts at three empty,
# since a list of paths tends to have two or three, and grows with what
# is written up to five; from there it scrolls.
LIST_MIN_ROWS = 3
LIST_MAX_ROWS = 5


class _ClickToSelectLabel(QLabel):
    """A label that on a click focuses its field and selects its text.

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
        # The label names the field for assistive technology.
        self.label.setBuddy(self.field)
        self.label.setFixedWidth(label_width)
        self.label.setToolTip(setting.key)
        self.label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_LABEL}; font-size: {Fonts.SIZE_SM}px;"
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
    @Slot(str)
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
        """Fit the field's height to its text, plus one empty line.

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
        field = theme.FIELD.on(self.pal)
        border = field.border if self.value() else theme.FIELD_EMPTY.on(self.pal).border
        widget = "QPlainTextEdit" if self._is_list else "QLineEdit"
        self.field.setStyleSheet(f"""
            {widget} {{
                background: {field.bg};
                color: {field.fg};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 5px 8px;
                font-size: {Fonts.SIZE_SM}px;
            }}
            {widget}:focus {{ border: 1px solid {field.focus}; }}
        """)
