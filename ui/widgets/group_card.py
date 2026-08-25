from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont

from ..theme import Colors, Fonts, tint
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
    la izquierda que solo aparece con el hover o si es destructiva. Ese
    mismo filete es el boton de favorito: un clic ahi marca la accion sin
    abrirla, en vez de vivir en un lugar aparte.
    """
    triggered = Signal(str)
    favorite_toggled = Signal(str, bool)
    run_requested = Signal(str)

    HEIGHT = 32
    PIN_ZONE = 12  # ancho clicable del filete, mas holgado que su trazo visual

    def __init__(self, capability_id: str, label: str, icon: str = '',
                 danger: bool = False, accent: str = Colors.ACCENT,
                 favorite: bool = False, parent=None):
        super().__init__(parent)
        self.capability_id = capability_id
        self.danger = danger
        self.accent = accent
        self.favorite = favorite
        self._hovered = False
        self._pin_hovered = False
        self._ready = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Clic para abrir · clic en el filete para marcar favorita")

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

        self.run_btn = QPushButton("▶")
        self.run_btn.setFixedSize(20, 20)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.capability_id))
        layout.addWidget(self.run_btn)

        self._restyle()
        self._restyle_run()

    def matches(self, needle: str) -> bool:
        return needle in self.text_label.text().lower()

    def set_ready(self, value: bool) -> None:
        if value == self._ready:
            return
        self._ready = value
        self._restyle_run()

    def _restyle_run(self) -> None:
        self.run_btn.setEnabled(self._ready)
        self.run_btn.setToolTip(
            "Correr con los parámetros por defecto" if self._ready
            else "Faltan claves de configuración para correr sin abrir la pestaña")
        color = self.accent if self._ready else Colors.TEXT_MUTED
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {color};
                font-size: {Fonts.SIZE_XS}px; border-radius: 4px;
            }}
            QPushButton:hover {{ background: {tint(self.accent, 0.16)}; }}
            QPushButton:disabled {{ color: {Colors.BORDER_LIGHT}; }}
        """)

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self._restyle_run()
        self.update()

    def set_favorite(self, value: bool) -> None:
        if value == self.favorite:
            return
        self.favorite = value
        self._restyle()
        self.update()

    def _restyle(self) -> None:
        if self.danger:
            color = Colors.ERROR if self._hovered else Colors.TEXT_DIM
        else:
            color = Colors.TEXT if (self._hovered or self.favorite) else Colors.TEXT_DIM
        self.text_label.setStyleSheet(f"background: transparent; color: {color};")

    def _in_pin_zone(self, pos) -> bool:
        return 0 <= pos.x() <= self.PIN_ZONE

    def enterEvent(self, event):
        self._hovered = True
        self._restyle()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pin_hovered = False
        self._restyle()
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        pin_hovered = self._in_pin_zone(event.position())
        if pin_hovered != self._pin_hovered:
            self._pin_hovered = pin_hovered
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        pos = event.position()
        inside = self.rect().contains(pos.toPoint())
        if event.button() == Qt.MouseButton.LeftButton and inside:
            if self._in_pin_zone(pos):
                self.favorite = not self.favorite
                self._restyle()
                self.update()
                self.favorite_toggled.emit(self.capability_id, self.favorite)
            else:
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
        # permanente) o si es favorita, mas ancho al pasar el mouse porque
        # ahi mismo se hace clic para marcarla. Asi el favorito se distingue
        # aun viendo todo, y su boton no necesita un lugar aparte.
        if self.danger or self.favorite or self._hovered:
            bar_alpha = 0.9 if (self._hovered and not self._pin_hovered) else (0.7 if self.favorite else 0.55)
            if self._pin_hovered:
                bar_alpha = 1.0
            bar_width = 5.0 if self._pin_hovered else 2.5
            p.fillRect(QRectF(0, 3, bar_width, r.height() - 6), _alpha(edge.name(), bar_alpha))
        p.end()


