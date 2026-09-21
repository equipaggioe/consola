# ADR-0010 · Un eje de varios valores se reparte en pestañas si la tarea vive, y se recorre en bucle si termina

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/registry.py, core/catalog.py, ui/tab_panel.py

## Contexto

Marcar tres SPA significa dos cosas distintas según el botón. En «Build Vite» son tres builds en fila, y verlos en un solo log es lo correcto. En «SPA Vite» son tres dev servers vivos a la vez, y meterlos en una consola sería ilegible, sin forma de detener uno solo.

## Decisión

1. La diferencia no la decide la capacidad caso por caso: la decide **`kind`**. Una capacidad que termina recorre su eje `many` en un bucle, dentro de su propia consola.
2. Una capacidad `live` declara `fanout='<nombre del eje>'` y la interfaz abre **una pestaña por valor marcado**, con su proceso y su consola.
3. El primero se queda en la pestaña desde la que se apretó Ejecutar, solo cambiando de nombre: el caso normal —un repo con una sola SPA— se ve exactamente igual que antes, sin una pestaña de más.
4. La función recibe **un solo valor**, no la lista: `kwargs_from` lo desarma cuando el eje es el del fanout.

## Consecuencias

- `serve_vite` y `run_python` corren una sola app por llamada, y eso está escrito en sus docstrings.
- La interfaz necesita renombrar una pestaña ya abierta (`_retitle`) y resolver colisiones de nombre.

## Descartado

- **Declarar el reparto capacidad por capacidad.** Es una consecuencia de que la tarea no termine, no una preferencia de cada botón.
