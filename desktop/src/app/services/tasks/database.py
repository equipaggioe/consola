"""Database group (operations).

Each step is an atomic capability with its own button, and `rebuild_db`
is the composite that chains them. Likewise `bootstrap_db` (create role,
create database, permissions, extensions, migrate) and `teardown_db`
(delete database, delete role).

Against the VPS, what changes its database is canone's `database.py`,
run from the admin account (ADR-0074): Consola only chooses the command.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale

from app.services import canone, db_explorer, envfile, files, runner
from app.services import database as db
from app.services.context import TaskContext
from app.services.database import Connection
from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.registry import registry
from app.services.ssh import Tunnel
from app.services.tasks import payloads, vps_setup

# --- schema life cycle ---


def create_role(ctx: TaskContext) -> str:
    """Create the application's role, or update its password."""
    admin = db.resolve_admin(ctx)
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
    ctx.ok(QCoreApplication.translate("database", "Rol listo: {0}").format(user))
    return user


def create_database(ctx: TaskContext) -> str:
    """Create the database owned by the app's role, or change owner."""
    admin = db.resolve_admin(ctx)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)

    exists = admin.query(
        ctx, f"SELECT 1 FROM pg_database WHERE datname = {db.quote_literal(name)};"
    )
    if exists:
        ctx.info(QCoreApplication.translate("database", "La base {0} ya existe.").format(name))
        admin.execute(ctx, f"ALTER DATABASE {ident} OWNER TO {owner};")
    else:
        admin.execute(ctx, f"CREATE DATABASE {ident} OWNER {owner};")
        ctx.ok(QCoreApplication.translate("database", "Base creada: {0}").format(name))
    return name


def grant_privileges(ctx: TaskContext) -> None:
    """Grant the role on the database and the public schema."""
    admin = db.resolve_admin(ctx)
    user, _, name = db.credentials(ctx.config)
    ident, owner = db.quote_ident(name), db.quote_ident(user)
    admin.execute(ctx, f"GRANT ALL PRIVILEGES ON DATABASE {ident} TO {owner};")
    admin.execute(ctx, f"GRANT ALL ON SCHEMA public TO {owner};", database=name)
    ctx.ok(
        QCoreApplication.translate("database", "Permisos otorgados a {0} sobre {1}.").format(
            user, name
        )
    )


def enable_extensions(ctx: TaskContext) -> list[str]:
    """Enable the extensions `DB_EXTENSIONS` declares, as superuser.

    It is separate from migrations because `CREATE EXTENSION` of an
    *untrusted* extension, with PostGIS the one that matters, requires
    superuser, and Alembic runs as the app's role (`runner.local`
    builds the URL with `db.credentials`). A migration asking for it
    would die with «permission denied to create extension». This is the
    only channel with superuser: `db.resolve_admin`. On the VPS,
    `install.py --extension` creates them.

    The list is declared in the repo's configuration, not deduced.
    `alembic revision --autogenerate` never writes a `CREATE EXTENSION`,
    since a model with geoalchemy2 `Geometry` columns leaves no trace,
    and a migration that does declare one needs the extension *already
    created* to apply. Neither `pg_available_extensions` (what can be
    created: hundreds with contrib) nor `pg_extension` (what is created)
    says what the project needs: that datum exists in no catalog until
    someone writes it.

    It goes in `DB_EXTENSIONS` and not an axis because it is a datum the
    task reads, not a decision of the run. It edits multi-line and saves
    separated by commas.

    An extension the system does not have stops the task: going on would
    hide the error until a migration needs it (ADR-0071).
    """
    # It resolves before the superuser channel so as not to ask for
    # admin credentials when there is nothing to create.
    views: set[str] = set()
    requested = [
        e
        for e in envfile.split_list(ctx.config.get("DB_EXTENSIONS"))
        if not (e.lower() in views or views.add(e.lower()))
    ]
    if not requested:
        ctx.info(
            QCoreApplication.translate(
                "database", "DB_EXTENSIONS esta vacia: no hay nada que habilitar."
            )
        )
        return []

    admin = db.resolve_admin(ctx)
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
                QCoreApplication.translate(
                    "database",
                    "La extensión {0} no está instalada en el sistema: instala su paquete o "
                    "quítala de DB_EXTENSIONS.",
                ).format(extension)
            )
        admin.execute(
            ctx, f"CREATE EXTENSION IF NOT EXISTS {db.quote_ident(extension)};", database=name
        )
        ctx.ok(
            QCoreApplication.translate("database", "Extension habilitada: {0}").format(extension)
        )
        enabled.append(extension)
    return enabled


