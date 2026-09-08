from __future__ import annotations
from datetime import datetime
from pathlib import Path

from . import payloads
from .. import database as db
from .. import files, ssh, vps
from ..errors import TaskError
from ..registry import registry
from ..toolchain import venv_python

"""
Grupo Base de datos (operaciones).

`rebuild_db.py` era un solo archivo que borraba tablas, reseteaba Alembic,
regeneraba la migracion inicial, aseguraba particiones y corria dos tandas de
seeders. Si solo hacia falta volver a correr los seeders mock habia que rehacer
todo, incluida la destruccion del esquema.

Aca cada uno de esos pasos es una atomica con boton propio, y `rebuild_db` es
la compuesta que los encadena. Lo mismo con `bootstrap_db` (crear rol, crear
base, permisos, extensiones, migrar) y `teardown_db` (borrar base, borrar rol).
"""

SERVER_DIR = 'SERVER_DIR'
BACKUP_DIR = '.backups'


def _server_root(ctx) -> Path:
    root = ctx.root / ctx.config.get(SERVER_DIR, 'server')
    if not root.is_dir():
        raise TaskError(f'No existe la carpeta del servidor: {root}')
    return root


def _alembic(ctx, conn: db.Connection, *args: str) -> int:
    """Corre Alembic con el Python del venv del servidor.

    Alembic necesita importar los modelos del proyecto para el autogenerate, y
    esos modelos solo existen en el venv del servidor: no hay forma de correrlo
    con el interprete de Consola.
    """
    server = _server_root(ctx)
    interprete = venv_python(server / '.venv')
    return ctx.run([str(interprete), '-m', 'alembic', *args],
                   cwd=server, env={'DATABASE_URL': conn.url})


# --- ciclo de vida del esquema ---------------------------------------------

def create_role(ctx, scope: str = db.LOCAL) -> str:
    """Crea el rol de la aplicacion, o le actualiza la contrasena si ya existe."""
    admin = db.resolve_admin(ctx, scope)
    user, password, _ = db.credentials(ctx.config)
    ctx.guard(password)

    ident, literal = db.quote_ident(user), db.quote_literal(user)
    admin.execute(ctx, (
        'DO $$ BEGIN '
        f'IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {literal}) THEN '
        f"EXECUTE format('CREATE ROLE %I LOGIN', {literal}); "
        'END IF; END $$;'
    ))
    admin.execute(ctx, f'ALTER ROLE {ident} WITH PASSWORD {db.quote_literal(password)};')
    ctx.ok(f'Rol listo: {user}')
    return user


def create_database(ctx, scope: str = db.LOCAL) -> str:
    """Crea la base con el rol de la app como duenio. Si existe, solo le cambia el duenio."""
    admin = db.resolve_admin(ctx, scope)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)

    existe = admin.query(ctx, f'SELECT 1 FROM pg_database WHERE datname = {db.quote_literal(name)};')
    if existe:
        ctx.info(f'La base {name} ya existe.')
        admin.execute(ctx, f'ALTER DATABASE {ident} OWNER TO {owner};')
    else:
        admin.execute(ctx, f'CREATE DATABASE {ident} OWNER {owner};')
        ctx.ok(f'Base creada: {name}')
    return name


def grant_privileges(ctx, scope: str = db.LOCAL) -> None:
    """Permisos del rol sobre la base y sobre el esquema public."""
    admin = db.resolve_admin(ctx, scope)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)
    admin.execute(ctx, f'GRANT ALL PRIVILEGES ON DATABASE {ident} TO {owner};')
    admin.execute(ctx, f'GRANT ALL ON SCHEMA public TO {owner};', database=name)
    ctx.ok(f'Permisos otorgados a {user} sobre {name}.')