class CountBadge(QLabel):
    """Cuenta de acciones de la caja: `9`, o `3/9` cuando hay acciones
    escondidas. En ese caso es el escape por caja — un clic muestra las 9
    sin tener que apagar el interruptor global."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clickable = False
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;"
        )

    def set_state(self, text: str, clickable: bool, peeking: bool = False) -> None:
        self.setText(text)
        self._clickable = clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable
                       else Qt.CursorShape.ArrowCursor)
        color = Colors.TEXT_DIM if clickable else Colors.TEXT_MUTED
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;"
        )
        if clickable:
            self.setToolTip("Ver solo las favoritas de esta caja" if peeking
                            else "Ver todas las acciones de esta caja")
        else:
            self.setToolTip("")

    def mouseReleaseEvent(self, event):
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        # Sin esto el clic se filtra a la cabecera y abre o cierra la caja.
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)


class GroupCard(QWidget):
    """Caja de un grupo: cerrada es un recuadro con nombre y cuenta; abierta
    despliega sus acciones, una por renglon, dentro del mismo recuadro."""
    action_triggered = Signal(str)
    favorite_toggled = Signal(str, bool)
    run_requested = Signal(str)
    expanded = Signal(object)   # pide el foco del acordeon

    HEADER_HEIGHT = 38

    def __init__(self, group: str, icon: str, capabilities: list,
                 accent: str = Colors.ACCENT, parent=None):
        super().__init__(parent)
        self.group = group
        self.accent = accent
        self._expanded = False
        self._header_hovered = False
        self._favorites: set[str] = set()
        self._only_favorites = False
        self._peek = False          # escape por caja: ver todo aqui, sin tocar el switch
        self._needle = ''

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

        self.count_label = CountBadge()
        self.count_label.set_state(str(len(capabilities)), False)
        self.count_label.clicked.connect(self._toggle_peek)

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
            row.favorite_toggled.connect(self._on_row_favorite_toggled)
            row.run_requested.connect(self.run_requested.emit)
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
        if not value:
            self._peek = False
            self._sync_rows()
        self.body_wrap.setVisible(value)
        self.chevron.set_angle(180.0 if value else 0.0)
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
        """Deja visibles los renglones que pasan el texto y el modo favoritos;
        devuelve cuantos."""
        self._needle = needle
        return self._sync_rows()

    # --- correr sin abrir la pestana -------------------------------------
    def set_ready(self, ready_ids: set[str]) -> None:
        for row in self.rows:
            row.set_ready(row.capability_id in ready_ids)

    # --- favoritos ------------------------------------------------------
    def set_favorites(self, favorites: set[str]) -> int:
        self._favorites = set(favorites)
        for row in self.rows:
            row.set_favorite(row.capability_id in self._favorites)
        return self._sync_rows()

    def set_only_favorites(self, value: bool) -> int:
        self._only_favorites = value
        self._peek = False
        return self._sync_rows()

    def favorite_count(self) -> int:
        return sum(1 for row in self.rows if row.capability_id in self._favorites)

    def _on_row_favorite_toggled(self, capability_id: str, value: bool) -> None:
        """El renglon ya se repinto solo; aca se actualiza el conjunto y el
        contador, y se avisa afuera para que quede guardado."""
        self._favorites.add(capability_id) if value else self._favorites.discard(capability_id)
        self._sync_rows()
        self.favorite_toggled.emit(capability_id, value)

    def _toggle_peek(self) -> None:
        self._peek = not self._peek
        self._sync_rows()
        if self._peek:
            self.set_expanded(True)

    def _sync_rows(self) -> int:
        """Una sola regla de visibilidad: pasa el filtro de texto Y (se ven
        todas, o es favorita, o esta caja esta espiando).

        Escribir en el filtro busca sobre TODAS las acciones aunque el
        interruptor este puesto: buscar es ir por algo puntual, y esconder
        justo lo que se busca por no estar marcado seria un chiste cruel.
        """
        hide_others = self._only_favorites and not self._peek and not self._needle
        visible = 0
        for row in self.rows:
            match = (not self._needle or row.matches(self._needle)) and (
                not hide_others or row.capability_id in self._favorites)
            row.setVisible(match)
            visible += int(match)

        total = len(self.rows)
        text = str(total) if visible == total else f"{visible}/{total}"
        escapable = (self._only_favorites and not self._needle
                     and (self._peek or self.favorite_count() < total))
        self.count_label.set_state(text, escapable, peeking=self._peek)
        self.updateGeometry()
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
        p.end()
