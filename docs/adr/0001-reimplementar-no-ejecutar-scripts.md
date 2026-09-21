# ADR-0001 · Los scripts se reimplementan como funciones; el único subproceso es un binario externo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** todo el repositorio

## Contexto

Cada repositorio administrado arrastraba una carpeta `scripts/` copiada: 51 archivos en nueve carpetas temáticas, con el mismo puñado de rutinas duplicado en una docena de ellos —cargar el `.env`, resolver la llave y el destino SSH, derivar el nombre del repo desde `GIT_REPO_URL`, subir un directorio por `scp`—. Mantenerlos iguales entre repos era el trabajo de otros dos scripts.

La salida fácil habría sido una interfaz que lanzara esos mismos archivos como subprocesos. Habría heredado todo: los `print` como único canal, el `SystemExit(1)` como único error, el `input()` que dentro de una ventana no tiene dónde escribirse, y los pasos empaquetados en archivos de seiscientas líneas que no se pueden pedir sueltos.

## Decisión

1. **Cada script se analiza y se reimplementa** como función Python sobre el nivel 0 (`core/`). No se copia el archivo ni se lo invoca.
2. **El único `subprocess` permitido es a un binario externo real**: `git`, `ssh`, `scp`, `flutter`, `flet`, `npm`, `adb`, `emulator`, `sdkmanager`, `psql`, `pg_dump`, `pyinstaller`, `uvicorn`.
3. Una capacidad que necesita lo que hace otra **la llama como función**, con un contexto hijo, no como proceso.
4. `scripts/` se conserva en el repositorio como **especificación de comportamiento**: es contra lo que se compara cada reimplementación. Nada del código lo importa.

## Consecuencias

- Cada paso interno es una función con nombre, así que puede tener botón propio cuando alguien lo pide solo (`upload_secret_files`, `bump_version`).
- La plomería existe una sola vez: la mayoría de las atómicas son de tres a diez líneas.
- Hay una excepción declarada y acotada: los **payloads** (`core/tasks/payloads.py`), que viajan por `-c` al intérprete del proyecto porque necesitan importar `app.` y `seeders.` del repo administrado.
- Queda en el repositorio código que nadie ejecuta. Borrarlo es una decisión aparte.

## Descartado

- **Lanzar los scripts como subprocesos.** Habría conservado el `print`/`SystemExit`/`input` y dejado los pasos empaquetados.
- **Pegar los `.py` originales dentro de la aplicación.** Es copiar, no reimplementar: el código venía de años de parches sueltos.