def enable_extensions(ctx, scope: str = db.LOCAL, extensions: list[str] | None = None) -> list[str]:
    """Habilita extensiones ya instaladas en el sistema. Se separa porque cambia
    con el tiempo: agregar PostGIS a un proyecto ya desplegado no deberia
    obligar a recrear nada.

    Antes de crear cada extension se chequea `pg_available_extensions`: no todo
    VPS tiene el paquete de sistema instalado (postgis no esta en
    `vps.DEFAULT_GROUPS`), y sin este chequeo el bootstrap entero fallaba con
    "extension is not available" en vez de avisar y seguir.
    """
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    pedidas = extensions or ['postgis']
    habilitadas = []
    for extension in pedidas:
        disponible = admin.query(
            ctx, f'SELECT 1 FROM pg_available_extensions WHERE name = {db.quote_literal(extension)};',
            database=name)
        if not disponible:
            ctx.warn(f'Extension no instalada en el sistema, se salta: {extension}')
            continue
        admin.execute(ctx, f'CREATE EXTENSION IF NOT EXISTS {db.quote_ident(extension)};', database=name)
        ctx.ok(f'Extension habilitada: {extension}')
        habilitadas.append(extension)
    return habilitadas


def drop_tables(ctx, scope: str = db.LOCAL) -> list[str]:
    """Borra todas las tablas del esquema public, menos las del propio PostGIS.

    Es el primer paso de `rebuild_db`, y tiene sentido suelto: dejar la base
    vacia sin tocar el rol, la base ni las migraciones ya escritas.
    """
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    tablas = admin.query(ctx, (
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename <> 'spatial_ref_sys' ORDER BY tablename;"
    ), database=name)

    if not tablas:
        ctx.info('No hay tablas para borrar.')
        return []

    ctx.warn(f'Se van a borrar {len(tablas)} tabla(s) de {name}.')
    sql = ' '.join(f'DROP TABLE IF EXISTS {db.quote_ident(t)} CASCADE;' for t in tablas)
    admin.execute(ctx, sql, database=name)
    ctx.ok(f'{len(tablas)} tabla(s) eliminadas.')
    return tablas


def drop_database(ctx, scope: str = db.LOCAL) -> str:
    """Elimina la base entera. Corta las conexiones vivas antes, o el DROP falla."""
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    admin.execute(ctx, (
        'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
        f'WHERE datname = {db.quote_literal(name)} AND pid <> pg_backend_pid();'
    ))
    admin.execute(ctx, f'DROP DATABASE IF EXISTS {db.quote_ident(name)};')
    ctx.ok(f'Base eliminada: {name}')
    return name


def drop_role(ctx, scope: str = db.LOCAL) -> str:
    admin = db.resolve_admin(ctx, scope)
    user, _, _ = db.credentials(ctx.config)
    admin.execute(ctx, f'DROP ROLE IF EXISTS {db.quote_ident(user)};')
    ctx.ok(f'Rol eliminado: {user}')
    return user


# --- migraciones -----------------------------------------------------------

def reset_migrations(ctx) -> int:
    """Borra los archivos de `alembic/versions/`, sin tocar la base.

    Separada de `generate_migration` a proposito: reset deja el historial en
    cero, generar agrega una revision encima del historial existente. Son dos
    intenciones distintas que el script original mezclaba en una sola funcion.
    """
    versiones = _server_root(ctx) / 'alembic' / 'versions'
    versiones.mkdir(parents=True, exist_ok=True)
    archivos = sorted(versiones.glob('*.py'))
    for archivo in archivos:
        archivo.unlink()
        ctx.info(f'Migracion eliminada: {archivo.name}')
    ctx.ok(f'{len(archivos)} migracion(es) eliminadas.')
    return len(archivos)


def generate_migration(ctx, scope: str = db.LOCAL, message: str = 'auto') -> Path | None:
    """Autogenera una revision de Alembic. Devuelve None si no habia cambios."""
    versiones = _server_root(ctx) / 'alembic' / 'versions'
    antes = {p.name for p in versiones.glob('*.py')}

    with db.connect(ctx, scope) as conn:
        _alembic(ctx, conn, 'revision', '--autogenerate', '-m', message)

    nuevas = {p.name for p in versiones.glob('*.py')} - antes
    if not nuevas:
        ctx.warn('El modelo no cambio: no se genero ninguna migracion.')
        return None
    generada = versiones / nuevas.pop()
    ctx.ok(f'Migracion generada: {generada.name}')
    return generada


