from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.projects import Project
from app.core.protection import Target
from app.theme import Colors, Fonts
from app.ui import palettes, repo_logo

"""
Los dos avisos del seguro por tipo de objetivo (`core/protection.py`). Ninguno
pide escribir nada: ni una palabra, ni el nombre del repo.

- `BlockedDialog` — un objetivo del radio de dano esta protegido en este repo.
  La accion NO corre y este dialogo no tiene forma de dejarla correr: su unico
  boton cierra. El seguro se quita en Configuracion, seccion Seguridad, una vez.
  Un seguro que se puede saltar en el mismo gesto con el que se aprieta Ejecutar
  no es un seguro.

- `ReminderDialog` — la accion destruye algo pero este repo no protege ese
  objetivo. No hay nada que comprobar, solo algo que recordar: sobre que repo se
  esta trabajando. Cancelar y Continuar, y Continuar nunca es el predeterminado
  —un Enter de mas no destruye nada—.

El error que los dos atajan es el mismo: apretar el boton correcto en el repo
equivocado. Por eso los dos muestran la identidad del repo en grande, con su
color, su icono y su ruta completa — el dato que se da por sabido cuando uno se
confunde de pestana.
"""


class _GuardDialog(QDialog):
    """Base de los dos avisos: el encabezado, la tarjeta del repo y la nota."""

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
        # El aviso es de ESTE repo: se pinta con su paleta, como el espacio de
        # trabajo del que sale.
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
    """La accion toca un objetivo protegido: se informa y no corre.

    No hereda de nadie que tenga boton de aceptar: aca no hay 'continuar igual'.
    """

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
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
    """La accion destruye algo no protegido: recordatorio del repo, sin mas."""

    def __init__(
        self, project: Project, action: str, targets: list[Target], parent: QWidget | None = None
    ) -> None:
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
        # Nunca es el boton por defecto: un Enter de mas no destruye nada.
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
