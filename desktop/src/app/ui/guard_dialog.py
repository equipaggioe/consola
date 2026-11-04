"""The guard's two notices by target type (`core/protection.py`).

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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.projects import Project
from app.core.protection import Target
from app.theme import Colors, Fonts
from app.ui import palettes, repo_logo


class _GuardDialog(QDialog):
    """Base of both notices: heading, repo card and note."""

    def __init__(
        self,
        project: Project,
        window_title: str,
        heading: str,
        note: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        # The notice belongs to THIS repo: it paints with its palette,
        # like the workspace it comes from.
        self.pal = palettes.get(project.theme)
        self.setWindowTitle(window_title)
        self.setMinimumWidth(460)
        self.setStyleSheet(f"QDialog {{ background: {self.pal.panel}; }}")

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(22, 20, 22, 18)
        self._lay.setSpacing(14)

        header = QLabel(heading)
        header.setWordWrap(True)
        header.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 600;"
        )
        self._lay.addWidget(header)

        self._lay.addWidget(self._repo_card())

        footer = QLabel(note)
        footer.setWordWrap(True)
        footer.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        self._lay.addWidget(footer)

    def _repo_card(self) -> QWidget:
        box = QWidget()
        box.setStyleSheet(
            f"background: {self.pal.surface_alt}; border-left: 3px solid "
            f"{self.pal.accent}; border-radius: 4px;"
        )
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)

        name = QLabel(self.project.name)
        name.setStyleSheet(
            f"background: transparent; color: {self.pal.accent}; "
            f"font-size: {Fonts.SIZE_LG}px; font-weight: 700;"
        )
        path = QLabel(self.project.path)
        path.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(repo_logo.RepoLogoView(18, repo_logo.resolve(self.project.path)))
        row.addWidget(name, 1)
        lay.addLayout(row)
        lay.addWidget(path)
        return box

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(32)
        return button


class BlockedDialog(_GuardDialog):
    """The action touches a protected target: report it and do not run.

    It inherits from nothing with an accept button: there is no
    «continue anyway» here.
    """

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
        """Build the notice."""
        which = _join_words([t.label for t in targets])
        super().__init__(
            project,
            "Accion bloqueada",
            f"{action} toca {which}, y este repositorio lo tiene protegido.",
            "El seguro se quita en Configuracion, seccion Seguridad: por tipo "
            "de objetivo y solo para este repositorio.",
            parent,
        )

        reasons = QLabel("\n".join(f"•  {t.setting_label} — {t.why}" for t in targets))
        reasons.setWordWrap(True)
        reasons.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        self._lay.insertWidget(2, reasons)

        buttons = QHBoxLayout()
        buttons.addStretch()
        understood = self._button("Entendido")
        understood.setDefault(True)
        understood.setStyleSheet(f"""
            QPushButton {{
                background: {self.pal.surface_alt}; color: {Colors.TEXT};
                border: 1px solid {Colors.BORDER}; border-radius: 5px;
                padding: 0 18px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {self.pal.surface_hover}; }}
        """)
        understood.clicked.connect(self.reject)
        buttons.addWidget(understood)
        self._lay.addLayout(buttons)


class ReminderDialog(_GuardDialog):
    """The action destroys something unprotected: a repo reminder."""

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
        """Build the notice."""
        which = _join_words([t.label for t in targets])
        super().__init__(
            project,
            "Confirmar accion",
            f"{action} va a destruir {which}.",
            "Este objetivo no esta protegido en este repositorio. Se protege "
            "en Configuracion, seccion Seguridad.",
            parent,
        )

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = self._button("Cancelar")
        cancel.setDefault(True)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {Colors.BORDER};
                color: {Colors.TEXT_DIM}; border-radius: 5px; padding: 0 16px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {self.pal.surface_hover}; color: {Colors.TEXT}; }}
        """)
        cancel.clicked.connect(self.reject)

        proceed = self._button("Continuar")
        # Never the default button: one Enter too many destroys nothing.
        proceed.setAutoDefault(False)
        proceed.setDefault(False)
        proceed.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.ERROR}; color: {Colors.BG};
                border: none; border-radius: 5px; padding: 0 18px;
                font-size: {Fonts.SIZE_XS}px; font-weight: 600;
            }}
        """)
        proceed.clicked.connect(self.accept)

        buttons.addWidget(cancel)
        buttons.addWidget(proceed)
        self._lay.addLayout(buttons)


def _join_words(things: list[str]) -> str:
    if len(things) <= 1:
        return things[0] if things else "algo"
    return ", ".join(things[:-1]) + " y " + things[-1]
