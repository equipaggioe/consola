from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF

from ui.theme import Colors, Fonts, tint, on_color
from ui.project_tabs import ProjectTab
from ui.palettes import NEUTRAL, Palette


class Diamond(QWidget):
    """El rombo de la marca, pintado.

    Como caracter (`◇`) es un trazo de un pixel que a esta escala se pierde
    contra el acento, y la negrita no lo engorda: es un simbolo geometrico,
    no una letra. Pintado se le puede pedir el grosor que la marca necesita.
    """

    SIZE = 17
    STROKE = 2.2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE + 4, self.SIZE + 4)
        self._color = Colors.INK

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._color))
        pen.setWidthF(self.STROKE)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = QRectF(self.rect()).center()
        h = self.SIZE / 2 - self.STROKE / 2
        rombo = QPolygonF([QPointF(c.x(), c.y() - h), QPointF(c.x() + h, c.y()),
                           QPointF(c.x(), c.y() + h), QPointF(c.x() - h, c.y())])
        p.drawPolygon(rombo)
        p.end()


class BrandMark(QWidget):
    """Marca de la aplicacion: el rombo y `CONSOLA`, sobre la barra de titulo
    pintada del color del repo activo.

    Abre la barra de titulo, a la izquierda de las pestanas de repos — el
    lugar donde un navegador pone su boton de menu o su logo.

    Sin placa que la separe, lo que la sostiene es el peso: el rombo se pinta
    con trazo propio y el nombre va en negro de imprenta.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(9)

        self.diamond = Diamond()
        self.title = QLabel("CONSOLA")
        self.title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self.diamond)
        layout.addWidget(self.title)
        self.set_palette(NEUTRAL)

    def set_palette(self, pal: Palette) -> None:
        fg = pal.on_accent
        self.diamond.set_color(fg)
        self.title.setStyleSheet(f"""
            background: transparent;
            color: {fg};
            font-size: {Fonts.SIZE_SM}px;
            font-weight: 900;
            letter-spacing: 3px;
        """)


class WindowButton(QPushButton):
    """Minimizar / maximizar / cerrar, dibujados por nosotros.

    La ventana es sin marco (`Qt.FramelessWindowHint`) para que las pestanas
    de repos y la marca compartan fila con estos tres botones; a cambio, hay
    que ponerlos.

    El glifo se **pinta**, no se escribe. Como texto («─», «□», «✕») eran
    trazos de un pixel que se perdian contra el acento, y la negrita no los
    engorda: son caracteres de dibujo de caja, no letras. Pintados, los tres
    tienen el mismo grosor y el mismo tamano, que es justo lo que se les pide.
    """

    WIDTH = 46
    STROKE = 1.6
    GLYPH = 11          # lado del cuadrado / de la equis, en pixeles

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind                    # 'min' | 'max' | 'close'
        self.maximized = False
        self.setFixedWidth(self.WIDTH)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._fg = Colors.TEXT_DIM
        self.set_foreground(Colors.TEXT_DIM)

    def set_foreground(self, color: str) -> None:
        """El trazo toma el color legible sobre la barra (`on_color`).

        El fondo del hover sale de ese mismo color y no de un gris fijo: un
        gris oscuro sobre una barra clara era una mancha que no se parecia a
        nada del resto de la ventana. El de cerrar si es rojo — ahi el color
        ES el aviso.
        """
        self._fg = color
        hover = Colors.ERROR if self.kind == 'close' else tint(color, 0.16)
        self.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; padding: 0; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {tint(
                Colors.ERROR if self.kind == 'close' else color, 0.32)}; }}
        """)
        self.update()

    def set_maximized(self, value: bool) -> None:
        self.maximized = value
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)           # el fondo del hover lo pone la hoja
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(Colors.TEXT if (self.kind == 'close' and self.underMouse())
                       else self._fg)
        pen = QPen(color)
        pen.setWidthF(self.STROKE)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        c = QRectF(self.rect()).center()
        h = self.GLYPH / 2
        if self.kind == 'min':
            p.drawLine(QPointF(c.x() - h, c.y()), QPointF(c.x() + h, c.y()))
        elif self.kind == 'max':
            if self.maximized:
                # Restaurar: la hoja de atras asomando por arriba y a la derecha.
                p.drawRect(QRectF(c.x() - h, c.y() - h + 2.5, self.GLYPH - 2.5,
                                  self.GLYPH - 2.5))
                p.drawLine(QPointF(c.x() - h + 2.5, c.y() - h + 2.5),
                           QPointF(c.x() - h + 2.5, c.y() - h))
                p.drawLine(QPointF(c.x() - h + 2.5, c.y() - h),
                           QPointF(c.x() + h, c.y() - h))
                p.drawLine(QPointF(c.x() + h, c.y() - h),
                           QPointF(c.x() + h, c.y() + h - 2.5))
            else:
                p.drawRect(QRectF(c.x() - h, c.y() - h, self.GLYPH, self.GLYPH))
        else:
            p.drawLine(QPointF(c.x() - h, c.y() - h), QPointF(c.x() + h, c.y() + h))
            p.drawLine(QPointF(c.x() + h, c.y() - h), QPointF(c.x() - h, c.y() + h))
        p.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


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
        # La fila entera se pinta del color del repo activo: es la senal de que
        # repo esta abierto, en vez de una linea bajo su pestana.
        self.accent = Colors.ACCENT
        self._press_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.brand = BrandMark()
        layout.addWidget(self.brand)

        self.tabs = tabs
        layout.addWidget(self.tabs, 1)

        self.min_btn = WindowButton('min')
        self.max_btn = WindowButton('max')
        self.close_btn = WindowButton('close')
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedHeight(self.HEIGHT)
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        self.max_btn.clicked.connect(self.maximize_requested.emit)
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)
        self.set_palette(NEUTRAL)

    # --- estado -----------------------------------------------------------
    def set_palette(self, pal: Palette) -> None:
        self.accent = pal.accent
        self.brand.set_palette(pal)
        fg = on_color(pal.accent)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.set_foreground(fg)
        self.update()

    def set_maximized(self, value: bool) -> None:
        self.max_btn.set_maximized(value)
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
        p.fillRect(self.rect(), QColor(self.accent))
        p.end()
