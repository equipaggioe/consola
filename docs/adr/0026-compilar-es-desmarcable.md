# ADR-0026 · Se puede subir el artefacto que ya está en disco, sin volver a compilarlo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, core/tasks/builders.py

## Contexto

Un `scp` cortado a la mitad obligaba a repetir la compilación entera: diez minutos de build, o un `npm install` completo, para reintentar una subida. Los scripts originales tenían justamente un flag para eso (`BUILD_APP=false`, `BUILD_SPA=false`, `BUILD_BINARY=false`), y al portarlos el paso quedó fijo.

## Decisión

1. «Compilar» es una casilla desmarcable en los tres builders. Sin ella, el builder **sube lo que ya está en disco**.
2. Cada builder sabe encontrar su último build: en la carpeta configurada si hay una, y si no donde lo deja el framework.
3. Sin compilar **y** sin subir no queda nada por hacer, y el botón lo dice en vez de correr en vacío.
4. Un paso cuya ausencia deja un modo sin sentido no es desmarcable: `optional=False` se dibuja marcado y deshabilitado.

## Consecuencias

- Reintentar una subida cuesta lo que cuesta la subida.
- Hay dos caminos por builder —compilar y re-subir— y los dos tienen que publicar igual.

## Descartado

- **Dejar «Compilar» como paso fijo.** Es lo que obligaba a pagar el build para reintentar un `scp`.
