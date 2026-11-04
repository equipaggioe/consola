from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from app.core import database as db
from app.core import db_explorer, envfile, files, runner, ssh, vps
from app.core.context import TaskContext
from app.core.database import Connection
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.registry import registry
from app.core.ssh import Tunnel
from app.core.tasks import payloads

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

# --- ciclo de vida del esquema ---------------------------------------------


def create_role(ctx: TaskContext, scope: str = db.LOCAL) -> str:
    """Crea el rol de la aplicacion, o le actualiza la contrasena si ya existe."""
    admin = db.resolve_admin(ctx, scope)
    user, password, _ = db.credentials(ctx.config)
    ctx.guard(password)

    ident, literal = db.quote_ident(user), db.quote_literal(user)
    admin.execute(
        ctx,
        (
            "DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {literal}) THEN "
            f"EXECUTE format('CREATE ROLE %I LOGIN', {literal}); "
            "END IF; END $$;"
        ),
    )
    admin.execute(ctx, f"ALTER ROLE {ident} WITH PASSWORD {db.quote_literal(password)};")
    ctx.ok(f"Rol listo: {user}")
    return user


def create_database(ctx: TaskContext, scope: str = db.LOCAL) -> str:
    """Crea la base con el rol de la app como duenio. Si existe, solo le cambia el duenio."""
    admin = db.resolve_admin(ctx, scope)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)

    exists = admin.query(
        ctx, f"SELECT 1 FROM pg_database WHERE datname = {db.quote_literal(name)};"
    )
    if exists:
        ctx.info(f"La base {name} ya existe.")
        admin.execute(ctx, f"ALTER DATABASE {ident} OWNER TO {owner};")
    else:
        admin.execute(ctx, f"CREATE DATABASE {ident} OWNER {owner};")
        ctx.ok(f"Base creada: {name}")
    return name


