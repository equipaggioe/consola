# El ancho del rail: automático, y fijable con el mouse

El rail dejó de tener un ancho fijo (`setFixedWidth(288)`). Ahora se comporta
como la columna derecha del panel de parámetros: se ajusta solo a lo que tiene
que mostrar, y quien quiera lo fija a mano arrastrando el separador.

## Las dos mitades

**Auto-ajuste.** `ActionRail.content_width()` mide `scroll_content.sizeHint()`
—las cajas de grupo, que crecen cuando una está abierta con acciones de título
largo— y le suma los márgenes y la barra de scroll. El resultado se clampa a
`[MIN_WIDTH, MAX_WIDTH]` (232–460). El rail emite `width_hint_changed` cada vez
que su contenido puede haber cambiado de ancho: al cambiar de repo (nombre
largo), al abrir/cerrar una caja del acordeón, al filtrar. `MainWindow`
escucha esa señal y reparte el `QSplitter`.

El aviso se difiere un ciclo de evento (`QTimer.singleShot(0, ...)`): el
`sizeHint` de una caja recién abierta solo es correcto después de que el layout
se acomode.

**Fijado manual.** Rail y espacio de trabajo van en un `QSplitter` horizontal
(`MainWindow.body_splitter`), igual que la consola y el panel de parámetros
dentro de cada pestaña. Al arrastrar el separador, `_on_rail_dragged` toma la
posición, la clampa y la guarda en `QSettings` bajo `ui/rail_width`. A partir de
ahí `preferred_width()` devuelve ese valor y el auto-ajuste no lo pisa.

**Volver a auto.** Doble clic en el separador (`eventFilter` sobre
`body_splitter.handle(1)`) llama a `clear_user_width()`: borra la clave de
`QSettings` y vuelve a mandar el contenido.

## La marca

`BrandMark` (la esquina «◇ CONSOLA» de la barra superior) ocupa la columna del
rail, así que copia su ancho con `set_width()` cada vez que cambia —arrastre o
auto-ajuste— para que su borde inferior siga coincidiendo con el separador.

## Estado de implementación

| Archivo | Estado |
|---|---|
| `ui/rail.py` | ✅ `content_width` / `preferred_width` / `set_user_width` / `clear_user_width`, señal `width_hint_changed`, persistencia en `QSettings` |
| `ui/main_window.py` | ✅ `QSplitter` rail↔workspace, `_on_rail_dragged`, `_sync_rail_width`, doble clic = reset, `BrandMark.set_width` |
