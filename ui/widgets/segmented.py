from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, Signal

from ..theme import Colors, Fonts


class Segmented(QWidget):
    """Control segmentado para ejes de seleccion unica (`select='one'`).

    Pedir dos valores a la vez seria un absurdo (start + stop), asi que el
    control impide expresarlo — a diferencia de las casillas.
    """
    value_changed = Signal(str)

    def __init__(self, values: list[str], current: str = '', accent: str = Colors.ACCENT,
                 danger: set[str] | None = None, parent=None):
        super().__init__(parent)
        self.accent = accent
        self.danger = danger or set()
        self._value = current or (values[0] if values else '')
        self._buttons: dict[str, QPushButton] = {}

        self.setStyleSheet(f"Segmented {{ background: {Colors.SURFACE_ALT}; border-radius: 6px; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        for value in values:
            btn = QPushButton(value)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, v=value: self.set_value(v))
            self._buttons[value] = btn
            layout.addWidget(btn)

        self._restyle()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value not in self._buttons or value == self._value:
            self._restyle()
            return
        self._value = value
        self._restyle()
        self.value_changed.emit(value)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()

    def _restyle(self) -> None:
        for value, btn in self._buttons.items():
            active = value == self._value
            btn.setChecked(active)
            if active:
                bg = Colors.ERROR if value in self.danger else self.accent
                fg = Colors.BG
            else:
                bg = 'transparent'
                fg = Colors.ERROR if value in self.danger else Colors.TEXT_DIM
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg};
                    color: {fg};
                    border: none;
                    border-radius: 4px;
                    padding: 5px 12px;
                    font-size: {Fonts.SIZE_SM}px;
                    font-weight: {'600' if active else '400'};
                }}
                QPushButton:hover {{
                    background: {bg if active else Colors.SURFACE_HOVER};
                    color: {fg if active else Colors.TEXT};
                }}
            """)
