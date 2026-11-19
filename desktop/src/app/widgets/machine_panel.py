"""The keys of this machine (`Setting.scope='machine'`).

The only place they edit: the repo's form leaves them out. This section
shows all of them and saves them where they live, QSettings
(`services/params_store.py::machine_env`). It starts hidden: it shows
from the Ver menu (`services/section_visibility.py`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import theme
from app.services import params_store
from app.services.palettes import Palette
from app.services.settings import machine_settings
from app.theme import Fonts
from app.widgets.env_row import EnvRow


class MachinePanel(QWidget):
    """The form of the machine keys, with Reload and Save."""

    saved = Signal()

    def __init__(self, pal: Palette, label_width: int, parent: QWidget | None = None) -> None:
        """Build one row per machine key and the footer."""
        super().__init__(parent)
        self.pal = pal
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        body = QVBoxLayout(self._body)
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(6)
        self.rows = {
            s.key: EnvRow(s, "", pal, label_width=label_width) for s in machine_settings()
        }
        for row in self.rows.values():
            body.addWidget(row)
        # In a scroll, like the repo's form: a short section scrolls the
        # rows instead of squeezing them and the footer.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        self.footer = QWidget()
        # Its natural height always (`setFixedHeight` below, once the
        # buttons are in): the section's height goes to the scroll
        # above. A Fixed size policy alone was not enough, the layout
        # still squeezed the buttons.
        bar = QHBoxLayout(self.footer)
        bar.setContentsMargins(16, 8, 16, 8)
        bar.setSpacing(8)
        bar.addStretch(1)
        self.reload_btn = QPushButton("Recargar")
        self.reload_btn.setToolTip("Descarta los cambios sin guardar")
        self.reload_btn.clicked.connect(self.reload)
        self.save_btn = QPushButton("Guardar")
        self.save_btn.setToolTip("Guarda las claves de esta máquina, para todos los repos")
        self.save_btn.clicked.connect(self.save)
        for button in (self.reload_btn, self.save_btn):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(button)
        root.addWidget(self.footer)
        self.footer.setFixedHeight(self.footer.sizeHint().height())

        self._restyle()
        self.reload()

    @Slot()
    def reload(self) -> None:
        """Read the saved values into the form."""
        values = params_store.machine_env()
        for key, row in self.rows.items():
            row.blockSignals(True)
            row.set_value(values.get(key, ""))
            row.blockSignals(False)

    @Slot()
    def save(self) -> None:
        """Write the form's values to QSettings."""
        params_store.save_machine_env({key: row.value() for key, row in self.rows.items()})
        self.saved.emit()

    def content_height(self) -> int:
        """Return the height of the rows and the footer."""
        return self._body.sizeHint().height() + self.footer.sizeHint().height()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        for row in self.rows.values():
            row.set_palette(pal)
        self._restyle()

    def _restyle(self) -> None:
        """Paint it like «Configuración del repo».

        The body is `panel` and the footer `surface`.
        """
        body = theme.SECTION_BODY.on(self.pal)
        footer = theme.FOOTER.on(self.pal)
        button = theme.ACCENT_BUTTON.on(self.pal)
        self.setStyleSheet(f"MachinePanel {{ background: {body.bg}; }}")
        # The same as `EnvPanel._scroll_style`: the viewport shows the
        # panel's background, and the bar's groove gets it by hand.
        self._scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {body.bg}; width: 8px; }}"
        )
        self.footer.setStyleSheet(
            f"background: {footer.bg}; border-top: 1px solid {footer.border};"
        )
        button_css = f"""
            QPushButton {{
                background: transparent; border: 1px solid {button.border};
                color: {button.fg}; border-radius: 5px;
                padding: 4px 12px; font-size: {Fonts.SIZE_XS}px;
            }}
            QPushButton:hover {{ background: {button.hover}; }}
        """
        for button in (self.reload_btn, self.save_btn):
            button.setStyleSheet(button_css)