def apply_migrations(ctx, scope: str = db.LOCAL, revision: str = 'head') -> None:
    with db.connect(ctx, scope) as conn:
        _alembic(ctx, conn, 'upgrade', revision)
    ctx.ok(f'Migraciones aplicadas hasta {revision}.')


def ensure_partitions(ctx, scope: str = db.LOCAL) -> None:
    """Crea las particiones de las tablas particionadas.

    `alembic revision --autogenerate` no genera las particiones (ni la DEFAULT),
    asi que sin este paso el primer INSERT revienta con "no partition of
    relation found for row".
    """
    with db.connect(ctx, scope) as conn:
        payloads.run(ctx, 'partitions', server_root=_server_root(ctx), database_url=conn.url)


# --- datos -----------------------------------------------------------------

def run_seeders(ctx, scope: str = db.LOCAL) -> None:
    """Seeders base: el paquete `seeders/` del proyecto."""
    with db.connect(ctx, scope) as conn:
        payloads.run(ctx, 'seed', 'seeders',
                     server_root=_server_root(ctx), database_url=conn.url)


def run_mock_seeders(ctx, scope: str = db.LOCAL) -> None:
    """Seeders de prueba: el paquete `mock_data/` del proyecto."""
    with db.connect(ctx, scope) as conn:
        payloads.run(ctx, 'seed', 'mock_data',
                     server_root=_server_root(ctx), database_url=conn.url)


# --- respaldo y diagnostico ------------------------------------------------

def backup_database(ctx, keep: int = 7) -> Path:
    """Vuelca la base del VPS a un archivo local, en formato custom de pg_dump."""
    remote = ssh.resolve_remote(ctx.config)
    user, password, name = db.credentials(ctx.config)
    ctx.guard(password)

    if not ssh.succeeds(remote, 'command -v pg_dump'):
        raise TaskError('El VPS no tiene pg_dump instalado.')

    sello = datetime.now().strftime('%Y%m%d-%H%M%S')
    remoto = f'/tmp/{name}-{sello}.dump'
    puerto = vps.postgres_port(remote)

    ctx.info(f'Volcando {name} en el VPS...')
    ssh.run(ctx, remote, (
        f'PGPASSWORD={ssh.quote(password)} pg_dump -h 127.0.0.1 -p {puerto} '
        f'-U {ssh.quote(user)} -Fc -f {ssh.quote(remoto)} {ssh.quote(name)}'
    ))

    destino = ctx.root / BACKUP_DIR / f'{name}-{sello}.dump'
    ssh.download(ctx, remote, remoto, destino)
    ssh.capture(remote, f'rm -f {ssh.quote(remoto)}')

    ctx.ok(f'Backup guardado: {destino} ({files.human_size(files.size_of(destino))})')
    rotate_backups(ctx, keep=keep)
    ctx.note(f'Backup de {name}: {destino.name}')
    return destino


def rotate_backups(ctx, keep: int = 7) -> list[Path]:
    """Deja solo los `keep` respaldos mas nuevos. Separada porque a veces se
    quiere limpiar sin volver a volcar."""
    carpeta = ctx.root / BACKUP_DIR
    if not carpeta.is_dir():
        return []
    respaldos = sorted(carpeta.glob('*.dump'), key=lambda p: p.stat().st_mtime, reverse=True)
    sobran = respaldos[keep:]
    for viejo in sobran:
        files.remove(viejo)
        ctx.info(f'Backup rotado: {viejo.name}')
    return sobran


def open_db_tunnel(ctx):
    """Tunel Postgres como servicio de fondo: sobrevive a su pestana (PLAN.md 7.2)."""
    remote = ssh.resolve_remote(ctx.config)
    remoto = vps.postgres_port(remote)
    from .. import ports
    local = ports.resolve_port(remoto, label='puerto del tunel')
    tunnel = ssh.open_tunnel(remote, local_port=local, remote_port=remoto)
    ctx.ok(f'Tunel abierto en {tunnel.endpoint} -> {remote.host}:{remoto}')
    return tunnel


