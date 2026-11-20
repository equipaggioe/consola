"""The notice of an action that destroys an unprotected target."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QWidget

from app import theme
from app.dialogs.guard_dialog import GuardDialog, join_words
from app.services.projects import Project
from app.services.protection import Target
from app.theme import Colors, Fonts


class ReminderDialog(GuardDialog):
    """The action destroys something unprotected: a repo reminder."""

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
        """Build the notice."""
        which = join_words([QCoreApplication.translate("protection", t.label) for t in targets])
        super().__init__(
            project,
            QCoreApplication.translate("ReminderDialog", "Confirmar accion"),
            QCoreApplication.translate("ReminderDialog", "{0} va a destruir {1}.").format(
                action, which
            ),
            QCoreApplication.translate(
                "ReminderDialog",
                "Este objetivo no esta protegido en este repositorio. Se protege en "
                "Configuracion, seccion Seguridad.",
            ),
            parent,
        )

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = self._button(QCoreApplication.translate("ReminderDialog", "Cancelar"))
        cancel.setDefault(True)
        button = theme.BUTTON.on(self.pal)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {button.border};
                color: {button.fg}; border-radius: 5px; padding: 0 16px;
                font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {button.hover}; color: {Colors.TEXT}; }}
        """)
        cancel.clicked.connect(self.reject)

        proceed = self._button(QCoreApplication.translate("ReminderDialog", "Continuar"))
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
