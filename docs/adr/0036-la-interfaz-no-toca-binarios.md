# ADR-0036 · Todo lo que ejecuta algo es una capacidad, incluso lo que dispara un ícono de la interfaz

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** ui/tab_panel.py, core/tasks/emulators.py, core/catalog.py

## Contexto

El ✕ que apaga un emulador huérfano podría llamar a `adb` directamente desde la interfaz: son dos líneas. Pero entonces esa ejecución no tendría log, no sería cancelable, no pasaría por el manejo de errores ni por la consola donde el usuario está mirando.

## Decisión

1. Lo que ejecuta algo es una **capacidad**, y corre por el mismo runner que todas: mismo log, mismos errores, misma cancelación.
2. Si no tiene sentido como botón, se declara `hidden=True` y sigue existiendo: `stop_emulator`, `bump_version`, `upload_to_vps`.
3. Una capacidad oculta **declara sus ejes igual**, aunque nadie dibuje su panel: es la única forma de que el parámetro llegue a la función, y la declaración es el contrato.
4. La interfaz no importa `subprocess` ni módulos de herramientas: pide una capacidad por id y la corre.

## Consecuencias

- Un gesto pequeño de la interfaz deja su rastro en la consola, como cualquier otra acción.
- El catálogo tiene entradas que no son botones, y hay que contarlas aparte al hablar de «cuántas acciones hay».

## Descartado

- **Llamar al binario desde el widget.** Se pierde el log, la cancelación y el manejo de errores.
