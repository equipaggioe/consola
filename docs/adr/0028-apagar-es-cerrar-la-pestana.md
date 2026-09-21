# ADR-0028 · Apagar un emulador es cerrar su pestaña; el inventario del panel es para los huérfanos

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/tasks/emulators.py, core/catalog.py, ui/tab_panel.py

## Contexto

«Apagar emulador» como botón del rail obliga a elegir cuál de una lista, justo cuando el que se quiere apagar es el de la pestaña que se está mirando. Y al emulador no se lo puede matar a golpes: guarda estado al cerrarse, y matarle el proceso deja el AVD a medio escribir.

## Decisión

1. **Cerrar la pestaña apaga el emulador** que esa pestaña lanzó. El apagado limpio se registra con `ctx.on_cancel` y corre **antes** de `kill_tree`, que así casi siempre no encuentra nada que matar.
2. El apagado limpio es `adb emu kill`, no una señal al proceso.
3. Para los **huérfanos** —uno de una sesión anterior, o arrancado desde Android Studio— está el ✕ de la cabecera de estado del panel, que es donde se ven. `live_state` declara qué inventario se muestra ahí.
4. `stop_emulator` sigue siendo una capacidad, **oculta**: no tiene botón en el menú, pero la corre el mismo runner que a todas las demás, con su log en la consola.
5. Corre con `track=False`: no se adueña de la pestaña, porque si lo hiciera cerrarla detendría el apagado en vez del emulador.
6. Declara su eje `serial` aunque nadie dibuje su panel: la declaración es el contrato, y es la única forma de que el serial llegue a la función.

## Consecuencias

- Lo que corre se ve donde se elige, y se apaga desde ahí.
- El apagado tarda un par de segundos, y por eso el cierre de la aplicación espera hasta 5 s antes de dejar que el sistema mate lo que quede.

## Descartado

- **Un botón «Apagar emulador» en el menú.** Pide elegir de una lista lo que ya está en la pestaña de adelante.
- **Matar el proceso del emulador.** Deja el AVD a medio escribir.
