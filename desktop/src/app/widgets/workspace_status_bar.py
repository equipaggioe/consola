"""The status bar of a repo's workspace, with its padlock."""

from __future__ import annotations

from typing import Any, override

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from app import theme
from app.services import (
    protection,
    sysinfo,
    toolstatus,
)
from app.services.palettes import Palette
from app.services.toolstatus import Tool
from app.theme import Colors, Fonts
from app.widgets.led_indicator import LedIndicator


class _PadlockChip(QLabel):
    """A protection target on the status bar.

    Its short name with a padlock, closed (protected) or open
    (unprotected). A click jumps to the Security section.
    """

    clicked = Signal()

    def __init__(
        self, chip: str, label: str, protected: bool, pal: Palette, parent: QWidget | None = None
    ) -> None:
        """Build the chip."""
        super().__init__(f"{'🔒' if protected else '🔓'} {chip}", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Closed = safe (the repo's color); open = exposed to a
        # destructive action with no net, and that is red in every repo.
        color = theme.PADLOCK.on(pal).fg if protected else Colors.ERROR
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )
        self.setToolTip(
            f"{label}: {'protegido' if protected else 'sin proteger'}. "
            "Clic para administrar en Configuración → Seguridad."
        )

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class WorkspaceStatusBar(QWidget):
    """The window's bottom bar: the repo at left, the machine at right.

    At left, what belongs to the active repo: its guards, and the
    background services when someone reports them. At right, what
    belongs to this machine and holds for every repo: the tools and the
    RAM.
    """

    # click on the active repo's guards indicator
    security_clicked = Signal()

    def __init__(self, pal: Palette, parent: QWidget | None = None) -> None:
        """Build the bar."""
        super().__init__(parent)
        self.pal = pal
        # What the padlocks last showed: on changing color they have to
        # be repainted, and the repo holds the state, not the bar.
        self._protection: dict[str, Any] = {}
        self.setFixedHeight(34)
        # Without this a QWidget subclass paints neither background nor
        # border from its style sheet: the top line separating it from
        # the content did not show (same reason as in
        # `widgets/accordion_section.py`).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # --- the repo ---
        #
        # The active repo's protection targets
        # (`services/protection.py`), each with its open or closed
        # padlock, always in view whichever action is open above
        # (`ADR-0018` §4). A click on any jumps to the Security section.
        self.security_box = QWidget()
        self.security_box.setStyleSheet("background: transparent;")
        self._security_row = QHBoxLayout(self.security_box)
        self._security_row.setContentsMargins(0, 0, 0, 0)
        self._security_row.setSpacing(9)
        layout.addWidget(self.security_box)

        self.services_layout = QHBoxLayout()
        self.services_layout.setSpacing(10)
        layout.addLayout(self.services_layout)

        layout.addStretch()

        # --- the machine ---
        #
        # Environment state: it checks itself, not with a button.
        self.tools_layout = QHBoxLayout()
        self.tools_layout.setSpacing(10)
        layout.addLayout(self.tools_layout)
        self._tools: dict[str, tuple[LedIndicator, QLabel]] = {}
        self.refresh_tools()

        self._sep_ram = self._divider()
        layout.addWidget(self._sep_ram)

        # Available RAM: unlike the SDKs, it changes all the time and
        # not only after an install, so it has its own timer.
        self.ram_label = QLabel()
        self.ram_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        layout.addWidget(self.ram_label)
        self._ram_timer = QTimer(self)
        self._ram_timer.timeout.connect(self.refresh_ram)
        self._ram_timer.start(5000)
        self.refresh_ram()

        self._restyle()

    def _divider(self) -> QFrame:
        """Return a thin vertical line between two bar sections."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"background: {theme.STATUS_BAR.on(self.pal).border}; border: none;")
        line.setFixedHeight(16)
        return line

    @Slot()
    def refresh_tools(self) -> None:
        """Look at the disk again and repaint the environment's LEDs.

        It is called on building the bar and after each machine action,
        such as installing an SDK: since the install leaves its
        variables in the process's `os.environ`, the LED turns green
        without restarting anything.
        """
        for tool in toolstatus.detect():
            if tool.key not in self._tools:
                self._tools[tool.key] = self._build_tool(tool)
            led, label = self._tools[tool.key]
            # 'on', not 'green': the pulsing green says «this is
            # running», and an installed tool is a still fact.
            led.set_state("on" if tool.found else "off")
            tip = f"{tool.label}: {tool.detail}"
            led.setToolTip(tip)
            label.setToolTip(tip)
            label.setStyleSheet(
                f"color: {Colors.TEXT_DIM if tool.found else Colors.TEXT_MUTED}; "
                f"font-size: {Fonts.SIZE_XS}px;"
            )

    @Slot()
    def refresh_ram(self) -> None:
        """Show available and total RAM, rounded to the GB.

        Enough to see at a glance whether to close something before
        launching a heavy build.
        """
        ram = sysinfo.available_ram()
        self.ram_label.setVisible(ram is not None)
        self._sep_ram.setVisible(ram is not None)
        if ram is None:
            return
        available, total = ram
        locale = self.locale()
        free, size = locale.toString(available, "f", 1), locale.toString(total, "f", 1)
        self.ram_label.setText(f"RAM {free}/{size} GB")
        threshold = total * 0.15
        color = Colors.TEXT_DIM if available > threshold else Colors.WARNING
        self.ram_label.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )

    def _build_tool(self, tool: Tool) -> tuple[LedIndicator, QLabel]:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=8)
        led.setAccessibleName(tool.label)
        label = QLabel(tool.label)
        clayout.addWidget(led)
        clayout.addWidget(label)

        self.tools_layout.addWidget(container)
        return led, label

    def add_service(self, name: str) -> None:
        """Add a service indicator."""
        container = QWidget()
        container.setObjectName(f"service_{name}")
        container.setStyleSheet("background: transparent;")
        clayout = QHBoxLayout(container)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(5)

        led = LedIndicator(size=9)
        led.setAccessibleName(name)
        led.set_state("green")
        clayout.addWidget(led)

        label = QLabel(name)
        label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_DIM}; font-size: {Fonts.SIZE_XS}px;"
        )
        clayout.addWidget(label)

        self.services_layout.addWidget(container)

    def clear(self) -> None:
        """Show no guards: no repository is open.

        See `windows/main_window.py::_show_empty_state`.
        """
        self.security_box.setVisible(False)

    def set_protection(self, state: dict[str, Any]) -> None:
        """Refresh the padlocks with the state of EACH target.

        From `services/protection.TARGETS`, not only the protected ones:
        a target with no guard is also a datum, and its open padlock
        shows at a glance. `state` is `{target_id: bool}`
        (`widgets/security_panel.py`). It is called on changing repo and
        each time a switch is touched.
        """
        self._protection = dict(state)
        while self._security_row.count():
            item = self._security_row.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.deleteLater()

        self.security_box.setVisible(True)
        for target in protection.TARGETS:
            protected = protection.is_protected(state, target)
            chip = _PadlockChip(target.chip, target.label, protected, self.pal)
            chip.clicked.connect(self.security_clicked.emit)
            self._security_row.addWidget(chip)
        self._restyle()

    def set_palette(self, pal: Palette) -> None:
        """Repaint with the palette of the repo."""
        self.pal = pal
        self._restyle()
        # Padlocks paint in the accent when closed, so they have to be
        # redone; with an empty bar there are none to redo.
        if self.security_box.isVisible():
            self.set_protection(self._protection)

    def _restyle(self) -> None:
        bar = theme.STATUS_BAR.on(self.pal)
        self.setStyleSheet(f"""
            WorkspaceStatusBar {{
                background: {bar.bg};
                border-top: 1px solid {bar.border};
            }}
        """)
        self._sep_ram.setStyleSheet(f"background: {bar.border}; border: none;")
