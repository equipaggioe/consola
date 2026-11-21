"""The notice of a protected target: the action does not run."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app import theme
from app.dialogs.guard_dialog import GuardDialog, join_words
from app.services.projects import Project
from app.services.protection import Target
from app.theme import Fonts


class BlockedDialog(GuardDialog):
    """The action touches a protected target: report it and do not run.

    It inherits from nothing with an accept button: there is no
    «continue anyway» here.
    """

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
        """Build the notice."""
        which = join_words([QCoreApplication.translate("protection", t.label) for t in targets])
        super().__init__(
            project,
            QCoreApplication.translate("BlockedDialog", "Accion bloqueada"),
            QCoreApplication.translate(
                "BlockedDialog", "{0} toca {1}, y este repositorio lo tiene protegido."
            ).format(action, which),
            QCoreApplication.translate(
                "BlockedDialog",
                "El seguro se quita en Configuracion, seccion Seguridad: por tipo de "
                "objetivo y solo para este repositorio.",
            ),
            parent,
        )

        reasons = QLabel(
            "\n".join(
                f"•  {QCoreApplication.translate('protection', t.setting_label)} — "
                f"{QCoreApplication.translate('protection', t.why)}"
                for t in targets
            )
        )
        reasons.setWordWrap(True)
        reasons.setFont(theme.font(Fonts.SIZE_XS))
        theme.HINT.on(self.pal).dress(reasons)
        self._lay.insertWidget(2, reasons)

        buttons = QHBoxLayout()
        buttons.addStretch()
        understood = self._button(QCoreApplication.translate("BlockedDialog", "Entendido"))
        understood.setDefault(True)
        theme.FILLED_BUTTON.on(self.pal).dress(understood, fill=False)
        understood.clicked.connect(self.reject)
        buttons.addWidget(understood)
        self._lay.addLayout(buttons)
