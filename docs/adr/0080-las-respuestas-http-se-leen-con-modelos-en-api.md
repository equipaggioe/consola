# ADR-0080 · Las respuestas HTTP de terceros se leen con modelos de Pydantic en `api/`

- **Estado:** Aceptada
- **Fecha:** 2026-11-04
- **Alcance:** `api/`, `core/tasks/utils.py`

## Contexto

`qt.md` de canone pide leer las respuestas HTTP con modelos de Pydantic en `api/`. Consola no tiene API propia: lee JSON de Cloudflare y del índice de releases de Flutter.

## Decisión

1. La regla también vale para las respuestas de terceros: `api/cloudflare.py` y `api/flutter.py`, un módulo por servicio.
2. Una respuesta que no coincide con su modelo detiene la tarea con `TaskError`.
3. `api/` tiene solo los modelos de lo que se lee hoy. `client.py`, `base.py` y `problem.py` de `qt.md` son de una API propia, y Consola no la tiene.

## Consecuencias

- `pydantic` pasa a ser una dependencia de Consola.
- Un campo nuevo de un tercero no rompe nada; uno que desaparece detiene la tarea y se nombra.

## Descartado

- **Seguir leyendo `dict`.** `qt.md` no hace excepciones, y un campo que faltaba daba un `KeyError` lejos de la respuesta.