def drop_tables(ctx: TaskContext) -> list[str]:
    """Delete all tables of the public schema, except PostGIS's own.

    It is `rebuild_db`'s first step, and it makes sense alone: leaving
    the database empty without touching the role, the database or
    written migrations.
    """
    admin = db.resolve_admin(ctx)
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
        ctx.info(QCoreApplication.translate("database", "No hay tablas para borrar."))
        return []

    ctx.warn(
        QCoreApplication.translate("database", "Se van a borrar {0} tabla(s) de {1}.").format(
            len(tables), name
        )
    )
    sql = " ".join(f"DROP TABLE IF EXISTS {db.quote_ident(t)} CASCADE;" for t in tables)
    admin.execute(ctx, sql, database=name)
    ctx.ok(QCoreApplication.translate("database", "{0} tabla(s) eliminadas.").format(len(tables)))
    return tables


def drop_database(ctx: TaskContext) -> str:
    """Delete the whole database.

    Cutting live connections or DROP fails.
    """
    admin = db.resolve_admin(ctx)
    _, _, name = db.credentials(ctx.config)
    admin.execute(
        ctx,
        (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = {db.quote_literal(name)} AND pid <> pg_backend_pid();"
        ),
    )
    admin.execute(ctx, f"DROP DATABASE IF EXISTS {db.quote_ident(name)};")
    ctx.ok(QCoreApplication.translate("database", "Base eliminada: {0}").format(name))
    return name


def drop_role(ctx: TaskContext) -> str:
    """Delete the application's role."""
    admin = db.resolve_admin(ctx)
    user, _, _ = db.credentials(ctx.config)
    admin.execute(ctx, f"DROP ROLE IF EXISTS {db.quote_ident(user)};")
    ctx.ok(QCoreApplication.translate("database", "Rol eliminado: {0}").format(user))
    return user


# --- migrations ---


def reset_migrations(ctx: TaskContext) -> int:
    """Delete the files in `alembic/versions/`, not the database.

    Separate from `generate_migration` on purpose: reset leaves the
    history at zero, generating adds a revision over the existing
    history. They are two different intentions.
    """
    versions = runner.server_root(ctx) / "alembic" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    files = sorted(versions.glob("*.py"))
    for file in files:
        file.unlink()
        ctx.info(
            QCoreApplication.translate("database", "Migracion eliminada: {0}").format(file.name)
        )
    ctx.ok(
        QCoreApplication.translate("database", "{0} migracion(es) eliminadas.").format(len(files))
    )
    return len(files)


def generate_migration(ctx: TaskContext, message: str = "auto") -> Path | None:
    """Autogenerate an Alembic revision. Return None if nothing changed.

    It leaves a file in `alembic/versions/` to review and commit.
    """
    versions = runner.server_root(ctx) / "alembic" / "versions"
    before = {p.name for p in versions.glob("*.py")}
    runner.local(ctx).run(ctx, "-m", "alembic", "revision", "--autogenerate", "-m", message)

    new = {p.name for p in versions.glob("*.py")} - before
    if not new:
        ctx.warn(
            QCoreApplication.translate(
                "database", "El modelo no cambio: no se genero ninguna migracion."
            )
        )
        return None
    generated = versions / new.pop()
    ctx.ok(
        QCoreApplication.translate("database", "Migracion generada: {0}").format(generated.name)
    )
    return generated


def apply_migrations(ctx: TaskContext, revision: str = "head") -> None:
    """Bring the local database up to date with the revisions."""
    runner.local(ctx).run(ctx, "-m", "alembic", "upgrade", revision)
    ctx.ok(
        QCoreApplication.translate("database", "Migraciones aplicadas hasta {0}.").format(revision)
    )


def ensure_partitions(ctx: TaskContext) -> None:
    """Create the partitions of partitioned tables.

    `alembic revision --autogenerate` does not generate partitions or
    the DEFAULT one, so without this step the first INSERT dies with «no
    partition of relation found for row».
    """
    payloads.run(ctx, runner.local(ctx), "partitions")


# --- data ---


