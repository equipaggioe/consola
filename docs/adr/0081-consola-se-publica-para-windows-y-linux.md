# ADR-0081 · Consola se publica para Windows y Linux

- **Estado:** Aceptada
- **Fecha:** 2026-11-04
- **Alcance:** `.github/workflows/release.yml`

## Decisión

1. `release.yml` construye `desktop-linux.bin` y `desktop-windows.exe`.
2. Consola no tiene servidor ni web: un job `draft` crea el release en borrador, que en la plantilla crea el job `artifact`.

## Consecuencias

- Coincide con los sistemas del [ADR-0048](0048-las-diferencias-de-sistema-viven-en-host.md).

## Descartado

- **macOS, que trae la plantilla.** El ADR-0048 no lo cubre, y nadie lo probó.
