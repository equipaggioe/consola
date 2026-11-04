"""The one deliberate exception to «no subprocesses into Python code».

Seeders and partition maintenance are not operations on the database:
they are *project code* (`seeders/`, `mock_data/`,
`app.services.maintenance`) that can only be imported from the server's
venv, with its dependencies and models. Consola cannot import them with
its own interpreter, so it launches these short programs with the
project's Python (`core/runner.py`).

They are not scripts of the managed repo: they live here, there is one
copy, and they enter as `python -c <source>`. They never touch a disk:
not this one, since a packaged Consola does not exist as loose files,
and not the VPS's, which need not receive a file to run something its
own venv can execute.
"""

from __future__ import annotations

from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.runner import Runner

SEED = """
import asyncio, importlib, os, pkgutil, sys

package_name = sys.argv[1]
sys.path.insert(0, os.getcwd())

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.settings import settings


def discover(name):
    package = importlib.import_module(name)
    if not hasattr(package, "__path__"):
        return []
    found = []
    for module_name in sorted(n for _, n, _ in pkgutil.walk_packages(package.__path__)):
        module = importlib.import_module(f"{name}.{module_name}")
        for attr in sorted(dir(module)):
            if not attr.startswith("seed_"):
                continue
            fn = getattr(module, attr)
            if callable(fn) and getattr(fn, "__module__", None) == module.__name__:
                found.append((module_name, attr, fn))
    return found


async def main():
    try:
        seeds = discover(package_name)
    except ModuleNotFoundError:
        print(f"[WARN] No existe el paquete {package_name}. Se saltea.")
        return
    if not seeds:
        print(f"[INFO] No hay funciones seed_ en {package_name}.")
        return

    engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            for module_name, attr, fn in seeds:
                print(f"[INFO] {package_name}.{module_name}.{attr}")
                try:
                    await fn(db)
                except Exception as exc:
                    await db.rollback()
                    print(f"[ERROR] Fallo {module_name}.{attr}: {exc}")
                    raise SystemExit(1)
            await db.commit()
        print(f"[OK] {len(seeds)} seeder(s) de {package_name} aplicados.")
    finally:
        await engine.dispose()


asyncio.run(main())
"""

PARTITIONS = """
import asyncio, os, sys

sys.path.insert(0, os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine
from app.core.settings import settings


async def main():
    try:
        from app.services.maintenance import maintain_partitions
    except ModuleNotFoundError:
        print("[WARN] app.services.maintenance no existe: se saltea el paso.")
        return

    engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
    try:
        ensured, stuck = await maintain_partitions(engine)
        print(f"[OK] Particiones aseguradas: {', '.join(ensured)}")
        if stuck:
            print(f"[ERROR] {stuck} fila(s) atascadas en una particion DEFAULT.")
            raise SystemExit(1)
    finally:
        await engine.dispose()


asyncio.run(main())
"""

SOURCES = {"seed": SEED, "partitions": PARTITIONS}


def run(ctx: TaskContext, runner: Runner, source: str, *args: str) -> int:
    """Run a payload with the project's Python, where the runner says.

    Payloads need not know where they run: all they take from the
    environment is the working directory, which gives the `sys.path`
    that lets them import `app.` and `seeders.`, and `DATABASE_URL`. The
    `Runner` sets both, so the same text works here and on the VPS.

    The log shows a summary and not the real argv: `-c` carries the
    whole program as one argument, and dumping it would be fifty lines
    of code hiding the seeder's output.
    """
    if source not in SOURCES:
        raise TaskError(f"Payload desconocido: {source!r}")

    runner.log_command(ctx, " ".join(["-c", f"<{source}>", *args]))
    return runner.run(ctx, "-c", SOURCES[source], *args, echo=False)
