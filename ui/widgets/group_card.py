from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont, QFontMetrics

from ..theme import Colors, Fonts
from .flow_layout import FlowLayout
from .section_header import ChevronWidget


def _alpha(hex_color: str, alpha: float) -> QColor:
    """El mismo color con transparencia: QColor no entiende 'rgba(...)',
    que es lo que sirve `theme.tint` para las hojas de estilo."""
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


class ActionChip(QWidget):
    """Una accion dentro de una caja de grupo: pastilla del ancho de su texto.

    Alternativa al renglon de lista: al ocupar solo lo que mide su nombre,
    varias caben por linea y un grupo entero se abarca de un vistazo.
    """
    triggered = Signal(str)

    HEIGHT = 30
    MAX_TEXT = 150

    def __init__(self, capability_id: str, label: str,
                 danger: bool = False, accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.capability_id = capability_id
        self.label = label
        self.danger = danger
        self.accent = accent
        self._hovered = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 0, 10, 0)
        layout.setSpacing(5)

        # Sin emoji: el icono del grupo ya esta en la cabecera de la caja, y
        # 24 px por pastilla son la diferencia entre una por renglon y dos o
        # tres — que es justamente el punto de presentarlas como etiquetas.
        # Lo destructivo si conserva senal propia: un punto rojo.
        self.dot_label = QLabel("●")
        self.dot_label.setStyleSheet(
            f"background: transparent; color: {Colors.ERROR}; font-size: 8px;"
        )
        self.dot_label.setVisible(danger)

        self.text_label = QLabel()
        f = QFont(self.text_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        self.text_label.setFont(f)
        self.text_label.setText(
            QFontMetrics(f).elidedText(label, Qt.TextElideMode.ElideRight, self.MAX_TEXT)
        )

        layout.addWidget(self.dot_label)
        layout.addWidget(self.text_label)

        self._restyle()

    def matches(self, needle: str) -> bool:
        return needle in self.label.lower()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle()
        self.update()

    def _restyle(self) -> None:
        if self.danger:
            color = Colors.ERROR if self._hovered else Colors.TEXT_DIM
        else:
            color = Colors.TEXT if self._hovered else Colors.TEXT_DIM
        self.text_label.setStyleSheet(f"background: transparent; color: {color};")

    def enterEvent(self, event):
        self._hovered = True
        self._restyle()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._restyle()
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and inside:
            self.triggered.emit(self.capability_id)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.HEIGHT / 2, self.HEIGHT / 2)

        edge = Colors.ERROR if self.danger else self.accent
        if self._hovered:
            p.fillPath(path, _alpha(edge, 0.20))
            p.setPen(_alpha(edge, 0.75))
        else:
            p.fillPath(path, QColor(Colors.SURFACE_ALT))
            p.setPen(_alpha(edge, 0.30) if self.danger else QColor(Colors.BORDER))
        p.drawPath(path)
        p.end()


class GroupCard(QWidget):
    """Caja de un grupo: cerrada es un recuadro con nombre y cuenta; abierta
    despliega sus acciones como pastillas dentro del mismo recuadro."""
    action_triggered = Signal(str)
    expanded = Signal(object)   # pide el foco del acordeon

    HEADER_HEIGHT = 38

    def __init__(self, group: str, icon: str, capabilities: list,
                 accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.group = group
        self.accent = accent
        self._expanded = False
        self._header_hovered = False

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # --- cabecera (toda la fila abre y cierra) ---------------------
        self.header = QWidget()
        self.header.setFixedHeight(self.HEADER_HEIGHT)
        self.header.setStyleSheet("background: transparent;")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.installEventFilter(self)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(11, 0, 8, 0)
        hl.setSpacing(8)

        self.icon_label = QLabel(icon or "◇")
        self.icon_label.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_BASE}px;")

        self.title_label = QLabel(group.upper())
        tf = QFont(self.title_label.font())
        tf.setPixelSize(Fonts.SIZE_XS)
        tf.setBold(True)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.7)
        self.title_label.setFont(tf)

        self.count_label = QLabel(str(len(capabilities)))
        self.count_label.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )

        self.chevron = ChevronWidget()
        self.chevron.set_angle(0.0)

        hl.addWidget(self.icon_label)
        hl.addWidget(self.title_label)
        hl.addStretch()
        hl.addWidget(self.count_label)
        hl.addWidget(self.chevron)

        # --- cuerpo: pastillas que envuelven --------------------------
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent;")
        self.flow = FlowLayout(self.body, margin=0, h_spacing=5, v_spacing=5)

        self.chips: list[ActionChip] = []
        for cap in capabilities:
            chip = ActionChip(cap.id, cap.name,
                              danger=cap.kind == 'destructive', accent=accent)
            chip.triggered.connect(self.action_triggered.emit)
            self.flow.addWidget(chip)
            self.chips.append(chip)

        self.body_wrap = QWidget()
        self.body_wrap.setStyleSheet("background: transparent;")
        bw = QVBoxLayout(self.body_wrap)
        bw.setContentsMargins(10, 0, 10, 10)
        bw.setSpacing(0)
        bw.addWidget(self.body)
        self.body_wrap.setVisible(False)

        outer.addWidget(self.header)
        outer.addWidget(self.body_wrap)

        self._restyle()

    # --- estado -------------------------------------------------------
    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, value: bool, announce: bool = True) -> None:
        if self._expanded == value:
            return
        self._expanded = value
        self.body_wrap.setVisible(value)
        self.chevron.set_angle(90.0 if value else 0.0)
        self._restyle()
        self.update()
        self.updateGeometry()
        if value and announce:
            self.expanded.emit(self)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        for chip in self.chips:
            chip.set_accent(accent)
        self._restyle()
        self.update()

    def filter(self, needle: str) -> int:
        """Deja visibles las pastillas que coinciden; devuelve cuantas."""
        if not needle:
            for chip in self.chips:
                chip.setVisible(True)
            self.flow.invalidate()
            return len(self.chips)
        visible = 0
        for chip in self.chips:
            match = chip.matches(needle)
            chip.setVisible(match)
            visible += int(match)
        self.flow.invalidate()
        return visible

    def _restyle(self) -> None:
        color = Colors.TEXT if self._expanded else Colors.TEXT_DIM
        self.title_label.setStyleSheet(f"background: transparent; color: {color};")

    # --- interaccion ---------------------------------------------------
    def eventFilter(self, obj, event):
        if obj is self.header:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonRelease:
                self.set_expanded(not self._expanded)
                return True
            if kind == QEvent.Type.Enter:
                self._header_hovered = True
                self.update()
            elif kind == QEvent.Type.Leave:
                self._header_hovered = False
                self.update()
        return super().eventFilter(obj, event)

    # --- pintura -------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)

        if self._expanded:
            p.fillPath(path, _alpha(self.accent, 0.07))
            p.setPen(_alpha(self.accent, 0.55))
        elif self._header_hovered:
            p.fillPath(path, QColor(Colors.SURFACE_HOVER))
            p.setPen(QColor(Colors.BORDER_LIGHT))
        else:
            p.fillPath(path, QColor(Colors.SURFACE))
            p.setPen(QColor(Colors.BORDER))
        p.drawPath(path)

        # Barra de color a la izquierda de la caja abierta: pertenece al
        # repo activo, como el resto del cromo.
        if self._expanded:
            bar = QPainterPath()
            bar.addRoundedRect(
                QRectF(r.left() + 2, r.top() + 10, 2.5, self.HEADER_HEIGHT - 20), 1.2, 1.2
            )
            p.fillPath(bar, QColor(self.accent))
        p.end()
