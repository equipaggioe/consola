"""Resolve the local or tunneled database and the superuser channel."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.services import canone, ports, ssh, vps
from app.services.context import TaskContext
from app.services.envfile import Config, read_value
from app.services.errors import TaskError
from app.services.host import HOST

LOCAL = "local"
REMOTE = "remote"
SCOPES = (LOCAL, REMOTE)

# The first loose number of a Postgres version is the major, both in
# what `version()` returns and what `pg_dump --version` prints.
_VERSION_MAJOR = re.compile(r"(\d+)")
_URL_PASSWORD = re.compile(r"://([^:/@]+):([^@]+)@")
# Where the VPS's PostgreSQL listens, and the local port a tunnel to it
# tries first (despliegue.md of canone, «PostgreSQL»).
VPS_SOCKET = "/run/postgresql/.s.PGSQL.5432"
TUNNEL_PORT = 5432


def build_url(*, user: str, password: str, host: str, port: int, name: str) -> str:
    """Return a Postgres URL."""
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def mask_url(url: str) -> str:
    """Return the URL without the password, for the console."""
    return _URL_PASSWORD.sub(r"://\1:******@", url)


def local_port() -> int:
    """Return the local Postgres's port, from its own configuration.

    A machine with several versions does not always leave the right one
    on 5432; reading `postgresql.conf` avoids a silent «cannot connect»
    against the wrong port. `HOST.pg_port` knows where that file is.
    """
    return HOST.pg_port()


def server_url(root: Path) -> str:
    """Return the DATABASE_URL in the server's own `server/.env`.

    It is the only allowed read of that file: Consola never writes it
    (ADR-0064). It preloads the explorer's form.
    """
    return read_value(str(root / "server" / ".env"), "DATABASE_URL")


@dataclass
class Connection:
    """A resolved connection, with its tunnel if one had to open.

    This is the real `scope` axis: the function always runs in the app,
    and all that changes is which database it points at.
    """

    url: str
    scope: str
    tunnel: ssh.Tunnel | None = None
    # The same data as in `url`, loose. Command line tools (`pg_dump`,
    # `pg_restore`) do not get the URL: the password would travel in
    # argv and stay in the run's log. They take `-h/-p/-U` and the
    # password through `PGPASSWORD`, like the superuser channel. On
    # remote the port is the tunnel's, which `connect` chooses.
    host: str = "127.0.0.1"
    port: int = 0

    @property
    def is_remote(self) -> bool:
        """Return whether it goes through a tunnel."""
        return self.scope == REMOTE

    @property
    def safe_url(self) -> str:
        """Return the URL with its password masked."""
        return mask_url(self.url)

    def close(self) -> None:
        """Close the tunnel, if any."""
        if self.tunnel is not None:
            self.tunnel.close()
            self.tunnel = None

    def __enter__(self) -> "Connection":
        """Return the connection, for a `with` block."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the tunnel when leaving the `with` block."""
        self.close()


def credentials(config: Config) -> tuple[str, str, str]:
    # `Config.get` resolves the defaults of DB_USER (the repo's name)
    # and DB_NAME (`<repo>_db`) by itself; they need no repeating here.
    """Return the database's user, password and name."""
    user = config.get("DB_USER")
    password = config.require("DB_PASSWORD")
    name = config.get("DB_NAME")
    return user, password, name


def connect(ctx: TaskContext, scope: str = LOCAL) -> Connection:
    """Return the connection of that scope, opening a tunnel if remote.

    It never connects to the VPS's public IP: traffic always goes by
    `127.0.0.1` through the SSH tunnel (ADR-0016).
    """
    if scope not in SCOPES:
        raise TaskError(
            QCoreApplication.translate("database", "Ambito invalido: {0!r}. Usa {1}.").format(
                scope, " | ".join(SCOPES)
            )
        )

    user, password, name = credentials(ctx.config)
    ctx.guard(password)

    if scope == LOCAL:
        resolved_port = local_port()
        url = build_url(
            user=user, password=password, host="127.0.0.1", port=resolved_port, name=name
        )
        ctx.info(
            QCoreApplication.translate("database", "Base de datos LOCAL: {0}").format(
                mask_url(url)
            )
        )
        return Connection(url, LOCAL, port=resolved_port)

    remote = ssh.resolve_remote(ctx.config)
    ssh_remote = vps.postgres_port(remote)
    local = ports.resolve_port(
        ssh_remote, label=QCoreApplication.translate("database", "puerto del tunel")
    )

    ctx.warn(
        QCoreApplication.translate(
            "database", "Base de datos REMOTA del VPS: los cambios afectan a {0}."
        ).format(remote.host)
    )
    tunnel = ssh.open_tunnel(remote, local_port=local, destination=f"127.0.0.1:{ssh_remote}")
    ctx.hold_tunnel(tunnel)
    ctx.info(
        QCoreApplication.translate("database", "Tunel SSH abierto: {0} -> {1}:{2}").format(
            tunnel.endpoint, remote.host, ssh_remote
        )
    )

    url = build_url(user=user, password=password, host="127.0.0.1", port=local, name=name)
    return Connection(url, REMOTE, tunnel, port=local)


def reader(app: str) -> str:
    """Return the role that reads a canone app's database."""
    return f"{app}_read"


