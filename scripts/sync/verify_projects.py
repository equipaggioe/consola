from __future__ import annotations

import hashlib
import os
from datetime import datetime

from sync_projects import COMMON_PATHS, COMMON_TARGETS, SOURCE, expand_paths

"""
Verifica que los archivos comunes estén iguales entre repos.

Flujo:
1) Expande rutas a verificar (igual que sync_projects).
2) Calcula SHA256 de cada archivo en SOURCE.
3) Compara contra cada TARGET.
4) Imprime OK/DIFF y al final un resumen + agrupación por versión para los diferentes.
"""

MISSING_VERSION_KEY = "__MISSING__"


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(targets: list[str], source: str, paths: list[str]) -> dict[str, int]:
    total = {"identical": 0, "different": 0, "missing_src": 0, "missing_dst": 0}
    versions_by_path: dict[str, dict[str, dict[str, set[object]]]] = {}
    has_diff_by_path: dict[str, bool] = {}

    expanded_paths = expand_paths(source, paths)
    source_abs = os.path.abspath(source)
    source_name = os.path.basename(source_abs.rstrip("\\/")) or source_abs
    source_label = f"{source_name} (fuente)"

    valid_targets: list[str] = []
    for target in targets:
        target_abs = os.path.abspath(target)
        if target_abs == source_abs or target_abs.startswith(source_abs + os.sep):
            continue
        valid_targets.append(target_abs)

    for rel_path in expanded_paths:
        src = os.path.join(source_abs, rel_path)
        if not os.path.exists(src):
            total["missing_src"] += 1
            print(f"  SKIP  {rel_path} (no existe en fuente)")
            continue

        src_hash = _file_hash(src)
        src_mtime = os.path.getmtime(src)
        versions: dict[str, dict[str, set[object]]] = {
            src_hash: {"projects": {source_label}, "mtimes": {src_mtime}},
        }
        has_any_diff = False
        has_any_missing_dst = False

        for target_abs in valid_targets:
            dst = os.path.join(target_abs, rel_path)
            target_name = os.path.basename(target_abs.rstrip("\\/")) or target_abs

            if not os.path.exists(dst):
                has_any_missing_dst = True
                missing_group = versions.setdefault(
                    MISSING_VERSION_KEY, {"projects": set(), "mtimes": set()}
                )
                missing_group["projects"].add(target_name)
                continue

            dst_hash = _file_hash(dst)
            dst_mtime = os.path.getmtime(dst)
            dst_group = versions.setdefault(dst_hash, {"projects": set(), "mtimes": set()})
            if target_name != source_name:
                dst_group["projects"].add(target_name)
            dst_group["mtimes"].add(dst_mtime)

            if dst_hash != src_hash:
                has_any_diff = True

        if has_any_diff or has_any_missing_dst:
            total["different"] += 1
            if has_any_missing_dst:
                total["missing_dst"] += 1
            has_diff_by_path[rel_path] = True
            versions_by_path[rel_path] = versions
            print(f"  DIFF  {rel_path}")
        else:
            total["identical"] += 1
            print(f"  OK    {rel_path}")

    print("\n" + "=" * 60)
    print("RESUMEN VERIFICACION")
    print("=" * 60)
    print(f"  Identicos     : {total['identical']}")
    print(f"  Diferentes    : {total['different']}")
    print(f"  No en fuente  : {total['missing_src']}")
    print(f"  No en destino : {total['missing_dst']}")

    diff_paths = [p for p in expanded_paths if has_diff_by_path.get(p)]
    if diff_paths:
        print("\n" + "=" * 60)
        print("AGRUPACION POR VERSION (SOLO DIFERENTES)")
        print("=" * 60)
        for rel_path in diff_paths:
            print(f"\n  {rel_path}")
            versions = versions_by_path.get(rel_path, {})
            ordered_versions = sorted(
                versions.items(),
                key=lambda item: (
                    1 if item[0] == MISSING_VERSION_KEY else 0,
                    min(item[1]["mtimes"]) if item[1]["mtimes"] else float("inf"),
                ),
            )
            for version_key, group_data in ordered_versions:
                ordered_projects = ", ".join(sorted(group_data["projects"]))  # type: ignore[arg-type]
                oldest_mtime = min(group_data["mtimes"]) if group_data["mtimes"] else None
                label = (
                    datetime.fromtimestamp(oldest_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    if oldest_mtime is not None
                    else "sin_fecha"
                )
                if version_key == MISSING_VERSION_KEY:
                    label = "NO_EXISTE"
                print(f"    {label}: {ordered_projects}")

    return total


if __name__ == "__main__":
    verify(targets=COMMON_TARGETS, source=SOURCE, paths=COMMON_PATHS)