def run_seeders(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Run the base seeders: the project's `seeders/` package.

    On the VPS, those of the active version, with `database.py seed`.
    """
    if scope == db.LOCAL:
        payloads.run(ctx, runner.local(ctx), "seed", "seeders")
    else:
        _database_py(ctx, "seed")


def run_mock_seeders(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Run the test seeders: the project's `mock_data/` package.

    On the VPS, with `database.py seed --mock`, which runs only on a
    machine marked for development.
    """
    if scope == db.LOCAL:
        payloads.run(ctx, runner.local(ctx), "seed", "mock_data")
    else:
        _in_development(ctx)
        _database_py(ctx, "seed --mock")


# --- the VPS's database ---


def _database_py(ctx: TaskContext, command: str) -> None:
    """Run canone's `database.py` on the VPS, from the admin account."""
    _, app = canone.origin(ctx.root)
    entry = vps_setup.admin(ctx)
    entry.run(ctx, canone.database_command(app, command))
    ctx.ok(
        QCoreApplication.translate("database", "database.py {0}: listo en {1}.").format(
            command, entry.remote.host
        )
    )


def _in_development(ctx: TaskContext) -> None:
    """Stop if the README says the repo is in production.

    `database.py` refuses too, on a machine without the development
    mark. This stops before reaching the VPS.
    """
    if canone.state(ctx.root) != canone.DEVELOPMENT:
        raise TaskError(
            QCoreApplication.translate(
                "database",
                "El README dice «Estado: en producción»: Consola no vacía la base del "
                "VPS ni le carga datos de prueba.",
            )
        )


def empty_vps_database(ctx: TaskContext) -> None:
    """Empty the VPS's database and its uploaded files.

    `database.py empty` stops the server and leaves the database as
    `install.py` creates it: empty and without migrations.
    """
    _in_development(ctx)
    ctx.warn(
        QCoreApplication.translate("database", "Se borran la base del VPS y los archivos subidos.")
    )
    _database_py(ctx, "empty")


# --- backup and diagnostics ---


def backup_dir(config: Config, root: Path) -> Path:
    """Return this repo's backups folder, already resolved.

    Relative resolves against the repo's root; absolute is used as is,
    which is how dumps leave the repo: `.backups/` is in no `.gitignore`
    by default, and a dump with real data in the working tree stays
    ready to commit with no warning (ADR-0045).

    It receives loose `config` and `root` and not the context:
    `restore_db`'s `dump` axis has to fill its list before any run
    exists (`services/catalog.py::queried_values`).
    """
    declared = Path(config.get("BACKUP_DIR"))
    return declared if declared.is_absolute() else root / declared


def list_backups(config: Config, root: Path) -> list[Path]:
    """Return THIS database's backups, newest first.

    The pattern carries the database's name and is not cosmetic: since
    `BACKUP_DIR` can point to a folder shared between repos, a bare
    `*.dump` would mix other databases' backups, and rotation would
    delete them.

    The name comes from `DB_NAME` and not `db.credentials`, which also
    requires the password: listing files connects to nothing, and asking
    for it would leave the axis empty in a repo that has none loaded
    yet.
    """
    folder = backup_dir(config, root)
    name = config.get("DB_NAME")
    if not name or not folder.is_dir():
        return []
    return sorted(folder.glob(f"{name}-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)


def backup_keep(ctx: TaskContext) -> int:
    """Return how many backups survive rotation.

    It fails loudly if what is written is not a positive integer.
    Falling back on 7 would hide the error right where it decides how
    many files are deleted forever.
    """
    raw = ctx.config.get("BACKUP_KEEP")
    try:
        keep = int(raw)
    except ValueError:
        raise TaskError(
            QCoreApplication.translate(
                "database", "BACKUP_KEEP tiene que ser un numero entero, y dice {0!r}."
            ).format(raw)
        ) from None
    if keep < 1:
        raise TaskError(
            QCoreApplication.translate(
                "database", "BACKUP_KEEP tiene que ser 1 o mas, y dice {0}."
            ).format(keep)
        )
    return keep


def _check_version(ctx: TaskContext, conn: Connection, tool: Path) -> None:
    """Check the local binary against the scope server's version.

    It is called with the connection open because the server's version
    comes from asking it. Finding the binary, by contrast, goes BEFORE
    connecting: its absence should not cost an SSH tunnel.
    """
    with db_explorer.open_readonly(conn.url) as probe:
        server = db_explorer.server_info(probe).version
    db.check_tool_version(ctx, tool, ctx.capture([str(tool), "--version"]), server)


def _pg_argv(tool: Path, conn: Connection, user: str) -> list[str]:
    """Return the connection flags `pg_dump` and `pg_restore` share.

    The password does not go here: it travels through `PGPASSWORD`,
    because an argv stays written in the run's log.
    """
    return [str(tool), "-h", conn.host, "-p", str(conn.port), "-U", user]


def backup_database(ctx: TaskContext) -> Path:
    """Dump the local database to a file, in pg_dump's custom format.

    Only the local one: canone's receiver backs up the VPS's database
    (ADR-0060).
    """
    user, password, name = db.credentials(ctx.config)
    ctx.guard(password)
    tool = db.pg_tool("pg_dump")
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir(ctx.config, ctx.root) / f"{name}-{stamp}.dump"
    destination.parent.mkdir(parents=True, exist_ok=True)

    with db.connect(ctx, db.LOCAL) as conn:
        _check_version(ctx, conn, tool)
        ctx.info(
            QCoreApplication.translate("database", "Volcando {0} en {1}...").format(
                name, destination.name
            )
        )
        ctx.run(
            [*_pg_argv(tool, conn, user), "-Fc", "-f", str(destination), name],
            env={"PGPASSWORD": password},
        )

    size = files.human_size(files.size_of(destination), QLocale())
    ctx.ok(
        QCoreApplication.translate("database", "Backup guardado: {0} ({1})").format(
            destination, size
        )
    )
    rotate_backups(ctx)
    ctx.note(
        QCoreApplication.translate("database", "Backup de {0}: {1}").format(name, destination.name)
    )
    return destination


def rotate_backups(ctx: TaskContext) -> list[Path]:
    """Keep only the `BACKUP_KEEP` newest backups of this database.

    Separate because sometimes one wants to clean without dumping again.
    """
    spare = list_backups(ctx.config, ctx.root)[backup_keep(ctx) :]
    for old in spare:
        files.remove(old)
        ctx.info(QCoreApplication.translate("database", "Backup rotado: {0}").format(old.name))
    return spare


def _without_extensions(content: str) -> str:
    """Return `pg_restore -l`'s list without extensions.

    Their comments go too.
    """
    return "".join(f"{line}\n" for line in content.splitlines() if " EXTENSION " not in line)


def restore_database(ctx: TaskContext, dump: str = "") -> Path:
    """Load a backup over the local database, replacing what is there.

    `--clean --if-exists` restores over the existing database, deleting
    each object before recreating it: it does not touch the role or the
    database itself, so it needs no cutting of connections or superuser
    channel. `--no-owner` because the dump's owner is the other side's,
    and here the right one is this repo's role. `--exit-on-error`
    because a half restore ending in «38 errors» is the silent
    degradation this repo does not want: it stops at the first.

    Extensions have to exist before: `CREATE EXTENSION` asks for
    superuser and has its own button (ADR-0047). So they leave what is
    restored: with `--clean`, the app's role tries to delete them and
    stops with «must be owner of extension».
    """
    if not dump:
        raise TaskError(
            QCoreApplication.translate("database", "No se eligio ningun respaldo para restaurar.")
        )
    file = backup_dir(ctx.config, ctx.root) / dump
    if not file.is_file():
        raise TaskError(
            QCoreApplication.translate("database", "No existe el respaldo: {0}").format(file)
        )

    user, password, name = db.credentials(ctx.config)
    ctx.guard(password)
    tool = db.pg_tool("pg_restore")

    with db.connect(ctx, db.LOCAL) as conn:
        _check_version(ctx, conn, tool)
        ctx.warn(
            QCoreApplication.translate(
                "database", "Restaurando {0} sobre {1}: se reemplaza lo que haya."
            ).format(file.name, name)
        )
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

    ctx.ok(
        QCoreApplication.translate("database", "Base {0} restaurada desde {1}.").format(
            name, file.name
        )
    )
    ctx.note(
        QCoreApplication.translate("database", "Restauracion de {0}: {1}").format(name, file.name)
    )
    return file


def open_db_tunnel(ctx: TaskContext) -> Tunnel:
    """Open a Postgres tunnel that outlives its tab (ADR-0016).

    It enters as `<app>_read`, without a password, to the `<app>`
    database: it reads, and changes nothing.
    """
    _, app = canone.origin(ctx.root)
    tunnel = db.vps_tunnel(ctx)
    ctx.ok(
        QCoreApplication.translate(
            "database", "Tunel abierto en {0}: entra como {1}, sin contraseña, a la base {2}."
        ).format(tunnel.endpoint, db.reader(app), app)
    )
    return tunnel


def explore_db(ctx: TaskContext, scope: str = db.LOCAL) -> None:
    """Connect the explorer and keep it connected until the tab closes.

    A live task, like a launcher (ADR-0015): it holds the connection
    and, on remote, the SSH tunnel, and what it delivers is not its log
    but the tree and data view of the same tab. Before publishing it
    tests the connection and leaves in the console the server, database,
    user, size and tables. Locally it connects as the app's role; on the
    VPS, as `<app>_read`.
    """
    conn = db.connect(ctx, db.LOCAL) if scope == db.LOCAL else db.connect_vps(ctx)
    with conn:
        with db_explorer.open_readonly(conn.url) as probe:
            info = db_explorer.server_info(probe)
            relations = db_explorer.list_relations(probe)

        ctx.ok(
            QCoreApplication.translate(
                "database", "Conectado a {0} como {1} (solo lectura)."
            ).format(info.database, info.user)
        )
        ctx.info(
            QCoreApplication.translate("database", "Servidor: {0}").format(
                info.version.split(" on ")[0]
            )
        )
        ctx.info(
            QCoreApplication.translate("database", "Tamaño de la base: {0}").format(
                files.human_size(info.size_bytes, QLocale())
            )
        )
        tables = [r for r in relations if r.kind in "rpf" and not r.parent]
        ctx.info(
            QCoreApplication.translate(
                "database", "{0} tabla(s), {1} vista(s) o partición(es):"
            ).format(len(tables), len(relations) - len(tables))
        )
        for rel in tables:
            ctx.info(
                QCoreApplication.translate("database", "  {0}  ~{1} filas  {2}").format(
                    rel.qualified,
                    db_explorer.human_count(rel.estimate, QLocale()),
                    files.human_size(rel.size_bytes, QLocale()),
                )
            )

        ctx.publish(db_explorer.session_key(conn.safe_url), conn.url)
        ctx.serve(conn.safe_url, key=f"explore_db:{scope}", label=info.database, web=False)
        while not ctx.wait_cancelled(1.0):
            if conn.tunnel is not None and not conn.tunnel.alive:
                raise TaskError(
                    QCoreApplication.translate(
                        "database", "El túnel SSH se cerró: vuelve a conectar."
                    )
                )
        ctx.raise_if_cancelled()


# --- composites ---


def populate_db(
    ctx: TaskContext,
    *,
    migrate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = False,
) -> None:
    """Composite: migrate, partitions, seeders, on the local database.

    It leaves USABLE a database that exists, however it came to exist.

    `bootstrap_db` (which created it first) and `rebuild_db` (which
    emptied it first) call it: a composite can chain another (ADR-0038).

    It has no button of its own, and that is no oversight: what the rail
    chooses is which of the two paths to take, create from scratch or
    rebuild, and filling a database already there without saying which
    is not an intention anyone has alone.

    Partitions go between migrations and seeders, and that is not
    cosmetic: `alembic revision --autogenerate` does not write them, and
    without them a seeder's first INSERT dies with «no partition of
    relation found for row».
    """
    if migrate:
        ctx.step("migrate")
        apply_migrations(ctx)
    if partitions:
        ctx.step("partitions")
        ensure_partitions(ctx)
    if seeders:
        ctx.step("seeders")
        run_seeders(ctx)
    if mock_seeders:
        ctx.step("mock_seeders")
        run_mock_seeders(ctx)


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
    """Composite: create role, database, permissions and extensions.

    Then it fills them with `populate_db`. It ends in a USABLE database,
    not an empty one: a bootstrap leaving the schema created without the
    minimum data forces pressing Reconstruir DB, a destructive action
    the console stops or warns about by the repo's guard, to complete
    something not destructive at all the first time.

    Only the local database: on the VPS canone's `install.py` creates
    the database and its roles (ADR-0060).
    """
    if role:
        ctx.step("role")
        create_role(ctx)
    if database:
        ctx.step("database")
        create_database(ctx)
    if privileges:
        ctx.step("privileges")
        grant_privileges(ctx)
    if extensions:
        ctx.step("extensions")
        enable_extensions(ctx)
    populate_db(
        ctx,
        migrate=migrate,
        partitions=partitions,
        seeders=seeders,
        mock_seeders=mock_seeders,
    )
    ctx.note(QCoreApplication.translate("database", "Bootstrap de la base local completado."))


def rebuild_db(
    ctx: TaskContext,
    scope: str = db.LOCAL,
    *,
    drop: bool = True,
    empty: bool = True,
    migrate: bool = True,
    partitions: bool = True,
    seeders: bool = True,
    mock_seeders: bool = True,
) -> None:
    """Destructive composite: empty the database and fill it again.

    The same destination as `bootstrap_db`, another starting point: a
    database that exists.

    It rebuilds with the migration history in the repo, without touching
    it. Deleting `alembic/versions/` and writing a new initial one is
    another intention, changing the project's history and not a
    database's state, and it has its own button (`reinit_migrations`).

    Each step is a checkbox because each is asked for alone in real
    life: rerunning the mock seeders without destroying the schema is
    the most common. Locally it deletes the tables and refills with
    `populate_db`. On the VPS each step is a `database.py` command:
    `empty`, `migrate`, which also runs the seeders and starts the
    server, `seed` and `seed --mock`. `drop` and `partitions` exist only
    locally, and `empty` only on the VPS (`Step.scopes`).
    """
    if scope == db.LOCAL:
        _, _, name = db.credentials(ctx.config)
        if drop:
            ctx.step("drop")
            drop_tables(ctx)
        populate_db(
            ctx,
            migrate=migrate,
            partitions=partitions,
            seeders=seeders,
            mock_seeders=mock_seeders,
        )
        ctx.note(
            QCoreApplication.translate(
                "database", "Reconstruccion de {0} (local) completada."
            ).format(name)
        )
        return
    if empty:
        ctx.step("empty")
        empty_vps_database(ctx)
    if migrate:
        ctx.step("migrate")
        _database_py(ctx, "migrate")
    if seeders:
        ctx.step("seeders")
        run_seeders(ctx, db.REMOTE)
    if mock_seeders:
        ctx.step("mock_seeders")
        run_mock_seeders(ctx, db.REMOTE)
    ctx.note(
        QCoreApplication.translate("database", "Reconstruccion de la base del VPS completada.")
    )


def reinit_migrations(
    ctx: TaskContext, *, drop: bool = True, reset: bool = True, generate: bool = True
) -> None:
    """Destructive composite: empty, delete versions and rewrite.

    It empties the local database, deletes `alembic/versions/` and
    writes the initial migration.

    It empties the schema itself, and that is no excess of scope:
    autogenerate compares models against the live database, so over a
    database with tables Alembic sees no differences and the «initial»
    comes out empty.

    It does not apply the migration: it leaves the database empty and
    the history at zero, exactly the state `rebuild_db` starts from,
    which applies, makes partitions and seeds.

    Only locally: the VPS takes the new history with «Reconstruir base»,
    emptying only, and «Desplegar versión».
    """
    _, _, name = db.credentials(ctx.config)
    if drop:
        ctx.step("drop")
        drop_tables(ctx)
    if reset:
        ctx.step("reset")
        reset_migrations(ctx)
    if generate:
        ctx.step("generate")
        generate_migration(ctx, message="initial_migration")
    ctx.note(
        QCoreApplication.translate(
            "database", "Historial de migraciones reiniciado; {0} quedo vacia."
        ).format(name)
    )


def teardown_db(ctx: TaskContext, *, database: bool = True, role: bool = True) -> None:
    """Destructive composite: delete the local database and the role.

    On the VPS the roles are `install.py`'s, and «Reconstruir base»
    empties the database.
    """
    _, _, name = db.credentials(ctx.config)
    if database:
        ctx.step("database")
        drop_database(ctx)
    if role:
        ctx.step("role")
        drop_role(ctx)
    ctx.note(QCoreApplication.translate("database", "Teardown de {0}.").format(name))


def migrate_db(
    ctx: TaskContext, message: str = "auto", *, generate: bool = True, apply: bool = True
) -> None:
    """Short composite: generate the pending revision and/or apply.

    Both steps are loose checkboxes because they are asked for loose:
    «Generar» to review the diff before touching anything, «Aplicar» to
    bring up to date a database left behind with migrations in the repo.

    Only the local database: on the VPS canone's `deploy.py` migrates
    (ADR-0060).
    """
    if generate:
        ctx.step("generate")
        generate_migration(ctx, message=message)
    if apply:
        ctx.step("apply")
        apply_migrations(ctx)


def bind_all() -> None:
    """Register the group's functions in the catalog."""
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
