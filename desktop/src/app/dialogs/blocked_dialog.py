"""The notice of a protected target: the action does not run."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app import theme
from app.dialogs.guard_dialog import GuardDialog, join_words
from app.services.projects import Project
from app.services.protection import Target
from app.theme import Colors, Fonts


class BlockedDialog(GuardDialog):
    """The action touches a protected target: report it and do not run.

    It inherits from nothing with an accept button: there is no
    «continue anyway» here.
    """

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
        """Build the notice."""
        which = join_words([t.label for t in targets])
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
        button = theme.FILLED_BUTTON.on(self.pal)
        understood.setStyleSheet(f"""
            QPushButton {{
                background: {button.bg}; color: {button.fg};
                border: 1px solid {button.border}; border-radius: 5px;
                padding: 0 18px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {button.hover}; }}
        """)
        understood.clicked.connect(self.reject)
        buttons.addWidget(understood)
        self._lay.addLayout(buttons)
