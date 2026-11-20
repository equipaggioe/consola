"""The repo's guards: one checkbox per target type.

See `services/protection.py`.

**They do not live in `config.env`.** That file holds the data tasks
need to work: the VPS's IP, the user, the token, the paths. No step ever
reads a guard: the console looks at them before letting something run
(`TabPanel._guard`). They belong with the steps left checked in an
action's panel, so they go to the same file, `.consola/params.json`
(`services/params_store.py`).

Another file has a visible consequence: there is no Save button here.
Touching a checkbox saves it, as in the parameters panel. The Save
button of Settings only rules `config.env`, and a section depending on
another's button is what made it look like guards were not being saved.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QCoreApplication, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QScrollArea, QVBoxLayout, QWidget

from app import theme
from app.services import params_store, protection
from app.services.palettes import NEUTRAL, Palette
from app.services.projects import Project
from app.theme import check_css


class SecurityPanel(QWidget):
    """The «Seguridad» section of the right panel.

    It emits `changed` with the whole state ({target_id: bool}) for the
    header's summary and the status bar indicator, which read what is on
    screen and not what stayed on disk.
    """

    changed = Signal(dict)

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        """Build one checkbox per target, with its saved state."""
        super().__init__(parent)
        self.project = project
        self._state = params_store.load_protection(project.path)
        self._checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Five fixed checkboxes, and still inside a scroll: the
        # accordion section drags by hand and without it, shrinking too
        # much crushed the checkboxes instead of cropping them.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll = scroll  # `_restyle` repaints it

        self._body = QWidget()
        self.pal = NEUTRAL
        self._restyle()
        lay = QVBoxLayout(self._body)
        lay.setContentsMargins(16, 10, 16, 12)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        for target in protection.TARGETS:
            # The explanation lives in the tooltip, not in text
            # alongside: the checkbox's label already says what it
            # protects.
            check = QCheckBox(QCoreApplication.translate("protection", target.setting_label))
            check.setCursor(Qt.CursorShape.PointingHandCursor)
            check.setChecked(self._state[target.id])
            check.setToolTip(QCoreApplication.translate("protection", target.why))

            def on_toggled(checked: bool, tid: str = target.id) -> None:
                self._toggle(tid, checked)

            check.toggled.connect(on_toggled)
            self._checks[target.id] = check
            lay.addWidget(check)

        scroll.setWidget(self._body)
        root.addWidget(scroll)

    def _scroll_style(self) -> str:
        """Leave the scroll with no background, showing the panel's.

        The bar's groove does need one. It falls under the same
        `QScrollArea > QWidget > QWidget` that makes the viewport
        transparent, since the bar is a child of the viewport, and
        transparent painted Qt's palette gray instead of the panel's
        background: a gray stripe at the edge of a tinted column. It
        gets its color by hand in this same sheet, which is the closest
        and the one that wins.
        """
        body = theme.SECTION_BODY.on(self.pal)
        check = theme.CHECK.on(self.pal)
        return (
            "QScrollArea, QScrollArea > QWidget > QWidget "
            "{ border: none; background: transparent; }"
            f"QScrollBar:vertical {{ background: {body.bg}; width: 8px; }}"
            + check_css(check.bg, check.border)
        )

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()

    def _restyle(self) -> None:
        self._body.setStyleSheet(f"background: {theme.SECTION_BODY.on(self.pal).bg};")
        self._scroll.setStyleSheet(self._scroll_style())

    def state(self) -> dict[str, Any]:
        """Return what is shown: what `TabPanel._guard` applies."""
        return dict(self._state)

    def content_height(self) -> int:
        """Return the height the checkboxes ask for without scrolling.

        `TabPanel._relayout_right` uses it to decide how much to give
        the section. It asks the body and not the scroll, which has no
        height of its own.
        """
        return self._body.sizeHint().height()

    def _toggle(self, target_id: str, checked: bool) -> None:
        self._state[target_id] = bool(checked)
        params_store.save_protection(self.project.path, self._state)
        self.changed.emit(self.state())
