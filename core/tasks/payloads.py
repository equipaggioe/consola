from __future__ import annotations
import tempfile
from pathlib import Path

from ..errors import TaskError
from ..toolchain import venv_python

"""
La unica excepcion deliberada a "nada de subprocesos a codigo Python".

Los seeders y el mantenimiento de particiones no son operaciones sobre la base:
son *codigo del proyecto* (`seeders/`, `mock_data/`, `app.services.maintenance`)
que solo se puede importar desde el venv del servidor, con sus dependencias y
sus modelos. Consola no puede importarlos con su propio interprete, asi que
lanza estos programas cortos con el Python del venv del proyecto.

No son scripts del repo gestionado: viven aca, hay una sola copia, y se escriben
a un archivo temporal en cada corrida para que sigan funcionando cuando Consola
este empaquetada con PyInstaller y no exista como archivos sueltos en disco.
"""

SEED = '''
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
'''

PARTITIONS = '''
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
'''

SOURCES = {'seed': SEED, 'partitions': PARTITIONS}


def run(ctx, source: str, *args: str, server_root: Path, database_url: str) -> int:
    """Ejecuta un payload con el Python del venv del servidor.

    `cwd` es la carpeta del servidor y `DATABASE_URL` viaja por el entorno del
    subproceso, nunca escrito a un archivo: es el mismo dato que ya resolvio
    la tarea que llama, no una segunda resolucion (ni un segundo tunel).
    """
    if source not in SOURCES:
        raise TaskError(f'Payload desconocido: {source!r}')

    interprete = venv_python(server_root / '.venv')
    with tempfile.TemporaryDirectory(prefix='consola_') as tmp:
        archivo = Path(tmp) / f'{source}.py'
        archivo.write_text(SOURCES[source], encoding='utf-8', newline='\n')
        return ctx.run([str(interprete), str(archivo), *args],
                       cwd=server_root, env={'DATABASE_URL': database_url})
