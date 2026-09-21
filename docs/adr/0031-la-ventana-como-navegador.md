# ADR-0031 · Un repositorio abierto es una pestaña de la barra de título; las ejecuciones son el segundo nivel

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** ui/main_window.py, ui/title_bar.py, ui/project_tabs.py, ui/tab_panel.py

## Contexto

Un repositorio abierto es el contexto entero de lo que se ve debajo, igual que la pestaña de un navegador. Una franja propia para esas pestañas le costaría a la ventana una fila entera de alto, en una interfaz que ya tiene barra de menú, sub-pestañas, columna derecha y barra de estado.

## Decisión

1. Los repos son pestañas de la **barra de título**, compartiendo fila con la marca y con minimizar/maximizar/cerrar. La ventana es sin marco (`FramelessWindowHint`).
2. Cada repo tiene su propio espacio de trabajo (`TabPanel`), indexado por la **ruta normalizada** de su carpeta: CPython reusa la dirección de un objeto liberado, así que quitar un repo y añadir otro podía darle al nuevo el espacio del viejo.
3. Un repo por carpeta: dos pestañas de la misma serían dos espacios escribiendo el mismo `params.json`.
4. El **color del repo** pinta la barra de título, el borde de contorno de la ventana, el buscador y el interruptor de favoritos. La pestaña activa se funde con la barra; las demás son placas oscuras con su nombre en su propio color.
5. El precio de no tener marco se paga explícito: agarres invisibles en bordes y esquinas, arrastre en el hueco de la barra, y el borde de contorno solo con el foco — sin él, restaurada se confunde contra un escritorio oscuro.
6. No hay lista de repos de fábrica: la barra arranca vacía y el primero se añade con «+».

## Consecuencias

- La ventana gana una fila de alto para contenido.
- Hay que implementar lo que el sistema daba gratis: mover, redimensionar, maximizar y la silueta de la ventana.
- Cerrar un repo destruye su espacio de trabajo y libera su caché de parámetros, bajando antes lo pendiente.

## Descartado

- **Una franja propia para las pestañas de repo.** Cuesta una fila entera de alto.
- **Indexar los espacios de trabajo por el objeto `Project`.** CPython reusa direcciones y los mezclaba.
