r"""Disk cache for catalogs that are expensive to query.

It exists for the two emulator catalogs. `avdmanager list device` and
`sdkmanager --list` take seconds to tens of seconds, and the parameters
panel needs them each time it draws: asking the SDK on every tab would
freeze the interface for something that changes every few months.

It caches *catalogs*, not state: lists a tool publishes (which devices
exist, which images can be downloaded). What changes by itself, such as
which AVD exists or which emulator is alive, is never cached: it is
cheap to ask, and an old answer would be a lie.

It lives in `%LOCALAPPDATA%/Consola/cache` (or `~/.cache/consola`),
outside the repos: it is history of the machine.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.errors import TaskError
from app.core.host import HOST


def app_dir() -> Path:
    """Return Consola's data folder on this machine."""
    return HOST.data_dir()


def _file(name: str) -> Path:
    return app_dir() / "cache" / f"{name}.json"


def read(name: str, *, max_age: float) -> Any | None:
    """Return what is saved under that name.

    Or `None` if it is missing or older than `max_age`.

    A file that cannot be read stops the task and is named: it does not
    count as empty (ADR-0076).
    """
    path = _file(name)
    try:
        if time.time() - path.stat().st_mtime > max_age:
            return None
        return json.loads(path.read_text(encoding="utf-8"))["value"]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError) as exc:
        raise TaskError(f"No se puede leer la caché {path}: bórrala. ({exc})") from exc


def write(name: str, value: Any) -> None:
    """Save a value under that name."""
    path = _file(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"saved": time.time(), "value": value}), encoding="utf-8")
    except OSError as exc:
        raise TaskError(f"No se puede escribir la caché {path}: {exc}") from exc


def forget(name: str) -> None:
    """Invalidate an entry, after changing what it describes."""
    _file(name).unlink(missing_ok=True)


def cached(
    name: str,
    producer: Callable[[], Any],
    *,
    max_age: float = 30 * 24 * 3600,
    refresh: bool = False,
) -> Any:
    """Return the cached value, or compute and save it with `producer`.

    `max_age` defaults to a month: SDK catalogs grow when a new API
    ships, not during a work session. `refresh=True` is the panel's ↻
    button.
    """
    if not refresh:
        hit = read(name, max_age=max_age)
        if hit is not None:
            return hit
    value = producer()
    write(name, value)
    return value
