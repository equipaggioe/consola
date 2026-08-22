from __future__ import annotations

import ast
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

"""
Genera y aplica una migracion incremental de Alembic, sin borrar nada:

- Resuelve DATABASE_URL según RUN_REMOTE (scripts/.env; ver common.resolve_database_url).
- Corre `alembic revision --autogenerate -m "<mensaje>"` (agrega un archivo
  nuevo en alembic/versions/, no toca los existentes).
- Corre `alembic upgrade head`.

Uso:
- python migrate_db.py "mensaje de la migracion"
- python migrate_db.py                          (autogenera el mensaje: auto_migration_<fecha_hora>)
"""


def _repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("No se encontró la raíz del repo (.git).")


sys.path.insert(0, str(_repo_root(Path(__file__).resolve()) / "scripts"))
from common import load_env_file, require_env, resolve_database_url, venv_python


def log(stage: str, message: str) -> None:
    print(f"[{stage}] {message}")


def _is_noop_migration(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade")
    }

    if set(functions) != {"upgrade", "downgrade"}:
        return False

    return all(
        len(node.body) == 1 and isinstance(node.body[0], ast.Pass)
        for node in functions.values()
    )


def _generate_revision(server_root: Path, message: str) -> Path | None:
    log("INFO", f"Generando migracion: {message!r}...")
    before = {p.name for p in (server_root / "alembic" / "versions").glob("*.py")}

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", message],
        cwd=server_root,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        log("ERROR", "Fallo la generacion de la migracion.")
        raise SystemExit(1)

    after = {p.name for p in (server_root / "alembic" / "versions").glob("*.py")}
    new_files = after - before
    if not new_files:
        log("ERROR", "Alembic no genero ningun archivo nuevo (¿no hay cambios de esquema?).")
        raise SystemExit(1)

    generated = server_root / "alembic" / "versions" / new_files.pop()

    if _is_noop_migration(generated):
        generated.unlink()
        log("OK", "No hay cambios de esquema, no se genera ninguna migracion.")
        return None

    log("OK", f"Migracion generada: {generated}")
    return generated


def _upgrade_head(server_root: Path) -> None:
    log("INFO", "Aplicando migracion a head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=server_root,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        log("ERROR", "Fallo alembic upgrade head.")
        raise SystemExit(1)
    log("OK", "Migracion aplicada.")


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit(
            f'Uso: {Path(sys.argv[0]).name} ["mensaje de la migracion"]'
        )

    if len(sys.argv) == 2 and sys.argv[1].strip():
        message = sys.argv[1].strip()
    else:
        message = f"auto_migration_{datetime.now():%Y%m%d_%H%M%S}"

    repo_root = _repo_root(Path(__file__).resolve())
    load_env_file(repo_root / "scripts" / ".env")
    server_root = repo_root / require_env("SERVER_DIR")

    venv_python(server_root / ".venv", restart=True)

    database_url, tunnel = resolve_database_url(repo_root)
    os.environ["DATABASE_URL"] = database_url

    try:
        generated = _generate_revision(server_root, message)
        _upgrade_head(server_root)

        if generated is not None:
            log("OK", f"Listo. Revisa y comitea: {generated.relative_to(server_root.parent)}")
    finally:
        if tunnel is not None:
            tunnel.terminate()


if __name__ == "__main__":
    main()
