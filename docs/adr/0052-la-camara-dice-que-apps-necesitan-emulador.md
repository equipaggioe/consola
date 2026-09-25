# ADR-0052 · Qué apps necesitan emulador lo dice la cámara, no el tipo de la app

- **Estado:** Propuesta
- **Fecha:** 2026-09-24
- **Alcance:** `core/tasks/images.py::shoot_screens`, el eje `avd`; cambia el punto 5 de [ADR-0049](0049-la-camara-de-capturas-es-un-script-del-repo.md)

## Contexto

ADR-0049 hacía cortar la corrida si se marcaba una app móvil (`flutter-app` o `flet-app`) sin elegir emulador. Supone que una app móvil solo se captura en un emulador.

La cámara de banditore captura sus dos apps Flet en el navegador: corre su Python en la PC y dibuja la pantalla en Chromium a 360 × 720. No usa emulador. Con la regla de ADR-0049 había que elegir un AVD igual, y Consola lo encendía y lo apagaba sin que nadie lo usara.

Consola no puede saber cómo captura cada cámara. La cámara sí: el kit ya rechaza una app declarada `mobile: true` sin `--device`, antes de sacar la primera foto.

## Decisión

1. **Consola enciende el emulador que se eligió y pasa su serial en `--device`**, sin mirar el tipo de las apps marcadas. Sin emulador elegido no pasa `--device`.
2. **Si una app lo necesita lo decide la cámara**, con `mobile: true` en lo que le da a `parseArgs`. Sin `--device`, la cámara termina con error nombrando la app y sin sacar nada.

El efecto de ADR-0049 se mantiene: una corrida que necesita emulador y no lo tiene corta antes de la primera foto. Cambia quién lo decide.

## Consecuencias

- banditore captura sus apps Flet sin emulador.
- En vettore, marcar `app` sin emulador sigue cortando, ahora con el mensaje de la cámara (`app: es una app móvil y falta --device`).
- El error sale después de borrar los crudos de las combinaciones pedidas. Da igual, porque la corrida iba a sacarlas de nuevo.

## Descartado

- **Una clave de `config.env` con las apps que necesitan emulador.** Repite en la configuración lo que la cámara ya declara en `parseArgs`: dos fuentes de verdad.
