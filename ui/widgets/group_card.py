from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont

from ..theme import Colors, Fonts
from .section_header import ChevronWidget


def _alpha(hex_color: str, alpha: float) -> QColor:
    """El mismo color con transparencia: QColor no entiende 'rgba(...)',
    que es lo que sirve `theme.tint` para las hojas de estilo."""
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


class ActionRow(QWidget):
    """Una accion dentro de una caja de grupo: renglon de ancho completo.

    Distinta de la pastilla (chip) que se probo antes: aqui cada accion
    ocupa toda la fila, como una entrada de menu, con un filete de acento a
    la izquierda que solo aparece con el hover o si es destructiva.
    """
    triggered = Signal(str)

    HEIGHT = 32

    def __init__(self, capability_id: str, label: str, icon: str = '',
                 danger: bool = False, accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.capability_id = capability_id
        self.danger = danger
        self.accent = accent
        self._hovered = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(9)

        self.icon_label = QLabel(icon or "·")
        self.icon_label.setFixedWidth(18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(f"background: transparent; font-size: {Fonts.SIZE_SM}px;")

        self.text_label = QLabel(label)
        f = QFont(self.text_label.font())
        f.setPixelSize(Fonts.SIZE_SM)
        self.text_label.setFont(f)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addStretch()

        self._restyle()

    def matches(self, needle: str) -> bool:
        return needle in self.text_label.text().lower()

    def set_accent(self, accent: str) -> None:
        self.accent = accent
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
        r = QRectF(self.rect())
        edge = QColor(Colors.ERROR) if self.danger else QColor(self.accent)

        if self._hovered:
            p.fillRect(r, _alpha(self.accent, 0.09) if not self.danger else _alpha(Colors.ERROR, 0.08))

        # Filete de acento: siempre visible y tenue si es destructiva (aviso
        # permanente), solo al pasar el mouse en las demas.
        if self.danger or self._hovered:
            bar_alpha = 0.9 if self._hovered else 0.55
            p.fillRect(QRectF(0, 3, 2.5, r.height() - 6), _alpha(edge.name(), bar_alpha))
        p.end()


class GroupCard(QWidget):
    """Caja de un grupo: cerrada es un recuadro con nombre y cuenta; abierta
    despliega sus acciones, una por renglon, dentro del mismo recuadro."""
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

        # --- cuerpo: un renglon por accion -----------------------------
        self.body_wrap = QWidget()
        self.body_wrap.setStyleSheet("background: transparent;")
        bw = QVBoxLayout(self.body_wrap)
        bw.setContentsMargins(0, 2, 0, 6)
        bw.setSpacing(0)

        self.rows: list[ActionRow] = []
        for cap in capabilities:
            row = ActionRow(cap.id, cap.name, cap.icon,
                            danger=cap.kind == 'destructive', accent=accent)
            row.triggered.connect(self.action_triggered.emit)
            bw.addWidget(row)
            self.rows.append(row)

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
        for row in self.rows:
            row.set_accent(accent)
        self._restyle()
        self.update()

    def filter(self, needle: str) -> int:
        """Deja visibles los renglones que coinciden; devuelve cuantos."""
        if not needle:
            for row in self.rows:
                row.setVisible(True)
            return len(self.rows)
        visible = 0
        for row in self.rows:
            match = row.matches(needle)
            row.setVisible(match)
            visible += int(match)
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
