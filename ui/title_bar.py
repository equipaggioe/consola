from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor

from ui.theme import Colors, Fonts, tint
from ui.widgets import ToggleSwitch
from ui import favorites


class BrandMark(QWidget):
    """Marca de la aplicacion: `◇ CONSOLA`, tenida por el repo activo.

    Vivia en la barra de repos, ocupando la columna del rail. Ahora abre la
    barra de titulo: es lo primero de la ventana, arriba de todo, y la barra
    de repos empieza directamente con las pestanas.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = Colors.ACCENT

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(8)

        self.diamond = QLabel("◇")
        self.title = QLabel("CONSOLA")
        self.title.setStyleSheet(f"""
            background: transparent;
            color: {Colors.TEXT};
            font-size: {Fonts.SIZE_SM}px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        layout.addWidget(self.diamond)
        layout.addWidget(self.title)
        self.set_accent(Colors.ACCENT)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.diamond.setStyleSheet(
            f"background: transparent; color: {accent}; font-size: {Fonts.SIZE_LG}px;")


class WindowButton(QPushButton):
    """Minimizar / maximizar / cerrar, dibujados por nosotros.

    La ventana es sin marco (`Qt.FramelessWindowHint`) para que la barra de
    menu, la marca y el interruptor de favoritos compartan fila con estos tres
    botones; a cambio, hay que ponerlos.
    """

    WIDTH = 44

    def __init__(self, glyph: str, danger: bool = False, parent=None):
        super().__init__(glyph, parent)
        self.setFixedWidth(self.WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        hover = Colors.ERROR if danger else Colors.SURFACE_HOVER
        text_hover = Colors.TEXT if danger else Colors.TEXT
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {Colors.TEXT_DIM};
                font-size: {Fonts.SIZE_SM}px;
            }}
            QPushButton:hover {{ background: {hover}; color: {text_hover}; }}
            QPushButton:pressed {{ background: {tint(hover, 0.75)}; }}
        """)


class TitleBar(QWidget):
    """Fila de titulo de la ventana: marca, catalogo de acciones, el modo
    «solo favoritos» y los botones de la ventana.

    Todo lo que antes estaba repartido —la marca en la barra de repos, la
    barra de menu como `menuBar()` de la ventana, el interruptor de favoritos
    dentro del rail— cabe en esta unica fila. El menu queda a la altura de los
    botones de ventana, que es donde se espera en una app de escritorio.
    """

    HEIGHT = 40

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    only_favorites_changed = Signal(bool)

    def __init__(self, menu_bar: QWidget, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.accent = Colors.ACCENT
        self._press_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.brand = BrandMark()
        layout.addWidget(self.brand)

        # El menu se lleva el ancho sobrante: con once grupos, es lo unico que
        # de verdad lo necesita, y `QMenuBar` sabe plegar en `»` lo que no
        # entre cuando la ventana esta en su minimo.
        self.menu_bar = menu_bar
        layout.addWidget(self.menu_bar, 1)

        self.fav_switch = ToggleSwitch("solo favoritos", favorites.only_favorites())
        self.fav_switch.toggled.connect(self.only_favorites_changed.emit)
        layout.addSpacing(10)
        layout.addWidget(self.fav_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(12)

        self.min_btn = WindowButton("─")
        self.max_btn = WindowButton("□")
        self.close_btn = WindowButton("✕", danger=True)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedHeight(self.HEIGHT)
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        self.max_btn.clicked.connect(self.maximize_requested.emit)
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    # --- estado -----------------------------------------------------------
    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.brand.set_accent(accent)
        self.fav_switch.set_accent(accent)
        self.update()

    def set_maximized(self, value: bool) -> None:
        self.max_btn.setText("❐" if value else "□")
        self.max_btn.setToolTip("Restaurar" if value else "Maximizar")

    # --- arrastrar la ventana ---------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """El movimiento del sistema arranca recien al arrastrar de verdad.

        Llamar a `startSystemMove()` en el press se comeria el doble clic —
        que es como se maximiza — porque el bucle de arrastre de Windows se
        queda con los eventos siguientes.
        """
        if self._press_pos is None:
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._press_pos).manhattanLength() < 6:
            return super().mouseMoveEvent(event)
        self._press_pos = None
        handle = self.window().windowHandle()
        if handle is not None:
            handle.startSystemMove()
        return None

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_requested.emit()
        super().mouseDoubleClickEvent(event)

    # --- pintura ----------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(Colors.CHROME))
        p.fillRect(0, self.height() - 1, self.width(), 1, QColor(Colors.BORDER))
        p.end()