def inspect_database(ctx, scope: str = db.LOCAL) -> list[str]:
    """Diagnostico de solo lectura: tablas con su cantidad de filas estimada."""
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    filas = admin.query(ctx, (
        "SELECT relname || ' | ' || n_live_tup FROM pg_stat_user_tables "
        'ORDER BY n_live_tup DESC;'
    ), database=name)
    for linea in filas:
        ctx.info(linea)
    return filas


# --- compuestas ------------------------------------------------------------

def bootstrap_db(
    ctx,
    scope: str = db.LOCAL,
    *,
    role: bool = True,
    database: bool = True,
    privileges: bool = True,
    extensions: bool = True,
    migrate: bool = True,
) -> None:
    """Compuesta: rol -> base -> permisos -> extensiones -> migraciones."""
    if role:
        ctx.step('Rol de la aplicacion')
        create_role(ctx, scope)
    if database:
        ctx.step('Base de datos')
        create_database(ctx, scope)
    if privileges:
        ctx.step('Permisos')
        grant_privileges(ctx, scope)
    if extensions:
        ctx.step('Extensiones')
        enable_extensions(ctx, scope)
    if migrate:
        ctx.step('Migraciones')
        apply_migrations(ctx, scope)
    ctx.note(f'Bootstrap de base ({scope}) completado.')


def rebuild_db(
    ctx,
    scope: str = db.LOCAL,
    *,
    drop: bool = True,
    reset: bool = True,
    generate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = True,
) -> None:
    """Compuesta destructiva: vaciar -> resetear historial -> migrar -> sembrar.

    Cada paso es una casilla porque cada uno se pide suelto en la vida real:
    volver a correr los seeders mock sin destruir el esquema es lo mas comun.
    """
    _, _, name = db.credentials(ctx.config)
    if not ctx.confirm(f'Escribe {name} para reconstruir la base ({scope}).',
                       danger=True, expect=name):
        ctx.warn('Cancelado: no se toco la base.')
        return

    if drop:
        ctx.step('Vaciar esquema')
        drop_tables(ctx, scope)
    if reset:
        ctx.step('Resetear historial de migraciones')
        reset_migrations(ctx)
    if generate:
        ctx.step('Migracion inicial')
        generate_migration(ctx, scope, message='initial_migration')
        apply_migrations(ctx, scope)
    if partitions:
        ctx.step('Particiones')
        ensure_partitions(ctx, scope)
    if seeders:
        ctx.step('Seeders base')
        run_seeders(ctx, scope)
    if mock_seeders:
        ctx.step('Seeders mock')
        run_mock_seeders(ctx, scope)
    ctx.note(f'Reconstruccion de {name} ({scope}) completada.')


def teardown_db(ctx, scope: str = db.LOCAL, *, database: bool = True, role: bool = True) -> None:
    """Compuesta destructiva: borrar la base y el rol."""
    _, _, name = db.credentials(ctx.config)
    if not ctx.confirm(f'Escribe {name} para ELIMINAR la base y su rol ({scope}).',
                       danger=True, expect=name):
        ctx.warn('Cancelado: no se elimino nada.')
        return
    if database:
        ctx.step('Base de datos')
        drop_database(ctx, scope)
    if role:
        ctx.step('Rol')
        drop_role(ctx, scope)
    ctx.note(f'Teardown de {name} ({scope}).')


def migrate_db(ctx, scope: str = db.LOCAL, message: str = 'auto', *, apply: bool = True) -> None:
    """Compuesta corta: generar la revision y aplicarla."""
    ctx.step('Generar migracion')
    generada = generate_migration(ctx, scope, message=message)
    if apply and generada is not None:
        ctx.step('Aplicar migracion')
        apply_migrations(ctx, scope)


def bind_all() -> None:
    registry.bind('bootstrap_db', bootstrap_db)
    registry.bind('teardown_db', teardown_db)
    registry.bind('migrate_db', migrate_db)
    registry.bind('rebuild_db', rebuild_db)
    registry.bind('run_seeders', run_seeders)
    registry.bind('run_mock_seeders', run_mock_seeders)
    registry.bind('backup_db', backup_database)
    registry.bind('ssh_tunnel', open_db_tunnel)
    registry.bind('inspect_db', inspect_database)
