from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QColor

from ui.theme import Colors, Fonts, tint
from ui.project_tabs import ProjectTab


class BrandMark(QWidget):
    """Marca de la aplicacion: `◇ CONSOLA`, tenida por el repo activo.

    Abre la barra de titulo, a la izquierda de las pestanas de repos — el
    lugar donde un navegador pone su boton de menu o su logo.
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

    La ventana es sin marco (`Qt.FramelessWindowHint`) para que las pestanas
    de repos y la marca compartan fila con estos tres botones; a cambio, hay
    que ponerlos.
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
    """Fila de titulo de la ventana, al modo de un navegador: la marca, las
    pestanas de repos y los botones de ventana, todo en el borde superior.

    Un repositorio abierto es lo que una pestana del navegador: el contexto
    entero de lo que se ve debajo. Ponerlas aca —y no en una franja propia—
    dice justamente eso, y ademas devuelve una fila de alto a la ventana.

    El hueco que dejan las pestanas es zona de arrastre: `ProjectTabBar` no
    atiende el raton fuera de sus pestanas, asi que el evento sube hasta aca.
    """

    HEIGHT = ProjectTab.HEIGHT

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, tabs: QWidget, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.accent = Colors.ACCENT
        # Color de la linea que cierra la fila. La barra de pestanas pinta la
        # suya en su tramo (el color del repo activo, roto por la pestana
        # abierta); esta es la del resto del ancho, y tiene que ser la misma.
        self.rule = Colors.BORDER
        self._press_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.brand = BrandMark()
        layout.addWidget(self.brand)

        self.tabs = tabs
        layout.addWidget(self.tabs, 1)

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
        self.update()

    def set_rule(self, color: str) -> None:
        """La misma linea inferior que pinta la barra de pestanas, para que
        no se corte de color a mitad de la fila."""
        self.rule = color
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
        p.fillRect(0, self.height() - 2, self.width(), 2, QColor(self.rule))
        p.end()
