# Consola

Aplicación de escritorio para operar repositorios: levanta sus piezas, compila, administra la base local, y prepara y despliega un VPS con los programas de [canone](https://github.com/equipaggioe/canone).

Estado: en desarrollo

## Piezas

| Pieza | Qué es | Cómo se levanta |
|---|---|---|
| [`desktop/`](desktop/) | La aplicación, con Qt Widgets y PySide6 | `uv sync` y `uv run python -m app.main`, desde `desktop/` |

## Documentación

- [`docs/`](docs/README.md): arquitectura, decisiones y planes.
- [canone](https://github.com/equipaggioe/canone): las convenciones que sigue este repositorio.