def grant_privileges(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Permisos del rol sobre la base y sobre el esquema public."""
    admin = db.resolve_admin(ctx, scope)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)
    admin.execute(ctx, f"GRANT ALL PRIVILEGES ON DATABASE {ident} TO {owner};")
    admin.execute(ctx, f"GRANT ALL ON SCHEMA public TO {owner};", database=name)
    ctx.ok(f"Permisos otorgados a {user} sobre {name}.")


def enable_extensions(ctx: TaskContext, scope: str = db.LOCAL) -> list[str]:
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
    aprieta el boton. Se edita multilinea y se guarda separada por comas.

    An extension the system does not have stops the task: going on would hide the
    error until a migration needs it (ADR-0071).
    """
    # Se resuelve antes que el canal de superusuario para no pedir credenciales
    # de administrador cuando no hay nada que crear.
    views: set[str] = set()
    requested = [
        e
        for e in envfile.split_list(ctx.config.get("DB_EXTENSIONS"))
        if not (e.lower() in views or views.add(e.lower()))
    ]
    if not requested:
        ctx.info("DB_EXTENSIONS esta vacia: no hay nada que habilitar.")
        return []

    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    enabled = []
    for extension in requested:
        available = admin.query(
            ctx,
            f"SELECT 1 FROM pg_available_extensions WHERE name = {db.quote_literal(extension)};",
            database=name,
        )
        if not available:
            raise TaskError(
                f"La extensión {extension} no está instalada en el sistema: "
                "instala su paquete o quítala de DB_EXTENSIONS."
            )
        admin.execute(
            ctx, f"CREATE EXTENSION IF NOT EXISTS {db.quote_ident(extension)};", database=name
        )
        ctx.ok(f"Extension habilitada: {extension}")
        enabled.append(extension)
    return enabled


def drop_tables(ctx: TaskContext, scope: str = db.LOCAL) -> list[str]:
    """Borra todas las tablas del esquema public, menos las del propio PostGIS.

    Es el primer paso de `rebuild_db`, y tiene sentido suelto: dejar la base
    vacia sin tocar el rol, la base ni las migraciones ya escritas.
    """
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    tables = admin.query(
        ctx,
        (
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'spatial_ref_sys' ORDER BY tablename;"
        ),
        database=name,
    )

    if not tables:
        ctx.info("No hay tablas para borrar.")
        return []

    ctx.warn(f"Se van a borrar {len(tables)} tabla(s) de {name}.")
    sql = " ".join(f"DROP TABLE IF EXISTS {db.quote_ident(t)} CASCADE;" for t in tables)
    admin.execute(ctx, sql, database=name)
    ctx.ok(f"{len(tables)} tabla(s) eliminadas.")
    return tables


def drop_database(ctx: TaskContext, scope: str = db.LOCAL) -> str:
    """Elimina la base entera. Corta las conexiones vivas antes, o el DROP falla."""
    admin = db.resolve_admin(ctx, scope)
    _, _, name = db.credentials(ctx.config)
    admin.execute(
        ctx,
        (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = {db.quote_literal(name)} AND pid <> pg_backend_pid();"
        ),
    )
    admin.execute(ctx, f"DROP DATABASE IF EXISTS {db.quote_ident(name)};")
    ctx.ok(f"Base eliminada: {name}")
    return name


def drop_role(ctx: TaskContext, scope: str = db.LOCAL) -> str:
    admin = db.resolve_admin(ctx, scope)
    user, _, _ = db.credentials(ctx.config)
    admin.execute(ctx, f"DROP ROLE IF EXISTS {db.quote_ident(user)};")
    ctx.ok(f"Rol eliminado: {user}")
    return user


# --- migraciones -----------------------------------------------------------


def reset_migrations(ctx: TaskContext) -> int:
    """Borra los archivos de `alembic/versions/`, sin tocar la base.

    Separada de `generate_migration` a proposito: reset deja el historial en
    cero, generar agrega una revision encima del historial existente. Son dos
    intenciones distintas que el script original mezclaba en una sola funcion.
    """
    versions = runner.server_root(ctx) / "alembic" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    files = sorted(versions.glob("*.py"))
    for file in files:
        file.unlink()
        ctx.info(f"Migracion eliminada: {file.name}")
    ctx.ok(f"{len(files)} migracion(es) eliminadas.")
    return len(files)


def generate_migration(
    ctx: TaskContext, scope: str = db.LOCAL, message: str = "auto"
) -> Path | None:
    """Autogenera una revision de Alembic. Devuelve None si no habia cambios.

    Es la unica del grupo que corre siempre en esta maquina, aunque el ambito
    sea remoto: deja un archivo en `alembic/versions/` que hay que revisar y
    comitear, y generado en el VPS caeria en el repo desplegado, donde el
    `git reset --hard` del proximo despliegue se lo lleva puesto. La base remota
    la alcanza por el tunel, como cualquier otro proceso local (`runner.here`).
    """
    versions = runner.server_root(ctx) / "alembic" / "versions"
    before = {p.name for p in versions.glob("*.py")}

    revision = ("-m", "alembic", "revision", "--autogenerate", "-m", message)
    if scope == db.LOCAL:
        runner.local(ctx).run(ctx, *revision)
    else:
        with db.connect(ctx, scope) as conn:
            runner.here(ctx, conn).run(ctx, *revision)

    new = {p.name for p in versions.glob("*.py")} - before
    if not new:
        ctx.warn("El modelo no cambio: no se genero ninguna migracion.")
        return None
    generated = versions / new.pop()
    ctx.ok(f"Migracion generada: {generated.name}")
    return generated


def apply_migrations(ctx: TaskContext, scope: str = db.LOCAL, revision: str = "head") -> None:
    """Lleva la base al dia con las revisiones que ya estan escritas.

    No toca archivos, asi que corre del lado que diga el ambito: con `remoto`,
    en el VPS, con las revisiones que el despliegue ya trajo y sin tunel.
    """
    runner.resolve(ctx, scope).run(ctx, "-m", "alembic", "upgrade", revision)
    ctx.ok(f"Migraciones aplicadas hasta {revision}.")


def ensure_partitions(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Crea las particiones de las tablas particionadas.

    `alembic revision --autogenerate` no genera las particiones (ni la DEFAULT),
    asi que sin este paso el primer INSERT revienta con "no partition of
    relation found for row".
    """
    payloads.run(ctx, runner.resolve(ctx, scope), "partitions")


# --- datos -----------------------------------------------------------------


def run_seeders(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Seeders base: el paquete `seeders/` del proyecto."""
    payloads.run(ctx, runner.resolve(ctx, scope), "seed", "seeders")


def run_mock_seeders(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Seeders de prueba: el paquete `mock_data/` del proyecto."""
    payloads.run(ctx, runner.resolve(ctx, scope), "seed", "mock_data")


# --- respaldo y diagnostico ------------------------------------------------


def backup_dir(config: Config, root: Path) -> Path:
    """La carpeta de respaldos de este repo, ya resuelta.

    Relativa se resuelve contra la raiz del repo; absoluta se usa tal cual, que
    es como se sacan los volcados de adentro del repo: `.backups/` no esta en
    ningun `.gitignore` por defecto, y un dump con datos reales dentro del arbol
    de trabajo queda listo para comitearse sin que nada avise (ADR-0045).

    Recibe `config` y `root` sueltos, no el contexto: el eje `dump` de
    `restore_db` tiene que llenar su lista antes de que exista ninguna corrida
    (`core/catalog.py::queried_values`).
    """
    declared = Path(config.get("BACKUP_DIR"))
    return declared if declared.is_absolute() else root / declared


def list_backups(config: Config, root: Path) -> list[Path]:
    """Los respaldos de ESTA base, del mas nuevo al mas viejo.

    El patron lleva el nombre de la base y no es cosmetico: desde que
    `BACKUP_DIR` puede apuntar a una carpeta compartida entre repos, un `*.dump`
    a secas mezclaria los respaldos de las otras bases — y la rotacion los
    borraria.

    El nombre sale de `DB_NAME` y no de `db.credentials`, que exige ademas la
    contrasena: listar archivos no conecta con nada, y pedirla dejaria el eje
    vacio en un repo al que todavia no se le cargo.
    """
    folder = backup_dir(config, root)
    name = config.get("DB_NAME")
    if not name or not folder.is_dir():
        return []
    return sorted(folder.glob(f"{name}-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)


def backup_keep(ctx: TaskContext) -> int:
    """Cuantos respaldos sobreviven a la rotacion.

    Falla ruidosamente si lo escrito no es un entero positivo. Caer en el 7 por
    defecto seria esconder el error justo donde se decide cuantos archivos se
    borran para siempre.
    """
    raw = ctx.config.get("BACKUP_KEEP")
    try:
        keep = int(raw)
    except ValueError:
        raise TaskError(f"BACKUP_KEEP tiene que ser un numero entero, y dice {raw!r}.") from None
    if keep < 1:
        raise TaskError(f"BACKUP_KEEP tiene que ser 1 o mas, y dice {keep}.")
    return keep


def _check_version(ctx: TaskContext, conn: Connection, tool: Path) -> None:
    """Comprueba el binario local contra la version del servidor del ambito.

    Se llama con la conexion ya abierta porque la version del servidor sale de
    preguntarsela. Encontrar el binario, en cambio, va ANTES de conectar: que
    falte no tiene por que costar un tunel SSH.
    """
    with db_explorer.open_readonly(conn.url) as probe:
        server = db_explorer.server_info(probe).version
    db.check_tool_version(ctx, tool, ctx.capture([str(tool), "--version"]), server)


def _pg_argv(tool: Path, conn: Connection, user: str) -> list[str]:
    """Los flags de conexion que comparten `pg_dump` y `pg_restore`.

    La contrasena no va aca: viaja por `PGPASSWORD`, porque un argv queda
    escrito en el log de la corrida.
    """
    return [str(tool), "-h", conn.host, "-p", str(conn.port), "-U", user]


def backup_database(ctx: TaskContext) -> Path:
    """Vuelca la base local a un archivo, en formato custom de pg_dump.

    Solo la local: la base del VPS la respalda la receptora de canone
    (ADR-0060).
    """
    user, password, name = db.credentials(ctx.config)
    ctx.guard(password)
    tool = db.pg_tool("pg_dump")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir(ctx.config, ctx.root) / f"{name}-{stamp}.dump"
    destination.parent.mkdir(parents=True, exist_ok=True)

    with db.connect(ctx, db.LOCAL) as conn:
        _check_version(ctx, conn, tool)
        ctx.info(f"Volcando {name} en {destination.name}...")
        ctx.run(
            [*_pg_argv(tool, conn, user), "-Fc", "-f", str(destination), name],
            env={"PGPASSWORD": password},
        )

    ctx.ok(f"Backup guardado: {destination} ({files.human_size(files.size_of(destination))})")
    rotate_backups(ctx)
    ctx.note(f"Backup de {name}: {destination.name}")
    return destination


def rotate_backups(ctx: TaskContext) -> list[Path]:
    """Deja solo los `BACKUP_KEEP` respaldos mas nuevos de esta base.

    Separada porque a veces se quiere limpiar sin volver a volcar.
    """
    spare = list_backups(ctx.config, ctx.root)[backup_keep(ctx) :]
    for old in spare:
        files.remove(old)
        ctx.info(f"Backup rotado: {old.name}")
    return spare


def _without_extensions(content: str) -> str:
    """La lista de `pg_restore -l` sin las extensiones ni sus comentarios."""
    return "".join(f"{line}\n" for line in content.splitlines() if " EXTENSION " not in line)


def restore_database(ctx: TaskContext, dump: str = "") -> Path:
    """Carga un respaldo sobre la base local, reemplazando lo que haya.

    `--clean --if-exists` restaura sobre la base que ya existe, borrando cada
    objeto antes de recrearlo: no toca el rol ni la base en si, asi que no hace
    falta cortar conexiones ni abrir el canal de superusuario. `--no-owner`
    porque el dueno que trae el dump es el del otro lado, y aca el correcto es el
    rol de este repo. `--exit-on-error` porque un restore a medias que termina
    diciendo «38 errores» es exactamente el degradado silencioso que este repo no
    quiere: corta en el primero.

    Las extensiones tienen que existir antes — `CREATE EXTENSION` pide
    superusuario y tiene su propio boton (ADR-0047). Por eso salen de lo que se
    restaura: con `--clean`, el rol de la app intenta borrarlas y corta con «must
    be owner of extension».
    """
    if not dump:
        raise TaskError("No se eligio ningun respaldo para restaurar.")
    file = backup_dir(ctx.config, ctx.root) / dump
    if not file.is_file():
        raise TaskError(f"No existe el respaldo: {file}")

    user, password, name = db.credentials(ctx.config)
    ctx.guard(password)
    tool = db.pg_tool("pg_restore")

    with db.connect(ctx, db.LOCAL) as conn:
        _check_version(ctx, conn, tool)
        ctx.warn(f"Restaurando {file.name} sobre {name}: se reemplaza lo que haya.")
        content = ctx.capture([str(tool), "-l", str(file)])
        with tempfile.TemporaryDirectory() as folder:
            items = Path(folder) / "lista"
            items.write_text(_without_extensions(content), encoding="utf-8")
            ctx.run(
                [
                    *_pg_argv(tool, conn, user),
                    "-d",
                    name,
                    "-L",
                    str(items),
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--exit-on-error",
                    str(file),
                ],
                env={"PGPASSWORD": password},
            )

    ctx.ok(f"Base {name} restaurada desde {file.name}.")
    ctx.note(f"Restauracion de {name}: {file.name}")
    return file


def open_db_tunnel(ctx: TaskContext) -> Tunnel:
    """Tunel Postgres como servicio de fondo: sobrevive a su pestana (ADR-0016)."""
    remote = ssh.resolve_remote(ctx.config)
    ssh_remote = vps.postgres_port(remote)
    from app.core import ports

    local = ports.resolve_port(ssh_remote, label="puerto del tunel")
    tunnel = ssh.open_tunnel(remote, local_port=local, remote_port=ssh_remote)
    ctx.hold_tunnel(tunnel)
    ctx.ok(f"Tunel abierto en {tunnel.endpoint} -> {remote.host}:{ssh_remote}")
    return tunnel


def explore_db(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Conecta el explorador y lo mantiene conectado hasta cerrar la pestana.

    Es una tarea viva, como un launcher (ADR-0015): lo que
    sostiene es la conexion —y en remoto, el tunel SSH—, y lo que entrega no es
    su log sino la vista de arbol y datos de la misma pestana. Antes de
    publicarla prueba la conexion con el rol de la app y deja en la consola lo
    que imprimia `inspect_db.py`: servidor, base, usuario, tamano y tablas.
    """
    with db.connect(ctx, scope) as conn:
        with db_explorer.open_readonly(conn.url) as probe:
            info = db_explorer.server_info(probe)
            relations = db_explorer.list_relations(probe)

        ctx.ok(f"Conectado a {info.database} como {info.user} (solo lectura).")
        ctx.info(f"Servidor: {info.version.split(' on ')[0]}")
        ctx.info(f"Tamaño de la base: {files.human_size(info.size_bytes)}")
        tables = [r for r in relations if r.kind in "rpf" and not r.parent]
        ctx.info(
            f"{len(tables)} tabla(s), {len(relations) - len(tables)} vista(s) o partición(es):"
        )
        for rel in tables:
            ctx.info(
                f"  {rel.qualified}  ~{db_explorer.human_count(rel.estimate)} filas"
                f"  {files.human_size(rel.size_bytes)}"
            )

        ctx.publish(db_explorer.session_key(conn.safe_url), conn.url)
        ctx.serve(conn.safe_url, key=f"explore_db:{scope}", label=info.database, web=False)
        while not ctx.wait_cancelled(1.0):
            if conn.tunnel is not None and not conn.tunnel.alive:
                raise TaskError("El túnel SSH se cerró: vuelve a conectar.")
        ctx.raise_if_cancelled()


# --- compuestas ------------------------------------------------------------


def populate_db(
    ctx: TaskContext,
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
    vacio): una compuesta puede encadenar a otra (ADR-0038). Antes estos cuatro
    pasos estaban copiados tal cual en las dos, etiquetas incluidas.

    No tiene boton propio y no es un olvido: lo que se elige en el rail es por
    cual de los dos caminos se llega —crear de cero o reconstruir—, y "llenar una
    base que ya esta ahi" sin decir cual de los dos no es una intencion que
    alguien tenga suelta.

    Las particiones van entre las migraciones y los seeders y no es cosmetico:
    `alembic revision --autogenerate` no las escribe, y sin ellas el primer
    INSERT de un seeder revienta con "no partition of relation found for row".
    """
    if migrate:
        ctx.step("migrate")
        apply_migrations(ctx, scope)
    if partitions:
        ctx.step("partitions")
        ensure_partitions(ctx, scope)
    if seeders:
        ctx.step("seeders")
        run_seeders(ctx, scope)
    if mock_seeders:
        ctx.step("mock_seeders")
        run_mock_seeders(ctx, scope)


def bootstrap_db(
    ctx: TaskContext,
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

    Solo la base local: en el VPS la base y sus roles los crea el `install.py`
    de canone (ADR-0060).
    """
    if role:
        ctx.step("role")
        create_role(ctx, db.LOCAL)
    if database:
        ctx.step("database")
        create_database(ctx, db.LOCAL)
    if privileges:
        ctx.step("privileges")
        grant_privileges(ctx, db.LOCAL)
    if extensions:
        ctx.step("extensions")
        enable_extensions(ctx, db.LOCAL)
    populate_db(
        ctx,
        db.LOCAL,
        migrate=migrate,
        partitions=partitions,
        seeders=seeders,
        mock_seeders=mock_seeders,
    )
    ctx.note("Bootstrap de la base local completado.")


def rebuild_db(
    ctx: TaskContext,
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
        ctx.step("drop")
        drop_tables(ctx, scope)
    populate_db(
        ctx,
        scope,
        migrate=migrate,
        partitions=partitions,
        seeders=seeders,
        mock_seeders=mock_seeders,
    )
    ctx.note(f"Reconstruccion de {name} ({scope}) completada.")


def reinit_migrations(
    ctx: TaskContext,
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
        ctx.step("drop")
        drop_tables(ctx, scope)
    if reset:
        ctx.step("reset")
        reset_migrations(ctx)
    if generate:
        ctx.step("generate")
        generate_migration(ctx, scope, message="initial_migration")
    ctx.note(f"Historial de migraciones reiniciado; {name} quedo vacia.")


def teardown_db(
    ctx: TaskContext, scope: str = db.LOCAL, *, database: bool = True, role: bool = True
) -> None:
    """Compuesta destructiva: borrar la base y el rol."""
    _, _, name = db.credentials(ctx.config)
    if database:
        ctx.step("database")
        drop_database(ctx, scope)
    if role:
        ctx.step("role")
        drop_role(ctx, scope)
    ctx.note(f"Teardown de {name} ({scope}).")


def migrate_db(
    ctx: TaskContext, message: str = "auto", *, generate: bool = True, apply: bool = True
) -> None:
    """Compuesta corta: generar la revision pendiente y/o aplicar lo que haya.

    Los dos pasos son casillas sueltas porque se piden sueltos: 'Generar' para
    revisar el diff antes de tocar nada, 'Aplicar' para poner al dia una base
    que quedo atras con migraciones que ya estan en el repo.

    Solo la base local: en el VPS migra el `deploy.py` de canone (ADR-0060).
    """
    if generate:
        ctx.step("generate")
        generate_migration(ctx, db.LOCAL, message=message)
    if apply:
        ctx.step("apply")
        apply_migrations(ctx, db.LOCAL)


def bind_all() -> None:
    registry.bind("bootstrap_db", bootstrap_db)
    registry.bind("teardown_db", teardown_db)
    registry.bind("migrate_db", migrate_db)
    registry.bind("rebuild_db", rebuild_db)
    registry.bind("reinit_migrations", reinit_migrations)
    registry.bind("enable_extensions", enable_extensions)
    registry.bind("run_seeders", run_seeders)
    registry.bind("run_mock_seeders", run_mock_seeders)
    registry.bind("backup_db", backup_database)
    registry.bind("restore_db", restore_database)
    registry.bind("ssh_tunnel", open_db_tunnel)
    registry.bind("explore_db", explore_db)
