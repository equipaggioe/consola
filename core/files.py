from __future__ import annotations
import filecmp
import hashlib
import os
import shutil
import tarfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator


@contextmanager
def reversible(path: Path) -> Iterator[None]:
    """Deja el archivo como estaba si el bloque falla o se cancela.

    Es el rollback del bump de version: si el build revienta despues de tocar
    `pubspec.yaml`, el repo no queda con una version que nunca se publico.
    """
    original = path.read_text(encoding='utf-8')
    try:
        yield
    except BaseException:
        path.write_text(original, encoding='utf-8', newline='\n')
        raise


def write_text(path: Path, content: str) -> None:
    """Escribe creando el directorio padre y con saltos de linea estables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace')


def compare(source: Path, target: Path) -> str:
    """Estado de un archivo frente a su copia: NEW, DIFF o SAME.

    Es el simulacro que exige PLAN.md 7.5: se muestra que va a cambiar antes de
    habilitar Aplicar, nunca se sobrescribe a ciegas.
    """
    if not target.exists():
        return 'NEW'
    if source.is_dir() or target.is_dir():
        return 'SAME' if _same_tree(source, target) else 'DIFF'
    return 'SAME' if filecmp.cmp(source, target, shallow=False) else 'DIFF'


def _same_tree(source: Path, target: Path) -> bool:
    left = {p.relative_to(source) for p in source.rglob('*') if p.is_file()}
    right = {p.relative_to(target) for p in target.rglob('*') if p.is_file()}
    if left != right:
        return False
    return all(filecmp.cmp(source / rel, target / rel, shallow=False) for rel in left)


def copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def collect(root: Path, patterns: Iterable[str]) -> list[Path]:
    """Rutas existentes que coinciden con los patrones, ordenadas y sin repetir.

    Lo usan los destructivos para armar la lista exacta de lo que van a borrar
    antes de pedir confirmacion.
    """
    found: set[Path] = set()
    for pattern in patterns:
        found.update(p for p in root.rglob(pattern) if p.exists())
    return sorted(found)


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def digest(path: Path, algorithm: str = 'sha256') -> str:
    """Huella del archivo, leyendolo por bloques.

    Una sola funcion con el algoritmo como parametro porque los dos SDK
    publican huellas distintas: Android da SHA-1 y Flutter SHA-256.
    """
    accumulator = hashlib.new(algorithm)
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            accumulator.update(chunk)
    return accumulator.hexdigest()


def extract(archive: Path, target: Path) -> Path:
    """Descomprime un .zip o un .tar.* preservando el bit de ejecucion.

    Los dos formatos hacen falta de verdad: Flutter publica .zip para Windows
    pero .tar.xz para Linux, y el script original abria todo con `zipfile`, con
    lo que en Linux no llegaba a descomprimir nada.
    """
    if archive.name.lower().endswith(('.tar.xz', '.tar.gz', '.tgz', '.tar.bz2')):
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as bundle:
            try:
                bundle.extractall(target, filter='data')
            except TypeError:  # Python anterior al filtro de extraccion
                bundle.extractall(target)
        return target
    return extract_zip(archive, target)


def extract_zip(archive: Path, target: Path) -> Path:
    """Descomprime un zip conservando los permisos Unix de cada entrada.

    `ZipFile.extractall` los descarta, y en Linux eso deja a `sdkmanager` y a
    `flutter` sin permiso de ejecucion: el zip se descomprime bien y despues
    nada arranca. Los modos viajan en los 16 bits altos de `external_attr`.
    """
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            extracted = Path(bundle.extract(info, target))
            mode = info.external_attr >> 16 & 0o7777
            if mode and os.name != 'nt':
                extracted.chmod(mode)
    return target


def human_size(total: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if total < 1024 or unit == 'GB':
            return f'{total:.0f} {unit}' if unit == 'B' else f'{total:.1f} {unit}'
        total /= 1024.0
    return f'{total:.1f} GB'
