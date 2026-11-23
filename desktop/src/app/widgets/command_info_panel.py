"""The long description of the open action."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app import theme
from app.services import command_docs
from app.services.palettes import NEUTRAL, Palette
from app.services.registry import Capability
from app.theme import Colors, Fonts


class _Heading(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text.upper(), parent)
        self.setFont(theme.caption())


class CommandInfoPanel(QWidget):
    """The open action's long description and the steps it runs.

    It lives in the top section of the right accordion. That section's
    header carries the action's name, set by `TabPanel`, so collapsed it
    still says which one it is. The text comes from
    `services/command_docs.py` when it exists, and otherwise from the
    capability's one-line description plus its steps' labels.

    Only what the button does and in which order: the sheet has no
    section of warnings or edge cases.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the scrollable column."""
        super().__init__(parent)
        # Without this, a QWidget subclass ignores its own sheet's
        # background and shows the global sheet's gray (`theme.py`): the
        # section's body did not take the repo's color.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.pal = NEUTRAL

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._content = QWidget()
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.setSpacing(10)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        root.addWidget(self._content)

        self._restyle()
        self.set_capability(None)

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        # Everything in it is a hint: the text takes the body's palette
        # with the hint's color.
        theme.SECTION_BODY.on(self.pal).dress(self)
        theme.ink(self, Colors.ON_SURFACE_VARIANT)

    # --- API ---
    def set_capability(self, capability: Capability | None) -> None:
        """Show the description of that capability, or nothing."""
        self._clear()
        if capability is None:
            self._lay.addWidget(
                self._muted(
                    QCoreApplication.translate(
                        "CommandInfoPanel",
                        "Abre una acción para ver de qué se trata y qué pasos ejecuta.",
                    )
                )
            )
            return

        doc = command_docs.get(capability.id)
        summary = (
            doc.summary
            if doc
            else (
                capability.description
                or QCoreApplication.translate(
                    "CommandInfoPanel", "Esta acción todavía no tiene una descripción larga."
                )
            )
        )
        self._lay.addWidget(self._body(summary))

        steps = doc.steps if doc else [s.label for s in capability.steps]
        if steps:
            self._lay.addWidget(_Heading(QCoreApplication.translate("CommandInfoPanel", "Pasos")))
            for i, text in enumerate(steps, 1):
                self._lay.addWidget(self._step(i, text))

    # --- internal ---
    def _clear(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()

    def _body(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(theme.font(Fonts.SIZE_SM))
        return label

    def _muted(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(theme.font(Fonts.SIZE_XS))
        return label

    def _step(self, number: int, text: str) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        badge = QLabel(str(number))
        badge.setFixedWidth(16)
        badge.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        badge.setFont(theme.font(Fonts.SIZE_XS, QFont.Weight.Bold))

        body = QLabel(text)
        body.setWordWrap(True)
        body.setFont(theme.font(Fonts.SIZE_XS))

        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(body, 1)
        return row
