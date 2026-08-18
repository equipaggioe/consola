from __future__ import annotations

import os
import shutil
from pathlib import Path

"""
Limpia artefactos de Python.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Recorre recursivamente y elimina directorios __pycache__.
3) Elimina archivos .pyc y .pyo sueltos.
4) Imprime el resumen.
"""


def clean_pycache(project_root: Path) -> tuple[int, int]:
    deleted_dirs = 0
    deleted_files = 0

    for root, dirs, files in os.walk(project_root):
        if "__pycache__" in dirs:
            pycache_path = Path(root) / "__pycache__"
            try:
                shutil.rmtree(pycache_path)
                print(f"Eliminado directorio: {pycache_path}")
                deleted_dirs += 1
            except Exception as exc:
                print(f"Error eliminando {pycache_path}: {exc}")
            dirs.remove("__pycache__")

        for name in files:
            if not (name.endswith(".pyc") or name.endswith(".pyo")):
                continue
            file_path = Path(root) / name
            try:
                file_path.unlink(missing_ok=True)
                print(f"Eliminado archivo: {file_path}")
                deleted_files += 1
            except Exception as exc:
                print(f"Error eliminando {file_path}: {exc}")

    return deleted_dirs, deleted_files


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    print(f"Iniciando limpieza de __pycache__ y .pyc desde: {project_root}")
    deleted_dirs, deleted_files = clean_pycache(project_root)
    print("-" * 30)
    print("Limpieza completada.")
    print(f"Directorios __pycache__ eliminados: {deleted_dirs}")
    print(f"Archivos .pyc/.pyo eliminados: {deleted_files}")


if __name__ == "__main__":
    main()
