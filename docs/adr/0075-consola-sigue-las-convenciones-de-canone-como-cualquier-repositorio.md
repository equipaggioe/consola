# ADR-0075 · Consola sigue las convenciones de canone como cualquier repositorio

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** todo el repositorio

## Contexto

El ADR-0107 de canone libera cómo Consola junta y guarda sus datos, no las convenciones de un repositorio: `principios.md`, `repositorio.md` y `documentacion.md` aplican a todos, y `python.md` y `qt.md` a una pieza de escritorio con PySide6. Consola corría desde la raíz con `core/`, `ui/`, `camara/` y `requirements.txt`, sin README, CI ni `.gitattributes`.

## Decisión

1. **Consola cumple las convenciones de canone, sin ADR de desviación.** Es el primer repositorio que tiene que cumplirlas.
2. **La pieza es `desktop/`**, con el paquete `app` en `desktop/src/app/`, `pyproject.toml` y `uv.lock`, y las pruebas en `desktop/tests/`. Los imports son absolutos.
3. **`scripts/` sale.** Reemplaza la parte del punto 1 del [ADR-0059](0059-desplegar-con-los-programas-de-canone.md) que la conservaba como especificación (pregunta 16 del plan de despliegue). El código sigue en la historia de git.
4. **Lo que todavía no cumple se anota en el 30**, y el CI queda en rojo hasta que se cumpla: una regla que no rompe el CI es una sugerencia.

## Consecuencias

- Los ADR anteriores citan rutas como `core/vps.py`: son relativas a `desktop/src/app/`.
- Consola se arranca con `uv run python -m app.main`, desde `desktop/`.

## Descartado

- **Declarar desviaciones de la estructura o del idioma.** Consola es la herramienta que lleva a los demás repositorios a canone.
