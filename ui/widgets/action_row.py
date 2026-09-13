from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QFont

from ..theme import Colors, Fonts, tint


def _alpha(hex_color: str, alpha: float) -> QColor:
    """El mismo color con transparencia: QColor no entiende 'rgba(...)',
    que es lo que sirve `theme.tint` para las hojas de estilo."""
    c = QColor(hex_color)
    c.setAlphaF(alpha)
    return c


class LevelMark(QLabel):
    """Marca de nivel de una accion: un solo paso o varios encadenados.

    Deliberadamente pequena y sin color propio: el color de la fila ya esta
    hablando de otra cosa (destructiva, favorita, lista para correr), asi que
    el nivel se dice con la forma. `◈` (rombo relleno, varias caras) es
    compuesta; `◦` (punto hueco) es atomica. Quien no lo adivine lo lee en el
    tooltip, que es el mismo lugar donde ya vive la descripcion.
    """
    COMPOSITE = '◈'
    ATOMIC = '◦'

    def __init__(self, composite: bool, parent=None):
        super().__init__(parent)
        self.setText(self.COMPOSITE if composite else self.ATOMIC)
        self.setFixedWidth(12)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip(
            "Compuesta: encadena varias acciones atómicas" if composite
            else "Atómica: un solo paso, idempotente")
        color = Colors.TEXT_DIM if composite else Colors.TEXT_MUTED
        self.setStyleSheet(
            f"background: transparent; color: {color}; font-size: {Fonts.SIZE_XS}px;")


class ScopeMark(QLabel):
    """Marca de alcance: esta accion le pasa a la maquina, no al repo abierto.

    Solo aparece en las de `scope='machine'` (instalar un SDK), porque la
    ausencia de marca ya significa "es de este repo", que es el caso normal.
    `⌂` se lee como la maquina misma, y no se confunde con las formas del
    nivel (`◈`/`◦`) que van al lado.
    """
    GLYPH = '⌂'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText(self.GLYPH)
        self.setFixedWidth(12)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("De la máquina: no depende del repositorio abierto")
        self.setStyleSheet(
            f"background: transparent; color: {Colors.TEXT_MUTED}; font-size: {Fonts.SIZE_XS}px;")


class ActionRow(QWidget):
    """Una accion en la lista del buscador: renglon de ancho completo.

    Cada accion ocupa toda la fila, como una entrada de menu, con un filete de acento a
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
                 favorite: bool = False, composite: bool = False,
                 description: str = '', machine: bool = False, parent=None):
        super().__init__(parent)
        self.capability_id = capability_id
        self.danger = danger
        self.accent = accent
        self.favorite = favorite
        self.composite = composite
        self.description = description
        self.machine = machine
        self._hovered = False
        self._pin_hovered = False
        self._ready = False

        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(self._tooltip(label))

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
        if machine:
            layout.addWidget(ScopeMark())
        layout.addWidget(LevelMark(composite))

        self.run_btn = QPushButton("▶")
        self.run_btn.setFixedSize(26, 26)
        self.run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(self.capability_id))
        layout.addWidget(self.run_btn)

        self._restyle()
        self._restyle_run()

    def _tooltip(self, label: str) -> str:
        """Nombre, que hace, de que nivel es y como se usa la fila."""
        level = ("Compuesta · encadena varias atómicas" if self.composite
                 else "Atómica · un solo paso")
        if self.machine:
            level += " · de la máquina, no del repo"
        lines = [f"<b>{label}</b>"]
        if self.description:
            lines.append(self.description)
        lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>{level}</span>")
        lines.append(f"<span style='color:{Colors.TEXT_MUTED};'>"
                     "Clic para abrir · clic en el filete para marcar favorita</span>")
        return '<br>'.join(lines)

    def matches(self, needle: str) -> bool:
        """El filtro tambien mira la descripcion: buscar 'disco' o 'caché'
        deberia encontrar Limpiar artefactos aunque no lo diga su nombre."""
        return needle in self.text_label.text().lower() or needle in self.description.lower()

    def set_ready(self, value: bool) -> None:
        if value == self._ready:
            return
        self._ready = value
        self._restyle_run()

    def set_highlighted(self, value: bool) -> None:
        """El mismo resalte del hover, puesto desde afuera: lo usa el buscador
        de la barra de menu para marcar la fila elegida con las flechas."""
        if value == self._hovered:
            return
        self._hovered = value
        self._restyle()
        self.update()

    def _restyle_run(self) -> None:
        self.run_btn.setEnabled(self._ready)
        self.run_btn.setToolTip(
            "Correr con los parámetros guardados de este repo" if self._ready
            else "Faltan claves de configuración para correr sin abrir la pestaña")
        color = self.accent if self._ready else Colors.TEXT_MUTED
        self.run_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; color: {color};
                font-size: {Fonts.SIZE_LG}px; border-radius: 4px;
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
