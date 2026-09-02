from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import TaskError
from .files import read_text

SPA_VITE = 'spa-vite'
FLUTTER_APP = 'flutter-app'
FLET_APP = 'flet-app'
FASTAPI = 'fastapi-server'
# App de escritorio en Python con su propio venv (la terminal de navetta). Es
# un tipo aparte y no `FASTAPI` porque no sirve HTTP: se lanza y abre su ventana.
PYTHON_APP = 'python-app'

# "La app movil" es una sola cosa del dominio aunque este escrita en Flutter o
# en Flet: se compila igual, se sube igual y se corre en el mismo emulador. El
# framework es una propiedad de la carpeta, no una eleccion de quien aprieta el
# boton, asi que los dos tipos viajan juntos en todos los ejes que la nombran.
MOBILE_APP = (FLUTTER_APP, FLET_APP)

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
    # Ultimo porque es el marcador mas debil: `src/main.py` lo tiene tambien
    # algun servidor, y ese ya se reconocio arriba.
    if (directory / 'src' / 'main.py').is_file():
        return PYTHON_APP
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


def by_kinds(root: Path, kinds: Sequence[str]) -> list[Target]:
    """Los subproyectos de cualquiera de esos tipos, en una sola pasada."""
    wanted = set(kinds)
    return [t for t in discover(root) if t.kind in wanted]


def by_kind(root: Path, kind: str) -> list[Target]:
    return by_kinds(root, (kind,))


def names_of(root: Path, kinds: Sequence[str]) -> list[str]:
    """Los valores que toma un eje descubierto, listos para el panel de parametros.

    Ordenados por nombre y no por tipo: para quien elige, la lista es de apps,
    y que las de Flet salgan antes que las de Flutter no le dice nada.
    """
    return sorted(t.name for t in by_kinds(root, kinds))


def names(root: Path, kind: str) -> list[str]:
    return names_of(root, (kind,))


def pick(root: Path, kinds: Sequence[str], name: str = '') -> Target:
    """El subproyecto elegido por nombre, o el unico que haya de esos tipos.

    Es la contraparte de `names_of`: el panel ofrece esos nombres y esto
    resuelve el elegido. Sin nombre cae en "el unico", que es el caso de casi
    todos los repos y evita pedir una eleccion que no existe.
    """
    found = by_kinds(root, kinds)
    etiqueta = ' o '.join(kinds)
    if name:
        for target in found:
            if target.name == name:
                return target
        raise TaskError(f'No hay ningun {etiqueta} llamado "{name}" en {root.name}.')
    if not found:
        raise TaskError(f'{root.name} no tiene ningun subproyecto de tipo {etiqueta}.')
    if len(found) > 1:
        elegir = ', '.join(t.name for t in found)
        raise TaskError(f'Hay mas de un {etiqueta} en {root.name}: {elegir}. Elige uno.')
    return found[0]


def find(root: Path, kind: str, name: str) -> Target:
    return pick(root, (kind,), name)


def only(root: Path, kind: str) -> Target:
    """El unico subproyecto de ese tipo. Falla si hay cero o mas de uno."""
    return pick(root, (kind,))
