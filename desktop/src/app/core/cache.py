from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Callable

from app.core.errors import TaskError
from app.core.host import HOST

"""
Cache en disco para catalogos caros de consultar.

Existe por un caso concreto: los dos catalogos del emulador. `avdmanager list
device` y `sdkmanager --list` tardan de segundos a decenas de segundos, y el
panel de parametros los necesita cada vez que se dibuja — preguntarselos al SDK
en cada apertura de pestana congelaria la interfaz por algo que no cambia en
meses.

Es cache de *catalogo*, no de estado: lo que se guarda aca son listas
publicadas por una herramienta (que dispositivos existen, que imagenes se
pueden bajar). Lo que cambia solo — que AVD hay creado, que emulador esta
vivo — no se cachea nunca: se pregunta cada vez, porque es barato y porque una
respuesta vieja ahi seria mentira.

Vive en `%LOCALAPPDATA%\\Consola\\cache` (o `~/.cache/consola`), fuera de los
repos: es historia de la maquina, igual que el SQLite de docs/arquitectura/30_riesgos_y_pendientes.md.
"""


def app_dir() -> Path:
    """Carpeta de datos de Consola en esta maquina."""
    return HOST.data_dir()


def _file(name: str) -> Path:
    return app_dir() / 'cache' / f'{name}.json'


def read(name: str, *, max_age: float) -> Any | None:
    """What is saved under that name, or `None` if it is missing or older than `max_age`.

    A file that cannot be read stops the task and is named: it does not count as empty
    (ADR-0076).
    """
    path = _file(name)
    try:
        if time.time() - path.stat().st_mtime > max_age:
            return None
        return json.loads(path.read_text(encoding='utf-8'))['value']
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError) as exc:
        raise TaskError(f'No se puede leer la caché {path}: bórrala. ({exc})') from exc


def write(name: str, value: Any) -> None:
    path = _file(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'saved': time.time(), 'value': value}),
                        encoding='utf-8')
    except OSError as exc:
        raise TaskError(f'No se puede escribir la caché {path}: {exc}') from exc


def forget(name: str) -> None:
    """Invalida una entrada. La llama quien acaba de cambiar lo que describe."""
    _file(name).unlink(missing_ok=True)


def cached(name: str, producer: Callable[[], Any], *,
           max_age: float = 30 * 24 * 3600, refresh: bool = False) -> Any:
    """Lo cacheado, o el resultado de `producer` recien calculado y guardado.

    `max_age` por defecto es un mes: los catalogos del SDK crecen cuando sale
    una API nueva, no durante una sesion de trabajo. `refresh=True` es el boton
    ↻ del panel.
    """
    if not refresh:
        hit = read(name, max_age=max_age)
        if hit is not None:
            return hit
    value = producer()
    write(name, value)
    return value
