"""Read and bump the version of a manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.errors import TaskError
from app.core.files import read_text, write_text

# The mode has two independent parts: which SemVer component to bump
# (`major`, `minor`, `patch`, `none`) and whether to also increment the
# build number (`+build`). They combine: `patch+build`, `major+build`. A
# bare `build` equals `none+build`: republish the same X.Y.Z with new
# code.
SEMVER_PARTS = ("major", "minor", "patch", "none")
MODES = ("major", "minor", "patch", "build", "none")

# Each manifest keeps the version in its own format; the rest of the
# flow need not know which (ADR-0004: bump_version is one atomic
# capability, not one per project type).
_PUBSPEC = re.compile(r"^(version:\s*)(\S+)\s*$", re.MULTILINE)
_PYPROJECT = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
_SEMVER = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:\+(\d+))?$")

MANIFEST_NAMES = ("pubspec.yaml", "package.json", "pyproject.toml")


def _parse_mode(mode: str) -> tuple[str, bool]:
    """`'patch+build'` -> `('patch', True)`.

    `'build'` -> `('none', True)`.
    """
    pieces = [p for p in (mode or "patch").strip().lower().split("+") if p]
    if not pieces:
        pieces = ["patch"]
    base = pieces[0]
    con_build = base == "build" or "build" in pieces[1:]
    if base == "build":
        base = "none"
    if base not in SEMVER_PARTS or any(p not in ("build",) for p in pieces[1:]):
        raise TaskError(
            f"Modo de bump invalido: {mode!r}. Usa {' | '.join(MODES)}, "
            f'combinando "build" con los demas (p. ej. patch+build).'
        )
    return base, con_build


def bump(version: str, mode: str) -> str:
    """Bump a SemVer version, keeping the input format.

    The mode has two parts that combine (see `MODES`): the SemVer
    component to bump and, with `+build`, Flutter's build number
    (`1.4.22+318`). They are independent on purpose: `patch` only bumps
    `X.Y.Z`; `patch+build` bumps both; a bare `build` republishes the
    same `X.Y.Z` with new code, for a change the user does not see.

    The build number only exists in `pubspec.yaml`. Asking for `+build`
    on a version without `+N` fails instead of pretending to do
    something.
    """
    base, con_build = _parse_mode(mode)
    if base == "none" and not con_build:
        return version

    match = _SEMVER.match(version.strip())
    if not match:
        raise TaskError(f"La version no tiene formato SemVer: {version!r}")

    major, minor, patch, build = match.groups()
    major, minor = int(major), int(minor)
    patch = int(patch) if patch is not None else None

    if base == "major":
        major, minor, patch = major + 1, 0, (0 if patch is not None else None)
    elif base == "minor":
        minor, patch = minor + 1, (0 if patch is not None else None)
    elif base == "patch":
        if patch is None:
            raise TaskError(f"{version!r} no tiene componente de parche para incrementar.")
        patch += 1

    if con_build and build is None:
        raise TaskError(
            f'{version!r} no tiene build number (+N): "+build" solo aplica a pubspec.yaml.'
        )

    new = f"{major}.{minor}" if patch is None else f"{major}.{minor}.{patch}"
    if build is not None:
        new = f"{new}+{int(build) + (1 if con_build else 0)}"
    return new


def find_manifest(project_dir: Path) -> Path:
    """Return the subproject's version manifest, of whichever type."""
    for name in MANIFEST_NAMES:
        candidate = project_dir / name
        if candidate.is_file():
            return candidate
    raise TaskError(f"No hay manifiesto de version en {project_dir}.")


def read_version(manifest: Path) -> str:
    """Return the version written in the manifest."""
    if manifest.name == "package.json":
        data = json.loads(read_text(manifest))
        version = str(data.get("version", "")).strip()
    elif manifest.name == "pubspec.yaml":
        match = _PUBSPEC.search(read_text(manifest))
        version = match.group(2) if match else ""
    else:
        match = _PYPROJECT.search(read_text(manifest))
        version = match.group(2) if match else ""

    if not version:
        raise TaskError(f"No se encontro la version en {manifest.name}.")
    return version


def write_version(manifest: Path, version: str) -> None:
    """Write the version touching only that line of the manifest."""
    if manifest.name == "package.json":
        text = read_text(manifest)
        data = json.loads(text)
        data["version"] = version
        indent = 2 if text.startswith("{\n  ") else 4
        write_text(manifest, json.dumps(data, indent=indent, ensure_ascii=False) + "\n")
        return

    text = read_text(manifest)
    if manifest.name == "pubspec.yaml":
        new, done = _PUBSPEC.subn(lambda m: f"{m.group(1)}{version}", text, count=1)
    else:
        new, done = _PYPROJECT.subn(lambda m: f"{m.group(1)}{version}{m.group(3)}", text, count=1)

    if not done:
        raise TaskError(f"No se pudo reescribir la version en {manifest.name}.")
    write_text(manifest, new)
