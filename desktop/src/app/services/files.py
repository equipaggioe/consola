"""Compare, copy, delete and revert files."""

from __future__ import annotations

import filecmp
import hashlib
import shutil
import tarfile
import zipfile
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QLocale

from app.services.host import HOST


@contextmanager
def reversible(path: Path) -> Generator[None]:
    """Leave the file as it was if the block fails or is cancelled.

    It is the version bump's rollback: if the build dies after touching
    `pubspec.yaml`, the repo does not stay with a version that was never
    published.
    """
    original = path.read_text(encoding="utf-8")
    try:
        yield
    except BaseException:
        path.write_text(original, encoding="utf-8", newline="\n")
        raise


def write_text(path: Path, content: str) -> None:
    """Write, creating the parent folder, with stable line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def read_text(path: Path) -> str:
    """Return the file's text."""
    return path.read_text(encoding="utf-8", errors="replace")


def compare(source: Path, target: Path) -> str:
    """Return a file's state against its copy: NEW, DIFF or SAME.

    It is the dry run ADR-0039 demands: it shows what will change before
    enabling Apply and never overwrites blindly.
    """
    if not target.exists():
        return "NEW"
    if source.is_dir() or target.is_dir():
        return "SAME" if _same_tree(source, target) else "DIFF"
    return "SAME" if filecmp.cmp(source, target, shallow=False) else "DIFF"


def _same_tree(source: Path, target: Path) -> bool:
    left = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}
    right = {p.relative_to(target) for p in target.rglob("*") if p.is_file()}
    if left != right:
        return False
    return all(filecmp.cmp(source / rel, target / rel, shallow=False) for rel in left)


def copy(source: Path, target: Path) -> None:
    """Copy a file, creating the target's folder."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def collect(root: Path, patterns: Iterable[str]) -> list[Path]:
    """Return the existing paths that match, sorted and without repeats.

    Destructive tasks use it to build the exact list of what they will
    delete before asking for confirmation.
    """
    found: set[Path] = set()
    for pattern in patterns:
        found.update(p for p in root.rglob(pattern) if p.exists())
    return sorted(found)


def size_of(path: Path) -> int:
    """Return the size of a file or of a whole folder."""
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def remove(path: Path) -> None:
    """Delete a file or a whole folder."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def digest(path: Path) -> str:
    """Return the file's SHA-256, reading it by blocks."""
    accumulator = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            accumulator.update(chunk)
    return accumulator.hexdigest()


def extract(archive: Path, target: Path) -> Path:
    """Extract a .zip or a .tar.*, keeping the execute bit.

    Both formats are truly needed: Flutter publishes .zip for Windows
    and .tar.xz for Linux.
    """
    if archive.name.lower().endswith((".tar.xz", ".tar.gz", ".tgz", ".tar.bz2")):
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as bundle:
            try:
                bundle.extractall(target, filter="data")
            # a Python older than the extraction filter
            except TypeError:
                bundle.extractall(target)
        return target
    return extract_zip(archive, target)


def extract_zip(archive: Path, target: Path) -> Path:
    """Extract a zip, keeping each entry's Unix permissions.

    `ZipFile.extractall` discards them, and on Linux that leaves
    `sdkmanager` and `flutter` unable to execute: the zip extracts fine
    and then nothing starts. The modes travel in the 16 high bits of
    `external_attr`.
    """
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            extracted = Path(bundle.extract(info, target))
            mode = info.external_attr >> 16 & 0o7777
            if mode and HOST.unix_modes:
                extracted.chmod(mode)
    return target


def human_size(size: int, locale: QLocale) -> str:
    """Return a size in bytes as readable text, in `locale`."""
    return locale.formattedDataSize(size, 1, QLocale.DataSizeFormat.DataSizeTraditionalFormat)
