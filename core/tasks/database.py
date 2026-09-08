from __future__ import annotations
import re
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


_EXTENSION_RE = re.compile(
    r'create\s+extension\s+(?:if\s+not\s+exists\s+)?["\']?([a-z0-9_]+)["\']?',
    re.IGNORECASE)


def _declared_extensions(ctx) -> list[str]:
    """Las extensiones que el repo del servidor realmente usa, sacadas de los
    `CREATE EXTENSION` de sus migraciones de Alembic.

    Antes esto era la lista fija `['postgis']`: el bootstrap intentaba habilitar
    PostGIS aunque el repo abierto no lo tocara, y no veia una segunda extension
    (`pg_trgm`, `unaccent`) por mas que una migracion la pidiera. La fuente de
    verdad es el propio repo, no una constante de Consola.
    """
    versiones = _server_root(ctx) / 'alembic' / 'versions'
    encontradas: list[str] = []
    vistas: set[str] = set()
    for archivo in sorted(versiones.glob('*.py')):
        for nombre in _EXTENSION_RE.findall(archivo.read_text(encoding='utf-8', errors='ignore')):
            if nombre.lower() not in vistas:
                vistas.add(nombre.lower())
                encontradas.append(nombre)
    return encontradas


def enable_extensions(ctx, scope: str = db.LOCAL, extensions: list[str] | None = None) -> list[str]:
    """Habilita las extensiones que declara el repo (`_declared_extensions`), o
    las que se le pasen. Se separa porque cambia con el tiempo: agregar PostGIS a
    un proyecto ya desplegado no deberia obligar a recrear nada.

    Antes de crear cada extension se chequea `pg_available_extensions`: no todo
    VPS tiene el paquete de sistema instalado (postgis no esta en
    `vps.DEFAULT_GROUPS`), y sin este chequeo el bootstrap entero fallaba con
    "extension is not available" en vez de avisar y seguir.
    """
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    pedidas = extensions if extensions is not None else _declared_extensions(ctx)
    if not pedidas:
        ctx.info('El repo no declara ninguna extension en sus migraciones.')
        return []
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

def populate_db(
    ctx,
    scope: str = db.LOCAL,
    *,
    migrate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = False,
) -> None:
    """Compuesta: migrar -> particiones -> seeders. Deja USABLE una base que ya
    existe, sin importar como llego a existir.

    La llaman `bootstrap_db` (que antes la creo) y `rebuild_db` (que antes la
    vacio), por lo mismo que `bootstrap_vps` llama a `bootstrap_db`: una
    compuesta puede encadenar a otra. Antes estos cuatro pasos estaban copiados
    tal cual en las dos, etiquetas incluidas.

    No tiene boton propio y no es un olvido: lo que se elige en el rail es por
    cual de los dos caminos se llega —crear de cero o reconstruir—, y "llenar una
    base que ya esta ahi" sin decir cual de los dos no es una intencion que
    alguien tenga suelta.

    Las particiones van entre las migraciones y los seeders y no es cosmetico:
    `alembic revision --autogenerate` no las escribe, y sin ellas el primer
    INSERT de un seeder revienta con "no partition of relation found for row".
    """
    if migrate:
        ctx.step('migrate')
        apply_migrations(ctx, scope)
    if partitions:
        ctx.step('partitions')
        ensure_partitions(ctx, scope)
    if seeders:
        ctx.step('seeders')
        run_seeders(ctx, scope)
    if mock_seeders:
        ctx.step('mock_seeders')
        run_mock_seeders(ctx, scope)


def bootstrap_db(
    ctx,
    scope: str = db.LOCAL,
    *,
    role: bool = True,
    database: bool = True,
    privileges: bool = True,
    extensions: bool = True,
    migrate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = False,
) -> None:
    """Compuesta: crea el continente —rol, base, permisos, extensiones— y lo
    llena con `populate_db`.

    Termina en una base USABLE, no en una base vacia: un bootstrap que deja el
    esquema creado pero sin los datos minimos obliga a apretar Reconstruir DB
    —una destructiva, que la consola frena o avisa segun el seguro del repo—
    para completar algo que no tiene nada de destructivo la primera vez.
    """
    if role:
        ctx.step('role')
        create_role(ctx, scope)
    if database:
        ctx.step('database')
        create_database(ctx, scope)
    if privileges:
        ctx.step('privileges')
        grant_privileges(ctx, scope)
    if extensions:
        ctx.step('extensions')
        enable_extensions(ctx, scope)
    populate_db(ctx, scope, migrate=migrate, partitions=partitions,
                seeders=seeders, mock_seeders=mock_seeders)
    ctx.note(f'Bootstrap de base ({scope}) completado.')


