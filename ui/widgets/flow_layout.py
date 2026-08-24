from __future__ import annotations
from PySide6.QtWidgets import QLayout, QSizePolicy
from PySide6.QtCore import Qt, QRect, QPoint, QSize


class FlowLayout(QLayout):
    """Disposicion que envuelve: los hijos se colocan en fila y saltan de
    linea cuando no cabe el siguiente.

    Es lo que permite que las acciones dentro de una caja de grupo se lean
    como etiquetas empacadas (cada una del ancho de su texto) en vez de
    como un listado de filas del mismo alto.
    """

    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    # --- plomeria de QLayout -----------------------------------------
    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        # Solo el alto de un elemento manda: si el minimo incluyera el ancho
        # del mas largo, el contenedor no podria angostarse y el rail acabaria
        # con barra de desplazamiento horizontal.
        height = 0
        for item in self._items:
            height = max(height, item.minimumSize().height())
        m = self.contentsMargins()
        return QSize(0, height + m.top() + m.bottom())

    # --- calculo -----------------------------------------------------
    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0

        for item in self._items:
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x - 1 > eff.right() and line_h > 0:
                x = eff.x()
                y = y + line_h + self._v
                next_x = x + hint.width()
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h
            line_h = max(line_h, hint.height())

        return y + line_h - rect.y() + m.bottom()
