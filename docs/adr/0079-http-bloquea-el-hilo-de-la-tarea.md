# ADR-0079 · HTTP va por QNetworkAccessManager y bloquea el hilo de la tarea

- **Estado:** Propuesta
- **Fecha:** 2026-11-03
- **Alcance:** `core/http.py`, `core/tasks/utils.py`

## Contexto

`qt.md` de canone pide HTTP por `QNetworkAccessManager`, y ruff prohíbe `urllib.request`. Las tareas de Consola corren en su propio hilo y se leen de arriba abajo: la detección de la IP, Cloudflare y las descargas de los SDK esperan la respuesta para seguir.

## Decisión

1. `core/http.py` es el único que hace HTTP: `request` devuelve el cuerpo y `download` lo entrega por partes.
2. Cada llamada crea su `QNetworkAccessManager` en el hilo que llama y corre un `QEventLoop` local hasta que termina la respuesta.
3. Un error de red o una respuesta HTTP de error levanta `OSError`.

## Consecuencias

- `core/` importa Qt en un módulo más, sin widgets ni señales hacia afuera.
- Hace falta una `QCoreApplication`; sin ella, `OSError`.
- `qt.md` dice además que las respuestas llegan como señales al hilo de la interfaz: en una tarea llegan a su propio hilo, que es donde se usan.

## Descartado

- **Reescribir las tareas con señales.** Partiría cada tarea en callbacks para seguir esperando lo mismo.
