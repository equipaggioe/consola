from __future__ import annotations
import json
import re
from pathlib import Path

from .errors import TaskError
from .files import read_text, write_text

# El modo tiene dos partes independientes: que componente SemVer subir
# (`major`/`minor`/`patch`/`none`) y si ademas incrementar el build number
# (`+build`). Se combinan: `patch+build`, `major+build`, etc. `build` a secas
# equivale a `none+build` — republicar el mismo X.Y.Z con codigo nuevo.
SEMVER_PARTS = ('major', 'minor', 'patch', 'none')
MODES = ('major', 'minor', 'patch', 'build', 'none')

# Cada manifiesto guarda la version en su propio formato; el resto del flujo
# no tiene por que enterarse de cual es (PLAN.md 2.2: bump_version es una sola
# atomica, no una por tipo de proyecto).
_PUBSPEC = re.compile(r'^(version:\s*)(\S+)\s*$', re.MULTILINE)
_PYPROJECT = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
_SEMVER = re.compile(r'^(\d+)\.(\d+)(?:\.(\d+))?(?:\+(\d+))?$')

MANIFEST_NAMES = ('pubspec.yaml', 'package.json', 'pyproject.toml')


def _parse_mode(mode: str) -> tuple[str, bool]:
    """`'patch+build'` -> `('patch', True)`. `'build'` -> `('none', True)`."""
    piezas = [p for p in (mode or 'patch').strip().lower().split('+') if p]
    if not piezas:
        piezas = ['patch']
    base = piezas[0]
    con_build = base == 'build' or 'build' in piezas[1:]
    if base == 'build':
        base = 'none'
    if base not in SEMVER_PARTS or any(p not in ('build',) for p in piezas[1:]):
        raise TaskError(f'Modo de bump invalido: {mode!r}. Usa {" | ".join(MODES)}, '
                        f'combinando "build" con los demas (p. ej. patch+build).')
    return base, con_build


def bump(version: str, mode: str) -> str:
    """Incrementa una version SemVer conservando el formato de entrada.

    El modo tiene dos partes que se combinan (ver `MODES`): el componente
    SemVer a subir y, con `+build`, el build number de Flutter (`1.4.22+318`).
    Son independientes a proposito: `patch` sube solo `X.Y.Z` y deja el codigo
    igual; `patch+build` sube los dos; `build` a secas republica el mismo
    `X.Y.Z` con codigo nuevo, que es lo que se pide cuando el cambio no le
    cambia nada al usuario.

    El build number solo existe en `pubspec.yaml`. Pedir `+build` sobre una
    version sin `+N` falla en vez de fingir que hizo algo.
    """
    base, con_build = _parse_mode(mode)
    if base == 'none' and not con_build:
        return version

    match = _SEMVER.match(version.strip())
    if not match:
        raise TaskError(f'La version no tiene formato SemVer: {version!r}')

    major, minor, patch, build = match.groups()
    major, minor = int(major), int(minor)
    patch = int(patch) if patch is not None else None

    if base == 'major':
        major, minor, patch = major + 1, 0, (0 if patch is not None else None)
    elif base == 'minor':
        minor, patch = minor + 1, (0 if patch is not None else None)
    elif base == 'patch':
        if patch is None:
            raise TaskError(f'{version!r} no tiene componente de parche para incrementar.')
        patch += 1

    if con_build and build is None:
        raise TaskError(
            f'{version!r} no tiene build number (+N): "+build" solo aplica a pubspec.yaml.')

    nueva = f'{major}.{minor}' if patch is None else f'{major}.{minor}.{patch}'
    if build is not None:
        nueva = f'{nueva}+{int(build) + (1 if con_build else 0)}'
    return nueva


def find_manifest(project_dir: Path) -> Path:
    """El manifiesto de version del subproyecto, sea del tipo que sea."""
    for name in MANIFEST_NAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise TaskError(f'No hay manifiesto de version en {project_dir}.')


def read_version(manifest: Path) -> str:
    if manifest.name == 'package.json':
        data = json.loads(read_text(manifest))
        version = str(data.get('version', '')).strip()
    elif manifest.name == 'pubspec.yaml':
        match = _PUBSPEC.search(read_text(manifest))
        version = match.group(2) if match else ''
    else:
        match = _PYPROJECT.search(read_text(manifest))
        version = match.group(2) if match else ''

    if not version:
        raise TaskError(f'No se encontro la version en {manifest.name}.')
    return version


def write_version(manifest: Path, version: str) -> None:
    """Escribe la version tocando solo esa linea: el resto del manifiesto queda igual."""
    if manifest.name == 'package.json':
        text = read_text(manifest)
        data = json.loads(text)
        data['version'] = version
        indent = 2 if text.startswith('{\n  ') else 4
        write_text(manifest, json.dumps(data, indent=indent, ensure_ascii=False) + '\n')
        return

    text = read_text(manifest)
    if manifest.name == 'pubspec.yaml':
        nuevo, hechos = _PUBSPEC.subn(lambda m: f'{m.group(1)}{version}', text, count=1)
    else:
        nuevo, hechos = _PYPROJECT.subn(lambda m: f'{m.group(1)}{version}{m.group(3)}', text, count=1)

    if not hechos:
        raise TaskError(f'No se pudo reescribir la version en {manifest.name}.')
    write_text(manifest, nuevo)
