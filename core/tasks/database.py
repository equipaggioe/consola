from __future__ import annotations
from datetime import datetime
from pathlib import Path

from . import payloads
from .. import database as db
from .. import envfile, files, runner, ssh, vps
from ..errors import TaskError
from ..registry import registry

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

BACKUP_DIR = '.backups'


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


def enable_extensions(ctx, scope: str = db.LOCAL) -> list[str]:
    """Habilita las extensiones que declara `DB_EXTENSIONS`, como superusuario.

    Existe separada de las migraciones porque `CREATE EXTENSION` de una
    extension *untrusted* —PostGIS es la que importa aca— exige superusuario, y
    Alembic corre como el rol de la app (`runner.resolve` arma la URL con
    `db.credentials`). Una migracion que la pidiera moriria con "permission
    denied to create extension". Este es el unico canal con superusuario:
    `db.resolve_admin`, que con ambito remoto entra por SSH como `postgres`.

    La lista se declara en la configuracion del repo, no se deduce. Antes salia
    de los `CREATE EXTENSION` de las migraciones, y eso no podia funcionar en
    ninguna de las dos direcciones: `alembic revision --autogenerate` nunca
    escribe uno (un modelo con columnas `Geometry` de geoalchemy2 no deja
    rastro), asi que la lista salia vacia justo cuando hacia falta; y si una
    migracion si lo declaraba, era la que necesitaba la extension *ya creada*
    para poder aplicarse. Ni `pg_available_extensions` (lo que se puede crear:
    cientos con contrib) ni `pg_extension` (lo que ya esta creado) dicen que
    necesita el proyecto: ese dato no existe en ningun catalogo hasta que
    alguien lo escribe.

    Va en `DB_EXTENSIONS` y no en un eje del panel porque es un dato que la
    tarea lee, no una decision de la corrida: no cambia entre dos veces que se
    aprieta el boton. Es el mismo caso que `SECRET_FILES`, y como el se edita
    multilinea y se guarda separada por comas.

    Antes de crear cada extension se chequea `pg_available_extensions`: no todo
    VPS tiene el paquete de sistema instalado (postgis no esta en
    `vps.DEFAULT_GROUPS`), y sin este chequeo el bootstrap entero fallaba con
    "extension is not available" en vez de avisar y seguir.
    """
    # Se resuelve antes que el canal de superusuario para no pedir credenciales
    # de administrador cuando no hay nada que crear.
    vistas: set[str] = set()
    pedidas = [e for e in envfile.split_list(ctx.config.get('DB_EXTENSIONS'))
               if not (e.lower() in vistas or vistas.add(e.lower()))]
    if not pedidas:
        ctx.info('DB_EXTENSIONS esta vacia: no hay nada que habilitar.')
        return []

    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
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
    versiones = runner.server_root(ctx) / 'alembic' / 'versions'
    versiones.mkdir(parents=True, exist_ok=True)
    archivos = sorted(versiones.glob('*.py'))
    for archivo in archivos:
        archivo.unlink()
        ctx.info(f'Migracion eliminada: {archivo.name}')
    ctx.ok(f'{len(archivos)} migracion(es) eliminadas.')
    return len(archivos)


def generate_migration(ctx, scope: str = db.LOCAL, message: str = 'auto') -> Path | None:
    """Autogenera una revision de Alembic. Devuelve None si no habia cambios.

    Es la unica del grupo que corre siempre en esta maquina, aunque el ambito
    sea remoto: deja un archivo en `alembic/versions/` que hay que revisar y
    comitear, y generado en el VPS caeria en el repo desplegado, donde el
    `git reset --hard` del proximo despliegue se lo lleva puesto. La base remota
    la alcanza por el tunel, como cualquier otro proceso local (`runner.here`).
    """
    versiones = runner.server_root(ctx) / 'alembic' / 'versions'
    antes = {p.name for p in versiones.glob('*.py')}

    with db.connect(ctx, scope) as conn:
        runner.here(ctx, conn).run(
            ctx, '-m', 'alembic', 'revision', '--autogenerate', '-m', message)

    nuevas = {p.name for p in versiones.glob('*.py')} - antes
    if not nuevas:
        ctx.warn('El modelo no cambio: no se genero ninguna migracion.')
        return None
    generada = versiones / nuevas.pop()
    ctx.ok(f'Migracion generada: {generada.name}')
    return generada


def apply_migrations(ctx, scope: str = db.LOCAL, revision: str = 'head') -> None:
    """Lleva la base al dia con las revisiones que ya estan escritas.

    No toca archivos, asi que corre del lado que diga el ambito: con `remoto`,
    en el VPS, con las revisiones que el despliegue ya trajo y sin tunel.
    """
    runner.resolve(ctx, scope).run(ctx, '-m', 'alembic', 'upgrade', revision)
    ctx.ok(f'Migraciones aplicadas hasta {revision}.')


def ensure_partitions(ctx, scope: str = db.LOCAL) -> None:
    """Crea las particiones de las tablas particionadas.

    `alembic revision --autogenerate` no genera las particiones (ni la DEFAULT),
    asi que sin este paso el primer INSERT revienta con "no partition of
    relation found for row".
    """
    payloads.run(ctx, runner.resolve(ctx, scope), 'partitions')


# --- datos -----------------------------------------------------------------

def run_seeders(ctx, scope: str = db.LOCAL) -> None:
    """Seeders base: el paquete `seeders/` del proyecto."""
    payloads.run(ctx, runner.resolve(ctx, scope), 'seed', 'seeders')


def run_mock_seeders(ctx, scope: str = db.LOCAL) -> None:
    """Seeders de prueba: el paquete `mock_data/` del proyecto."""
    payloads.run(ctx, runner.resolve(ctx, scope), 'seed', 'mock_data')


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
    registry.bind('enable_extensions', enable_extensions)
    registry.bind('run_seeders', run_seeders)
    registry.bind('run_mock_seeders', run_mock_seeders)
    registry.bind('backup_db', backup_database)
    registry.bind('ssh_tunnel', open_db_tunnel)
    registry.bind('inspect_db', inspect_database)
