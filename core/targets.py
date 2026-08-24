from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .errors import TaskError
from .files import read_text

SPA_VITE = 'spa-vite'
FLUTTER_APP = 'flutter-app'
FLET_APP = 'flet-app'
FASTAPI = 'fastapi-server'

_IGNORED = {'node_modules', '.git', '.venv', 'venv', 'build', 'dist', '.consola',
            '__pycache__', '.dart_tool', 'android', 'ios', 'web'}
_DEPTH = 2


@dataclass(frozen=True)
class Target:
    """Un subproyecto encontrado dentro del repo abierto.

    Es lo que convierte `panel`/`backoffice`/`landing` de tres scripts casi
    identicos en tres botones del mismo eje: la lista sale de mirar el repo,
    no de enumerarla a mano por proyecto (PLAN.md 2.4).
    """
    name: str
    kind: str
    path: Path

    @property
    def rel(self) -> str:
        return self.name


def _detect(directory: Path) -> str:
    package = directory / 'package.json'
    if package.is_file() and any(directory.glob('vite.config.*')):
        return SPA_VITE
    if (directory / 'pubspec.yaml').is_file():
        return FLUTTER_APP
    pyproject = directory / 'pyproject.toml'
    if pyproject.is_file() and 'flet' in read_text(pyproject).lower():
        return FLET_APP
    if (directory / 'app' / 'main.py').is_file() or (directory / 'alembic.ini').is_file():
        return FASTAPI
    return ''


def discover(root: Path) -> list[Target]:
    """Recorre el repo y devuelve los subproyectos tipados que encuentra.

    Se corta a dos niveles: mas abajo solo hay dependencias y artefactos, y
    recorrer `node_modules` entero por cada apertura de proyecto no vale nada.
    """
    found: list[Target] = []
    for directory in _walk(root, _DEPTH):
        kind = _detect(directory)
        if kind:
            name = directory.name if directory != root else root.name
            found.append(Target(name, kind, directory))
    return sorted(found, key=lambda t: (t.kind, t.name))


def _walk(root: Path, depth: int):
    yield root
    if depth <= 0:
        return
    try:
        entries = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return
    for entry in entries:
        if entry.name in _IGNORED or entry.name.startswith('.'):
            continue
        yield from _walk(entry, depth - 1)


def by_kind(root: Path, kind: str) -> list[Target]:
    return [t for t in discover(root) if t.kind == kind]


def names(root: Path, kind: str) -> list[str]:
    """Los valores que toma un eje descubierto, listos para el panel de parametros."""
    return [t.name for t in by_kind(root, kind)]


def find(root: Path, kind: str, name: str) -> Target:
    for target in by_kind(root, kind):
        if target.name == name:
            return target
    raise TaskError(f'No hay ningun {kind} llamado "{name}" en {root.name}.')


def only(root: Path, kind: str) -> Target:
    """El unico subproyecto de ese tipo. Falla si hay cero o mas de uno."""
    found = by_kind(root, kind)
    if not found:
        raise TaskError(f'{root.name} no tiene ningun subproyecto de tipo {kind}.')
    if len(found) > 1:
        elegir = ', '.join(t.name for t in found)
        raise TaskError(f'Hay mas de un {kind} en {root.name}: {elegir}. Elige uno.')
    return found[0]
