from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

"""
Ejecuta seeders base.

Flujo:
- Asegura que se ejecute con el Python del venv del servidor.
- Resuelve DATABASE_URL según RUN_REMOTE (scripts/.env; ver common.resolve_database_url).
- Carga configuración desde app.core.settings.
- Descubre funciones async que empiecen con seed_ dentro de seeders.
- Ejecuta en orden estable (módulos y funciones ordenadas), hace commit al final.
- Si algo falla: rollback y termina con exit code 1.
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


SeedFn = Callable[[AsyncSession], Awaitable[object]]


def _discover_seed_functions(package_name: str) -> list[tuple[str, str, SeedFn]]:
    package = importlib.import_module(package_name)
    if not hasattr(package, "__path__"):
        return []

    module_names = sorted(name for _, name, _ in pkgutil.walk_packages(package.__path__))
    discovered: list[tuple[str, str, SeedFn]] = []

    for module_name in module_names:
        full_module_name = f"{package_name}.{module_name}"
        module = importlib.import_module(full_module_name)
        for attr_name in sorted(dir(module)):
            if not attr_name.startswith("seed_"):
                continue
            candidate = getattr(module, attr_name)
            if not callable(candidate):
                continue
            if getattr(candidate, "__module__", None) != module.__name__:
                continue
            discovered.append((module_name, attr_name, candidate))

    return discovered


async def run() -> None:
    repo_root = _repo_root(Path(__file__).resolve())
    load_env_file(repo_root / "scripts" / ".env")
    server_root = repo_root / require_env("SERVER_DIR")
    venv_python(server_root / ".venv", restart=True)
    sys.path.append(str(server_root))

    database_url, tunnel = resolve_database_url(repo_root)
    os.environ["DATABASE_URL"] = database_url

    try:
        from app.core.settings import settings

        log("INFO", "Iniciando seeders base: seeders")
        try:
            seeds = _discover_seed_functions("seeders")
        except ModuleNotFoundError:
            log("WARN", "No existe el paquete seeders. Saltando.")
            return

        if not seeds:
            log("INFO", "No se encontraron funciones seed_ en seeders.")
            return

        engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as db:
                for module_name, func_name, func in seeds:
                    log("INFO", f"Ejecutando {func_name} ({module_name})...")
                    try:
                        await func(db)
                    except Exception as exc:
                        await db.rollback()
                        log("ERROR", f"Seeder falló: {module_name}.{func_name}: {exc}")
                        raise SystemExit(1) from exc
                await db.commit()
            log("OK", "Seeders base completados.")
        finally:
            await engine.dispose()
    finally:
        if tunnel is not None:
            tunnel.terminate()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
