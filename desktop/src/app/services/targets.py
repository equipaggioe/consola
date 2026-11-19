"""Discover subprojects inside the open repo."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.errors import TaskError
from app.services.files import read_text

SPA_VITE = "spa-vite"
FLUTTER_APP = "flutter-app"
FLET_APP = "flet-app"
FASTAPI = "fastapi-server"
# A Python app that launches and opens its window (PySide6, desktop
# Flet, a bot). A separate type and not `FASTAPI` because it does not
# serve HTTP.
PYTHON_APP = "python-app"

# What the «App Python» button runs on the desktop: a Flet app with its
# `pyproject.toml` is `flet-app` for the mobile axes, but on this
# machine it starts like any other Python app.
DESKTOP_APP = (PYTHON_APP, FLET_APP)

# Where a Python app starts, in order of preference.
PYTHON_ENTRYPOINTS = ("src/main.py", "main.py")
# What makes a folder Python is its manifest or venv, not a loose
# `main.py`: without this, any folder of scripts would count as an app.
_PYTHON_MARKERS = ("requirements.txt", "pyproject.toml", ".venv")
# Where a server's `FastAPI(` is looked for, and the uvicorn module it
# gets.
_ASGI_MODULES = (
    ("src/app/main.py", "app.main:app"),
    ("app/main.py", "app.main:app"),
    ("main.py", "main:app"),
)

# «The mobile app» is one thing in the domain whether written in Flutter
# or Flet: it compiles alike, uploads alike and runs on the same
# emulator. The framework is a property of the folder, not a choice of
# whoever presses the button, so both types travel together on every
# axis naming it.
MOBILE_APP = (FLUTTER_APP, FLET_APP)

# --- repo features ---
#
# They are not subprojects: not chosen or listed, they are just there or
# not. They decide whether a step makes sense here. A repo that does not
# version its schema does not have «generar migración» turned off: it
# does not have it.
MIGRATIONS = "migrations"

IGNORED = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    ".consola",
    "__pycache__",
    ".dart_tool",
}
# A Flutter app's platform folders. Skipped only inside one: at the
# repo's root, `web/` is the SPA.
_FLUTTER_PLATFORMS = {"android", "ios", "web"}
_DEPTH = 2


@dataclass(frozen=True)
class Target:
    """A subproject found inside the open repo.

    It turns `panel`, `backoffice` and `landing` into three buttons of
    one axis: the list comes from looking at the repo, not from
    enumerating it per project (ADR-0006).
    """

    name: str
    kind: str
    path: Path

    @property
    def rel(self) -> str:
        """Return its path relative to the repo."""
        return self.name


def _detect(directory: Path) -> str:
    package = directory / "package.json"
    if package.is_file() and any(directory.glob("vite.config.*")):
        return SPA_VITE
    if (directory / "pubspec.yaml").is_file():
        return FLUTTER_APP
    if not any((directory / m).exists() for m in _PYTHON_MARKERS):
        return ""
    # Naming `flet` is not enough: a Flet library or extension names it
    # too. The app is what starts, like what `flet build` compiles.
    pyproject = directory / "pyproject.toml"
    if (
        pyproject.is_file()
        and "flet" in read_text(pyproject).lower()
        and python_entrypoint(directory)
    ):
        return FLET_APP
    if asgi_app(directory):
        return FASTAPI
    # Last because it is the weakest marker: a server also has its
    # `main.py`, and that one was already recognized above.
    if python_entrypoint(directory):
        return PYTHON_APP
    return ""


def asgi_app(directory: Path) -> str:
    """Return the module uvicorn has to load, or empty if not a server.

    It is recognized by the `FastAPI(` in its startup module, which
    makes it a server whatever the folder is called (`server/`,
    `backend/`). `alembic.ini` plus `app/main.py` covers one that builds
    its app in another module.
    """
    for relative, module in _ASGI_MODULES:
        source = directory / relative
        if source.is_file() and "FastAPI(" in read_text(source):
            return module
    if (directory / "alembic.ini").is_file() and (directory / "app" / "main.py").is_file():
        return "app.main:app"
    return ""


def python_entrypoint(directory: Path) -> Path | None:
    """Return the `main.py` a Python app starts with, or None."""
    for relative in PYTHON_ENTRYPOINTS:
        source = directory / relative
        if source.is_file():
            return source
    return None


# --- a single walk per pass ---
#
# Looking at the repo costs: `discover` runs a `stat` per file it
# examines to type each folder. One question is cheap, but some passes
# repeat the SAME question dozens of times in a row
# (`services/readiness.py` resolves all capabilities against one repo,
# each walking it again), and the walk came to take tenths of a second.
# As that ran on each keystroke of a text field, typing lagged by
# seconds.
#
# `one_scan()` shares the walk among the questions of ONE pass and lets
# go on leaving: it is no cache between events, which would lie if a
# subproject were added with Consola open. Each pass looks at the disk
# anew.
_pass: dict[tuple[str, str], Any] | None = None


@contextmanager
def one_scan() -> Iterator[None]:
    """Walk the repo once per question inside this block.

    And not once per asker. Nesting it does not open a new pass.
    """
    global _pass
    if _pass is not None:
        yield
        return
    _pass = {}
    try:
        yield
    finally:
        _pass = None


def _shared[T](key: tuple[str, str], produce: Callable[[], T]) -> T:
    if _pass is None:
        return produce()
    if key not in _pass:
        _pass[key] = produce()
    return _pass[key]


def discover(root: Path) -> list[Target]:
    """Walk the repo and return the typed subprojects it finds.

    It cuts at two levels: further down there are only dependencies and
    artifacts, and walking a whole `node_modules` per project opening is
    worth nothing.
    """
    return _shared(("discover", str(root)), lambda: _discover(root))


def _discover(root: Path) -> list[Target]:
    found: list[Target] = []
    for directory in _walk(root, _DEPTH):
        kind = _detect(directory)
        if kind:
            name = directory.name if directory != root else root.name
            found.append(Target(name, kind, directory))
    return sorted(found, key=lambda t: (t.kind, t.name))


def _walk(root: Path, depth: int) -> Iterator[Path]:
    yield root
    if depth <= 0:
        return
    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    flutter_app = (root / "pubspec.yaml").is_file()
    for entry in entries:
        if entry.name in IGNORED or entry.name.startswith("."):
            continue
        if flutter_app and entry.name in _FLUTTER_PLATFORMS:
            continue
        yield from _walk(entry, depth - 1)


def by_kinds(root: Path, kinds: Sequence[str]) -> list[Target]:
    """Return the subprojects of any of those types, in one pass."""
    wanted = set(kinds)
    return [t for t in discover(root) if t.kind in wanted]


def by_kind(root: Path, kind: str) -> list[Target]:
    """Return the subprojects of that type."""
    return by_kinds(root, (kind,))


def names_of(root: Path, kinds: Sequence[str]) -> list[str]:
    """Return a discovered axis's values, for the parameters panel.

    Sorted by name and not type: to whoever chooses, the list is of
    apps, and Flet ones coming before Flutter ones says nothing.
    """
    return sorted(t.name for t in by_kinds(root, kinds))


def names(root: Path, kind: str) -> list[str]:
    """Return the names of the subprojects of that type."""
    return names_of(root, (kind,))


def pick(root: Path, kinds: Sequence[str], name: str = "") -> Target:
    """Return the subproject chosen by name, or the only one.

    It is the counterpart of `names_of`: the panel offers those names
    and this resolves the choice. With no name it takes the only one,
    the case of almost every repo, and avoids asking for a choice that
    does not exist.
    """
    found = by_kinds(root, kinds)
    label = " o ".join(kinds)
    if name:
        for target in found:
            if target.name == name:
                return target
        raise TaskError(f'No hay ningun {label} llamado "{name}" en {root.name}.')
    if not found:
        raise TaskError(f"{root.name} no tiene ningun subproyecto de tipo {label}.")
    if len(found) > 1:
        choose = ", ".join(t.name for t in found)
        raise TaskError(f"Hay mas de un {label} en {root.name}: {choose}. Elige uno.")
    return found[0]


def find(root: Path, kind: str, name: str) -> Target:
    """Return the subproject of that type with that name."""
    return pick(root, (kind,), name)


def only(root: Path, kind: str) -> Target:
    """Return the only subproject of that type.

    It fails on zero or several.
    """
    return pick(root, (kind,))


def has_migrations(root: Path) -> bool:
    """Return whether the repo keeps its schema in versioned migrations.

    Alembic says so: its `alembic.ini` or the revisions folder. It looks
    at what the task looks at when running
    (`services/runner.py::server_root` plus `alembic/versions`), because
    that is the question: if the button were pressed, would there be a
    history to generate from or apply?
    """
    return _shared(
        ("migrations", str(root)),
        lambda: any(
            (d / "alembic.ini").is_file() or (d / "alembic" / "versions").is_dir()
            for d in _walk(root, _DEPTH)
        ),
    )


def features(root: Path) -> frozenset[str]:
    """Return the features this repo has, for what requires them."""
    return frozenset({MIGRATIONS} if has_migrations(root) else ())
