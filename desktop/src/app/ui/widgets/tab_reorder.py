from __future__ import annotations
from PySide6.QtCore import Qt


class ReorderableTab:
    """Mezcla para una pestana que se puede arrastrar para reordenarla.

    La seleccion sigue ocurriendo al apretar (respuesta inmediata, como en
    un navegador); si el cursor se mueve mas alla del umbral sin soltar, la
    pestana entra en modo arrastre y la barra la va recolocando cada vez que
    el cursor cruza el centro de una vecina.

    Quien la usa debe: llamar `_init_reorder()` en su __init__, delegar los
    tres eventos de raton a `_reorder_press/_reorder_move/_reorder_release`,
    y tener como padre una barra con `reorder_to(tab, index)` y `tabs`.
    """

    DRAG_THRESHOLD = 6

    def _init_reorder(self) -> None:
        self._drag_origin = None
        self._is_dragging = False

    @property
    def is_dragging(self) -> bool:
        return getattr(self, '_is_dragging', False)

    def _reorder_bar(self):
        """Sube por los padres hasta quien sabe reordenar: el contenedor
        directo de las pestanas no siempre es el que lleva la lista (las
        sub-pestanas viven en un layout anidado dentro del panel)."""
        node = self.parent()
        while node is not None:
            if hasattr(node, 'reorder_to'):
                return node
            node = node.parent()
        return None

    def _reorder_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.position()

    def _reorder_move(self, event) -> None:
        if self._drag_origin is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        bar = self._reorder_bar()
        if bar is None or len(getattr(bar, 'tabs', [])) < 2:
            return

        if not self._is_dragging:
            if abs(event.position().x() - self._drag_origin.x()) < self.DRAG_THRESHOLD:
                return
            self._is_dragging = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.raise_()
            self.update()

        # Centro del cursor en coordenadas de la barra: la posicion del punto
        # agarrado, no la del borde, para que la pestana no salte al tomarla.
        pos_in_bar = self.mapToParent(event.position().toPoint())
        bar.reorder_to(self, bar.index_for_x(pos_in_bar.x(), self))

    def _reorder_release(self, event) -> None:
        self._drag_origin = None
        if self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update()


class ReorderableBar:
    """Mezcla para la barra que contiene pestanas arrastrables.

    Espera `self.tabs` (lista ordenada) y `self._tab_layout()` (el layout que
    las contiene). `reorder_to` reconstruye el orden del layout, asi que no
    hay aritmetica de indices que se pueda desincronizar del modelo.
    """

    def _tab_layout(self):
        raise NotImplementedError

    def index_for_x(self, x: int, dragged) -> int:
        """Indice donde deberia quedar `dragged` si se suelta en `x`."""
        target = len(self.tabs) - 1
        for i, tab in enumerate(self.tabs):
            if x < tab.x() + tab.width() / 2:
                target = i
                break
        return max(0, min(target, len(self.tabs) - 1))

    def reorder_to(self, tab, index: int) -> None:
        if tab not in self.tabs:
            return
        current = self.tabs.index(tab)
        if index == current:
            return
        self.tabs.insert(index, self.tabs.pop(current))
        self._relayout_tabs()
        self.tabs_reordered()

    def _relayout_tabs(self) -> None:
        layout = self._tab_layout()
        for tab in self.tabs:
            layout.removeWidget(tab)
        for offset, tab in enumerate(self.tabs):
            layout.insertWidget(offset, tab)
        layout.activate()

    def tabs_reordered(self) -> None:
        """Gancho para quien quiera reaccionar al nuevo orden."""
        pass
