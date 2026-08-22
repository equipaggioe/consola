from __future__ import annotations

import os
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root

"""
Limpia artefactos comunes del repo.

Flujo:
1) Calcula la raíz del repo (busca .git subiendo desde este archivo).
2) Recorre recursivamente y, según la configuración y el modo (simulación/borrado), identifica y procesa:
3) Loguea cada elemento procesado.
4) Imprime el resumen de la operación.
"""

dry_run = False
excluded_dir_names = {".git"}


dir_names = {"__pycache__", ".gradle", ".kotlin", ".cxx"} # ".dart_tool",
file_names = {".flutter-plugins", ".flutter-plugins-dependencies", ".packages", "CMakeOutput.log"}
prefixes = {"hs_err_pid", "replay_pid"}
suffixes = {".pyc", ".pyo"}
suffixes_under = {".log": {"build"}}


def _match_file(file_path: Path) -> tuple[bool, str, str]:
    if file_path.name in file_names:
        return True, "name", file_path.name

    matched_prefix = next((p for p in prefixes if file_path.name.startswith(p)), None)
    if matched_prefix:
        return True, "prefix", matched_prefix

    suffix = file_path.suffix.lower()
    if suffix in suffixes:
        return True, "suffix", suffix

    scope = suffixes_under.get(suffix)
    if not scope:
        return False, "", ""

    if any(parent.name in scope for parent in file_path.parents):
        return True, "suffix_under", suffix

    return False, "", ""


def clean_artifacts(
    project_root: Path,
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    deleted_dirs = 0
    deleted_files = 0
    deleted_dirs_by_name: dict[str, int] = {}
    deleted_files_by_category: dict[str, int] = {}

    for root, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in excluded_dir_names]

        for dir_name in tuple(dirnames):
            if dir_name not in dir_names:
                continue
            target_dir = Path(root) / dir_name
            if dry_run:
                print(f"Simular eliminado directorio: {target_dir}")
                deleted_dirs += 1
                deleted_dirs_by_name[dir_name] = deleted_dirs_by_name.get(dir_name, 0) + 1
            else:
                try:
                    shutil.rmtree(target_dir)
                    print(f"Eliminado directorio: {target_dir}")
                    deleted_dirs += 1
                    deleted_dirs_by_name[dir_name] = deleted_dirs_by_name.get(dir_name, 0) + 1
                except Exception as exc:
                    print(f"Error eliminando {target_dir}: {exc}")
            dirnames.remove(dir_name)

        for name in filenames:
            file_path = Path(root) / name
            match, kind, label = _match_file(file_path)
            if not match:
                continue
            category = label if kind in {"name", "prefix"} else file_path.suffix.lower()
            if dry_run:
                print(f"Simular eliminado archivo: {file_path}")
                deleted_files += 1
                deleted_files_by_category[category] = deleted_files_by_category.get(category, 0) + 1
            else:
                try:
                    file_path.unlink(missing_ok=True)
                    print(f"Eliminado archivo: {file_path}")
                    deleted_files += 1
                    deleted_files_by_category[category] = deleted_files_by_category.get(category, 0) + 1
                except Exception as exc:
                    print(f"Error eliminando {file_path}: {exc}")

    return (
        deleted_dirs,
        deleted_files,
        deleted_dirs_by_name,
        deleted_files_by_category,
    )


def main() -> None:
    project_root = find_project_root(Path(__file__).resolve().parent)
    mode = "SIMULACION" if dry_run else "BORRADO"
    print(f"Iniciando limpieza de artefactos desde: {project_root} ({mode})")
    (
        deleted_dirs,
        deleted_files,
        deleted_dirs_by_name,
        deleted_files_by_category,
    ) = clean_artifacts(project_root)
    print("-" * 30)
    print("Limpieza completada.")
    print(f"Directorios eliminados: {deleted_dirs}")
    print(f"Archivos eliminados: {deleted_files}")
    print("-" * 30)
    for dir_name, count in sorted(deleted_dirs_by_name.items()):
        print(f"Directorios '{dir_name}': {count}")
    for category, count in sorted(deleted_files_by_category.items()):
        print(f"Archivos '{category}': {count}")


if __name__ == "__main__":
    main()