def rebuild_db(
    ctx,
    scope: str = db.LOCAL,
    *,
    drop: bool = True,
    migrate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = True,
) -> None:
    """Compuesta destructiva: borra las tablas y vuelve a llenar con
    `populate_db`. Mismo destino que `bootstrap_db`, otro punto de partida: una
    base que ya existe.

    Reconstruye con el historial de migraciones que ya existe en el repo; no lo
    toca. Borrar `alembic/versions/` y escribir una inicial nueva es otra
    intencion —cambiar la historia del proyecto, no el estado de una base— y
    tiene su propio boton (`reinit_migrations`).

    Cada paso es una casilla porque cada uno se pide suelto en la vida real:
    volver a correr los seeders mock sin destruir el esquema es lo mas comun.
    """
    _, _, name = db.credentials(ctx.config)
    if drop:
        ctx.step('drop')
        drop_tables(ctx, scope)
    populate_db(ctx, scope, migrate=migrate, partitions=partitions,
                seeders=seeders, mock_seeders=mock_seeders)
    ctx.note(f'Reconstruccion de {name} ({scope}) completada.')


def reinit_migrations(
    ctx,
    scope: str = db.LOCAL,
    *,
    drop: bool = True,
    reset: bool = True,
    generate: bool = True,
) -> None:
    """Compuesta destructiva: vaciar la base, borrar `alembic/versions/` y
    escribir la migracion inicial.

    Vacia el esquema ella misma, y no es un exceso de alcance: el autogenerate
    compara los modelos contra la base viva, asi que sobre una base con tablas
    Alembic no ve diferencias y la "inicial" sale vacia. Sin este paso adentro,
    el boton solo funcionaba si te acordabas de vaciar antes por tu cuenta.

    No aplica la migracion: deja la base vacia y el historial en cero, que es
    exactamente el estado del que parte `rebuild_db` — el que aplica, hace las
    particiones y siembra.
    """
    _, _, name = db.credentials(ctx.config)
    if drop:
        ctx.step('drop')
        drop_tables(ctx, scope)
    if reset:
        ctx.step('reset')
        reset_migrations(ctx)
    if generate:
        ctx.step('generate')
        generate_migration(ctx, scope, message='initial_migration')
    ctx.note(f'Historial de migraciones reiniciado; {name} quedo vacia.')


def teardown_db(ctx, scope: str = db.LOCAL, *, database: bool = True, role: bool = True) -> None:
    """Compuesta destructiva: borrar la base y el rol."""
    _, _, name = db.credentials(ctx.config)
    if database:
        ctx.step('database')
        drop_database(ctx, scope)
    if role:
        ctx.step('role')
        drop_role(ctx, scope)
    ctx.note(f'Teardown de {name} ({scope}).')


def migrate_db(ctx, scope: str = db.LOCAL, message: str = 'auto', *,
               generate: bool = True, apply: bool = True) -> None:
    """Compuesta corta: generar la revision pendiente y/o aplicar lo que haya.

    Los dos pasos son casillas sueltas porque se piden sueltos: 'Generar' para
    revisar el diff antes de tocar nada, 'Aplicar' para poner al dia una base
    que quedo atras con migraciones que ya estan en el repo.
    """
    if generate:
        ctx.step('generate')
        generate_migration(ctx, scope, message=message)
    if apply:
        ctx.step('apply')
        apply_migrations(ctx, scope)


def bind_all() -> None:
    registry.bind('bootstrap_db', bootstrap_db)
    registry.bind('teardown_db', teardown_db)
    registry.bind('migrate_db', migrate_db)
    registry.bind('rebuild_db', rebuild_db)
    registry.bind('reinit_migrations', reinit_migrations)
    registry.bind('run_seeders', run_seeders)
    registry.bind('run_mock_seeders', run_mock_seeders)
    registry.bind('backup_db', backup_database)
    registry.bind('ssh_tunnel', open_db_tunnel)
    registry.bind('inspect_db', inspect_database)
