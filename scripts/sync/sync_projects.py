



from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path

"""
Sincroniza archivos comunes entre repos.

Flujo:
1) Usa SOURCE como el directorio actual.
2) Expande rutas que terminen en / o \\ para incluir todos sus archivos.
3) Para cada TARGET, copia archivos nuevos o diferentes desde SOURCE.
4) Imprime el resumen.
"""

SOURCE = os.path.abspath(os.getcwd())

ONLY_REPLACE_EXISTING = False

ALLOWED_EXTENSIONS: list[str] = [".py"]

COMMON_TARGETS = [
    r"e:\Git\banditore",
    r"e:\Git\cadenza",
    r"e:\Git\forziere",
    r"e:\Git\navetta",
    r"e:\Git\parametri",
    r"e:\Git\presenze",
    r"e:\Git\spazio",
    r"e:\Git\vettore",
]

COMMON_PATHS = [
#    ".vscode/settings.json",
    "docs/api_response_standard.md",
    
    "scripts/",
    #"scripts/.env",

    "server/alembic/env.py",
    "server/alembic/script.py.mako",
    "server/app/models/base.py",
    "server/app/models/table_config.py",
    "server/app/schemas/base.py",

    "server/scripts/setup/",
    "server/scripts/inspect_db.py",    

    "server/.gitignore",
    "server/alembic.ini",

    ".gitignore",
]


def _matches_extension(file_path: Path, extensions: list[str]) -> bool:
    if not extensions:
        return True
    return file_path.suffix in extensions or file_path.name in extensions


def expand_paths(
    source: str,
    paths: list[str],
    extensions: list[str] = ALLOWED_EXTENSIONS,
) -> list[str]:
    result: set[str] = set()
    for rel_path in paths:
        if rel_path.endswith("/") or rel_path.endswith("\\"):
            cleaned = rel_path.rstrip("/\\")
            base_dir = Path(source) / cleaned
            if not base_dir.is_dir():
                continue
            for file_path in base_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if not _matches_extension(file_path, extensions):
                    continue
                rel = file_path.relative_to(Path(source)).as_posix()
                result.add(rel)
        else:
            result.add(rel_path)
    return sorted(result)


def get_status(src: str, dst: str) -> str:
    if not os.path.exists(src):
        return "MISSING_IN_SOURCE"
    if not os.path.exists(dst):
        return "MISSING_IN_DEST"
    if filecmp.cmp(src, dst, shallow=False):
        return "IDENTICAL"
    return "DIFFERENT"


def sync(
    targets: list[str],
    source: str,
    paths: list[str],
    only_replace_existing: bool = ONLY_REPLACE_EXISTING,
    extensions: list[str] = ALLOWED_EXTENSIONS,
) -> dict[str, int]:
    total = {
        "identical": 0,
        "different": 0,
        "missing_src": 0,
        "missing_dst": 0,
        "copied_new": 0,
        "overwritten": 0,
        "skipped_missing_dst": 0,
    }

    expanded = expand_paths(source, paths, extensions)
    source_abs = os.path.abspath(source)

    for target in targets:
        target_abs = os.path.abspath(target)
        if target_abs == source_abs or target_abs.startswith(source_abs + os.sep):
            print("\n" + "=" * 60)
            print(f"PROYECTO: {target}")
            print("=" * 60)
            print("  SKIP  (es la fuente o está dentro de ella)")
            continue

        print("\n" + "=" * 60)
        print(f"PROYECTO: {target}")
        print("=" * 60)

        for rel_path in expanded:
            src = os.path.join(source, rel_path)
            dst = os.path.join(target, rel_path)
            status = get_status(src, dst)

            if status == "IDENTICAL":
                total["identical"] += 1
                print(f"  OK    {rel_path}")
                continue

            if status == "MISSING_IN_SOURCE":
                total["missing_src"] += 1
                print(f"  SKIP  {rel_path} (no existe en fuente)")
                continue

            dst_dir = os.path.dirname(dst)
            if dst_dir:
                os.makedirs(dst_dir, exist_ok=True)

            if status == "MISSING_IN_DEST":
                total["missing_dst"] += 1
                if only_replace_existing:
                    total["skipped_missing_dst"] += 1
                    print(f"  SKIP  {rel_path} (no existe en destino, modo solo-reemplazo)")
                    continue
                print(f"  NEW   {rel_path}")
                shutil.copy2(src, dst)
                total["copied_new"] += 1
                print("        -> COPIADO")
                continue

            total["different"] += 1
            print(f"  DIFF  {rel_path}")
            shutil.copy2(src, dst)
            total["overwritten"] += 1
            print("        -> ACTUALIZADO")

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Identicos      : {total['identical']}")
    print(f"  Diferentes     : {total['different']}")
    print(f"  No en fuente   : {total['missing_src']}")
    print(f"  Nuevos copiados: {total['copied_new']}")
    print(f"  Sobrescritos   : {total['overwritten']}")
    print(f"  No en destino  : {total['missing_dst']}")
    if only_replace_existing:
        print(f"  Omitidos (solo-reemplazo): {total['skipped_missing_dst']}")
    return total


def _validate_paths(common_paths: list[str], exclusive_paths: list[str], case_name: str) -> None:
    duplicates = sorted(set(common_paths).intersection(exclusive_paths))
    if duplicates:
        raise ValueError(
            f"El caso '{case_name}' tiene rutas duplicadas entre comunes y exclusivas: {duplicates}"
        )


def run_case(
    case_name: str,
    source: str,
    targets: list[str],
    common_paths: list[str],
    exclusive_paths: list[str],
) -> dict[str, int]:
    if not source:
        raise ValueError(f"El caso '{case_name}' no tiene SOURCE definido")
    if not targets:
        raise ValueError(f"El caso '{case_name}' no tiene TARGETS definidos")

    _validate_paths(common_paths, exclusive_paths, case_name)
    paths = common_paths + exclusive_paths

    print("\n" + "#" * 60)
    print(f"CASO: {case_name}")
    print("#" * 60)
    return sync(targets, source, paths)


def run_common_only() -> None:
    print("\n" + "=" * 60)
    print("EJECUCION CENTRAL - SOLO GENERALES")
    print("=" * 60)
    sync(targets=COMMON_TARGETS, source=SOURCE, paths=COMMON_PATHS)


if __name__ == "__main__":
    run_common_only()