def vps_tunnel(ctx: TaskContext) -> ssh.Tunnel:
    """Open a tunnel to the socket of the VPS's PostgreSQL.

    canone's roles have no password and enter by `peer`. Through the
    socket, PostgreSQL sees the account `sshd` opens the tunnel with,
    the one that administers, and `install.py` lets it in only as
    `<app>_read`: it reads, and changes nothing.
    """
    remote = ssh.resolve_remote(ctx.config)
    local = ports.resolve_port(
        TUNNEL_PORT, label=QCoreApplication.translate("database", "puerto del tunel")
    )
    tunnel = ssh.open_tunnel(remote, local_port=local, destination=VPS_SOCKET)
    ctx.hold_tunnel(tunnel)
    ctx.info(
        QCoreApplication.translate("database", "Tunel SSH abierto: {0} -> {1}:{2}").format(
            tunnel.endpoint, remote.host, VPS_SOCKET
        )
    )
    return tunnel


def connect_vps(ctx: TaskContext) -> Connection:
    """Return the VPS's database as `<app>_read`, through `vps_tunnel`.

    The database is `<app>`, the one `install.py` creates, and not
    `DB_NAME`, which names the local one.
    """
    _, app = canone.origin(ctx.root)
    tunnel = vps_tunnel(ctx)
    url = f"postgresql://{reader(app)}@127.0.0.1:{tunnel.local_port}/{app}"
    return Connection(url, REMOTE, tunnel, port=tunnel.local_port)


# --- superuser channel ---


def quote_ident(value: str) -> str:
    """Quote an SQL identifier.

    Without this, a name with capitals or a hyphen breaks the DDL, and a
    malicious name rewrites it.
    """
    if not value or not all(c.isalnum() or c in "_-" for c in value):
        raise TaskError(
            QCoreApplication.translate("database", "Identificador SQL invalido: {0!r}").format(
                value
            )
        )
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def quote_literal(value: str) -> str:
    """Quote an SQL literal."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


@dataclass
class Admin:
    """Run SQL as the local Postgres superuser.

    It is the channel for life cycle operations such as creating or
    deleting a role or database: unlike `Connection`, which connects as
    the application, this one needs admin rights, so it goes through
    `psql` and not the driver. On the VPS, canone's `install.py` and
    `database.py` do that.
    """

    argv: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def _command(self, database: str, sql: str, *, tuples: bool = False) -> list[str]:
        flags = ["-tA"] if tuples else []
        return [*self.argv, "-v", "ON_ERROR_STOP=1", "-X", "-q", *flags, "-d", database, "-c", sql]

    def execute(self, ctx: TaskContext, sql: str, *, database: str = "postgres") -> None:
        """Run SQL, showing it in the log."""
        ctx.run(self._command(database, sql), env=self.env or None, cwd=None)

    def query(self, ctx: TaskContext, sql: str, *, database: str = "postgres") -> list[str]:
        """Run SQL and return its output, without the log."""
        output = ctx.capture(
            self._command(database, sql, tuples=True), env=self.env or None, cwd=None
        )
        return [line.strip() for line in output.splitlines() if line.strip()]


def pg_tool(name: str) -> Path:
    """Return the executable `name` of the local PostgreSQL install.

    Three channels use it: `psql` for the local superuser channel, and
    `pg_dump` and `pg_restore` for backup and restore, which run on this
    side in both scopes and reach the remote database through the
    tunnel.

    The newest version first: a machine with 15 and 17 has to use 17,
    because 15 refuses to read a 17 server. `HOST.pg_tool` knows where
    each version installs.
    """
    return HOST.pg_tool(name)


def major_of(version: str) -> int:
    """Return a Postgres version's major number, wherever it came from.

    It serves the two forms it arrives in: the server's, from
    `version()`, 'PostgreSQL 16.2 (Debian...) on x86_64...', and the
    local binary's, from `pg_dump --version`, 'pg_dump (PostgreSQL)
    16.2'. In both the first loose number is the major.
    """
    match = _VERSION_MAJOR.search(version)
    if not match:
        raise TaskError(
            QCoreApplication.translate(
                "database", "No se pudo leer la version de Postgres: {0!r}"
            ).format(version)
        )
    return int(match.group(1))


def check_tool_version(ctx: TaskContext, tool: Path, client: str, server: str) -> None:
    """Stop if the local binary is older than the server.

    `pg_dump` and `pg_restore` refuse to work against a newer server,
    and say so with a raw «server version mismatch» mid-run. Checking
    first leaves a message naming both versions and the exact binary
    chosen, which is what fixing it takes.
    """
    if major_of(client) >= major_of(server):
        return
    raise TaskError(
        QCoreApplication.translate(
            "database",
            "{0} es de PostgreSQL {1} y el servidor es {2}: las herramientas cliente "
            "no leen un servidor mas nuevo. Instala PostgreSQL {3} o posterior en "
            "esta maquina ({4}).",
        ).format(tool.name, major_of(client), major_of(server), major_of(server), tool)
    )


def resolve_admin(ctx: TaskContext) -> Admin:
    """Return the local superuser channel."""
    # Setting.default='postgres' already covers empty
    superuser = ctx.config.get("PG_SUPERUSER")
    password = ctx.config.require("PG_PASSWORD")
    ctx.guard(password)
    argv = [str(pg_tool("psql")), "-U", superuser, "-h", "127.0.0.1", "-p", str(local_port())]
    return Admin(argv=argv, env={"PGPASSWORD": password})
