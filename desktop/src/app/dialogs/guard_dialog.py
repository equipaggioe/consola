"""The guard's two notices by target type (`services/protection.py`).

Neither asks to type anything: not a word, not the repo's name.

- `BlockedDialog`: a target in the blast radius is protected in this
  repo. The action does NOT run and this dialog has no way to let it
  run: its only button closes. The guard comes off in Settings, Security
  section, once. A guard that can be skipped with the same gesture that
  presses Run is no guard.

- `ReminderDialog`: the action destroys something, but this repo does
  not protect that target. There is nothing to check, only something to
  remember: which repo this is. Cancel and Continue, and Continue is
  never the default, so one Enter too many destroys nothing.

Both catch the same error: pressing the right button in the wrong repo.
So both show the repo's identity in large type, with its color, icon and
full path: what gets taken for granted when one mistakes the tab.
"""

from __future__ import annotations

from typing import override

from PySide6.QtCore import QCoreApplication, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPaintEvent, QPalette
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import palettes, repo_logo
from app.services.projects import Project
from app.theme import Fonts, Radius
from app.widgets.repo_logo_view import RepoLogoView


class GuardDialog(QDialog):
    """Base of both notices: heading, repo card and note."""

    def __init__(
        self,
        project: Project,
        window_title: str,
        heading: str,
        note: str,
        parent: QWidget | None = None,
    ) -> None:
        """Build the heading, the repo card and the note."""
        super().__init__(parent)
        self.project = project
        # The notice belongs to THIS repo: it paints with its palette,
        # like the workspace it comes from.
        self.pal = palettes.get(project.theme)
        self.setWindowTitle(window_title)
        self.setMinimumWidth(460)
        theme.DIALOG.on(self.pal).dress(self)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 20, 22, 18)
        self._lay.setSpacing(14)

        header = QLabel(heading)
        header.setWordWrap(True)
        header.setFont(theme.font(Fonts.SIZE_LG, QFont.Weight.DemiBold))
        self._lay.addWidget(header)

        self._lay.addWidget(self._repo_card())

        footer = QLabel(note)
        footer.setWordWrap(True)
        footer.setFont(theme.font(Fonts.SIZE_XS))
        theme.HINT.on(self.pal).dress(footer)
        self._lay.addWidget(footer)

    def _repo_card(self) -> QWidget:
        box = _RepoCard()
        theme.REPO_CARD.on(self.pal).dress(box, fill=False)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)

        name = QLabel(self.project.name)
        name.setFont(theme.font(Fonts.SIZE_LG, QFont.Weight.Bold))
        path = QLabel(self.project.path)
        path.setFont(theme.font(Fonts.SIZE_XS))
        theme.HINT.on(self.pal).dress(path)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(RepoLogoView(18, repo_logo.resolve(self.project.path)))
        row.addWidget(name, 1)
        lay.addLayout(row)
        lay.addWidget(path)
        return box

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(28)
        button.setFont(theme.font(Fonts.SIZE_XS))
        return button


class _RepoCard(QFrame):
    """The repo's plate: its background, with a stripe on the left.

    The stripe is the part's outline, Dark in its palette.
    """

    STRIPE = 3

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        colors = self.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(colors.color(QPalette.ColorRole.Dark))
        p.drawRoundedRect(QRectF(self.rect()), Radius.SM, Radius.SM)
        p.setBrush(colors.color(QPalette.ColorRole.Window))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(self.STRIPE, 0, 0, 0), Radius.SM, Radius.SM)
        p.end()


def join_words(things: list[str]) -> str:
    """Join the names as a list reads: «a, b y c»."""
    if len(things) <= 1:
        return things[0] if things else QCoreApplication.translate("guard_dialog", "algo")
    return QCoreApplication.translate("guard_dialog", "{0} y {1}").format(
        ", ".join(things[:-1]), things[-1]
    )
