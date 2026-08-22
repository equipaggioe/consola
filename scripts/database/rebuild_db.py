from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

"""
Reconstruye la base de datos:

- Resuelve DATABASE_URL según RUN_REMOTE (scripts/.env; ver common.resolve_database_url).
- Borra tablas del esquema public (excepto spatial_ref_sys).
- Resetea migraciones de Alembic: borra versiones, autogenera initial_migration y aplica upgrade head.
- Puede ejecutar seeders base y mock (scripts/database/run_seeders.py y scripts/database/run_mock_seeders.py).
  Como DATABASE_URL ya queda seteado en el entorno de este proceso, esos subprocesos lo heredan
  y no vuelven a resolverlo (no abren un segundo túnel).
"""

run_seeders = True
run_mock_seeders = True
# `message` y `message_attachment` son particionadas; autogenerate no genera sus particiones
# (ni siquiera la DEFAULT), así que sin este paso el primer INSERT revienta con "no partition of
# relation found for row" en cuanto un seeder toque mensajes. Ver docs/plan.md, "Notas de decisión".
run_partitions = True


def _repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("No se encontró la raíz del repo (.git).")


sys.path.insert(0, str(_repo_root(Path(__file__).resolve()) / "scripts"))
from common import load_env_file, require_env, resolve_database_url, venv_python


def log(stage: str, message: str) -> None:
    print(f"[{stage}] {message}")


async def _clean_public_schema(engine: AsyncEngine) -> None:
    log("INFO", "Limpiando base de datos (esquema public)...")
    async with engine.connect() as conn:
        tables = (await conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename <> 'spatial_ref_sys'
                ORDER BY tablename
                """
            )
        )).scalars().all()

        if not tables:
            log("INFO", "No se encontraron tablas para eliminar.")
            await conn.commit()
            return

        for table in tables:
            await conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}" CASCADE;')
            log("OK", f"Tabla eliminada: {table}")
        await conn.commit()
    log("OK", "Base de datos limpia.")


def _reset_alembic_migrations(server_root: Path) -> None:
    migrations_dir = server_root / "alembic" / "versions"
    log("INFO", f"Reseteando migraciones en: {migrations_dir}")

    migrations_dir.mkdir(parents=True, exist_ok=True)
    for migration_file in sorted(migrations_dir.glob("*.py")):
        migration_file.unlink()
        log("OK", f"Migración eliminada: {migration_file.name}")

    log("INFO", "Generando migración inicial...")
    revision = subprocess.run(
        [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "initial_migration"],
        cwd=server_root,
        capture_output=True,
        text=True,
    )
    if revision.returncode != 0:
        log("ERROR", "Falló generación de migración.")
        if revision.stdout.strip():
            print(revision.stdout.strip())
        if revision.stderr.strip():
            print(revision.stderr.strip())
        raise SystemExit(1)
    if revision.stdout.strip():
        print(revision.stdout.strip())
    log("OK", "Migración inicial generada.")

    log("INFO", "Aplicando migración a head...")
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=server_root,
        capture_output=True,
        text=True,
    )
    if upgrade.returncode != 0:
        log("ERROR", "Falló alembic upgrade head.")
        if upgrade.stdout.strip():
            print(upgrade.stdout.strip())
        if upgrade.stderr.strip():
            print(upgrade.stderr.strip())
        raise SystemExit(1)
    if upgrade.stdout.strip():
        print(upgrade.stdout.strip())
    log("OK", "Migración aplicada a head.")


def _run_setup_script(server_root: Path, script_path: Path) -> None:
    if not script_path.exists():
        log("ERROR", f"No existe el script: {script_path}")
        raise SystemExit(1)

    log("INFO", f"Ejecutando: {script_path.name}")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=server_root,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        log("ERROR", f"Falló el script: {script_path.name}")
        raise SystemExit(result.returncode)


async def run() -> None:
    setup_dir = Path(__file__).resolve().parent
    repo_root = _repo_root(setup_dir)
    load_env_file(repo_root / "scripts" / ".env")
    server_root = repo_root / require_env("SERVER_DIR")

    venv_python(server_root / ".venv", restart=True)
    sys.path.append(str(server_root))

    database_url, tunnel = resolve_database_url(repo_root)
    os.environ["DATABASE_URL"] = database_url

    try:
        from app.core.settings import settings

        log("INFO", f"Servidor raíz: {server_root}")
        engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
        try:
            await _clean_public_schema(engine)
            _reset_alembic_migrations(server_root)
            if run_partitions:
                try:
                    from app.services.maintenance import maintain_partitions
                except ModuleNotFoundError:
                    log("WARN", "app.services.maintenance no existe todavía: se saltea el manejo de particiones.")
                else:
                    log("INFO", "Asegurando particiones de message/message_attachment...")
                    ensured, stuck = await maintain_partitions(engine)
                    log("OK", f"Particiones aseguradas: {', '.join(ensured)}")
                    if stuck:
                        log("ERROR", f"{stuck} fila(s) atascadas en alguna partición DEFAULT.")
                        raise SystemExit(1)
            if run_seeders:
                _run_setup_script(server_root, setup_dir / "run_seeders.py")
            if run_mock_seeders:
                _run_setup_script(server_root, setup_dir / "run_mock_seeders.py")
            log("OK", "Reconstrucción finalizada.")
        except SystemExit:
            raise
        except Exception as exc:
            log("ERROR", f"Proceso detenido: {exc}")
            raise SystemExit(1) from exc
        finally:
            await engine.dispose()
    finally:
        if tunnel is not None:
            tunnel.terminate()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
