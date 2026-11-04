from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core import ports, ssh, vps
from app.core.envfile import Config, read_value
from app.core.errors import TaskError
from app.core.host import HOST

LOCAL = "local"
REMOTE = "remoto"
SCOPES = (LOCAL, REMOTE)

# El primer numero suelto de una version de Postgres es el mayor, tanto en lo que
# devuelve `version()` como en lo que imprime `pg_dump --version`.
_VERSION_MAJOR = re.compile(r"(\d+)")
_URL_PASSWORD = re.compile(r"://([^:/@]+):([^@]+)@")


def build_url(*, user: str, password: str, host: str, port: int, name: str) -> str:
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def mask_url(url: str) -> str:
    """La URL sin la contrasena, para poder mostrarla en la consola."""
    return _URL_PASSWORD.sub(r"://\1:******@", url)


def local_port() -> int:
    """Puerto de Postgres local, leido de su propia configuracion.

    Una maquina con varias versiones no siempre deja la buena en 5432; leer
    `postgresql.conf` evita el 'no conecta' silencioso contra el puerto
    equivocado. Donde esta ese archivo lo sabe `HOST.pg_port`.
    """
    return HOST.pg_port()


def server_url(root: Path) -> str:
    """La DATABASE_URL que el propio server declara en `server/.env`.

    Es la unica lectura permitida de ese archivo: Consola nunca lo escribe
    (ADR-0064). Sirve para precargar el formulario del explorador.
    """
    return read_value(str(root / "server" / ".env"), "DATABASE_URL")


@dataclass
class Connection:
    """Una conexion resuelta, con su tunel si hizo falta abrirlo.

    Esto es el eje `scope` de verdad: en los scripts, `RUN_REMOTE` reenviaba el
    script entero al VPS por SSH. Aca la funcion corre siempre en la app y lo
    unico que cambia es contra que base apunta.
    """

    url: str
    scope: str
    tunnel: ssh.Tunnel | None = None
    # Los mismos datos que ya van dentro de `url`, sueltos. Las herramientas de
    # linea de comandos (`pg_dump`, `pg_restore`) no reciben la URL: la
    # contrasena viajaria en el argv y quedaria en el log de la corrida. Toman
    # `-h/-p/-U` y la contrasena por `PGPASSWORD`, igual que el canal de
    # superusuario. En remoto el puerto es el del tunel, que lo elige `connect`.
    host: str = "127.0.0.1"
    port: int = 0

    @property
    def is_remote(self) -> bool:
        return self.scope == REMOTE

    @property
    def safe_url(self) -> str:
        return mask_url(self.url)

    def close(self) -> None:
        if self.tunnel is not None:
            self.tunnel.close()
            self.tunnel = None

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def credentials(config: Config) -> tuple[str, str, str]:
    # Los defaults de DB_USER (el nombre del repo) y DB_NAME (`<repo>_db`)
    # los resuelve `Config.get` solo; no hay que repetirlos aca.
    user = config.get("DB_USER")
    password = config.require("DB_PASSWORD")
    name = config.get("DB_NAME")
    return user, password, name


def connect(ctx, scope: str = LOCAL) -> Connection:
    """Devuelve la conexion del ambito pedido, abriendo el tunel si es remota.

    Nunca se conecta a la IP publica del VPS: el trafico va siempre por
    `127.0.0.1` a traves del tunel SSH (ADR-0016).
    """
    if scope not in SCOPES:
        raise TaskError(f"Ambito invalido: {scope!r}. Usa {' | '.join(SCOPES)}.")

    user, password, name = credentials(ctx.config)
    ctx.guard(password)

    if scope == LOCAL:
        puerto = local_port()
        url = build_url(user=user, password=password, host="127.0.0.1", port=puerto, name=name)
        ctx.info(f"Base de datos LOCAL: {mask_url(url)}")
        return Connection(url, LOCAL, port=puerto)

    remote = ssh.resolve_remote(ctx.config)
    remoto = vps.postgres_port(remote)
    local = ports.resolve_port(remoto, label="puerto del tunel")

    ctx.warn(f"Base de datos REMOTA del VPS: los cambios afectan a {remote.host}.")
    tunnel = ssh.open_tunnel(remote, local_port=local, remote_port=remoto)
    ctx.hold_tunnel(tunnel)
    ctx.info(f"Tunel SSH abierto: {tunnel.endpoint} -> {remote.host}:{remoto}")

    url = build_url(user=user, password=password, host="127.0.0.1", port=local, name=name)
    return Connection(url, REMOTE, tunnel, port=local)


def vps_url(ctx, remote: ssh.Remote) -> str:
    """La base del VPS vista DESDE el VPS: `127.0.0.1` y su puerto real, sin tunel.

    `connect(REMOTE)` devuelve la misma base vista desde aca, y para eso abre un
    tunel. El tunel existe para que un proceso de esta maquina alcance esa base;
    cuando el proceso corre del otro lado (`core/runner.py`) sobra, y su puerto
    local no significaria nada alli.
    """
    user, password, name = credentials(ctx.config)
    ctx.guard(password)
    return build_url(
        user=user, password=password, host="127.0.0.1", port=vps.postgres_port(remote), name=name
    )


# ---------------------------------------------------------------------------
# Canal de superusuario
# ---------------------------------------------------------------------------


def quote_ident(value: str) -> str:
    """Cita un identificador SQL. Sin esto, un nombre con mayusculas o guion
    rompe el DDL y un nombre malicioso lo reescribe.
    """
    if not value or not all(c.isalnum() or c in "_-" for c in value):
        raise TaskError(f"Identificador SQL invalido: {value!r}")
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def quote_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


@dataclass
class Admin:
    """Ejecuta SQL como superusuario de Postgres, local o en el VPS.

    Es el mecanismo del eje `scope` para las operaciones de ciclo de vida
    (crear rol, crear base, borrarlas): a diferencia de `Connection`, que
    conecta como la aplicacion, este canal necesita permisos de administrador
    y por eso pasa por `psql`, no por el driver.
    """

    scope: str
    remote: "ssh.Remote | None" = None
    argv: list = field(default_factory=list)
    env: dict = field(default_factory=dict)

    @property
    def is_remote(self) -> bool:
        return self.scope == REMOTE

    def _command(self, database: str, sql: str, *, tuples: bool = False) -> list[str]:
        flags = ["-tA"] if tuples else []
        if self.is_remote:
            assert self.remote is not None
            remoto = " ".join(
                [
                    "sudo -n -u postgres psql -v ON_ERROR_STOP=1 -X -q",
                    *flags,
                    "-d",
                    ssh.quote(database),
                    "-c",
                    ssh.quote(sql),
                ]
            )
            return self.remote.argv(remoto)
        return [*self.argv, "-v", "ON_ERROR_STOP=1", "-X", "-q", *flags, "-d", database, "-c", sql]

    def execute(self, ctx, sql: str, *, database: str = "postgres") -> None:
        ctx.run(self._command(database, sql), env=self.env or None, cwd=None)

    def query(self, ctx, sql: str, *, database: str = "postgres") -> list[str]:
        salida = ctx.capture(
            self._command(database, sql, tuples=True), env=self.env or None, cwd=None
        )
        return [line.strip() for line in salida.splitlines() if line.strip()]


def pg_tool(name: str) -> Path:
    """El ejecutable `name` de la instalacion local de PostgreSQL.

    Lo usan tres canales: `psql` para el canal de superusuario local, y
    `pg_dump`/`pg_restore` para el respaldo y la restauracion, que corren de este
    lado en los dos ambitos y alcanzan la base remota por el tunel.

    La version mas nueva primero: una maquina con 15 y 17 instaladas tiene que
    usar la de 17, porque la de 15 se niega a leer un servidor 17. Donde se
    instala cada version lo sabe `HOST.pg_tool`.
    """
    return HOST.pg_tool(name)


def major_of(version: str) -> int:
    """El numero mayor de una version de Postgres, venga de donde venga.

    Sirve para las dos formas en que llega: la del servidor —`version()`, que
    devuelve 'PostgreSQL 16.2 (Debian...) on x86_64...'— y la del binario local
    —`pg_dump --version`, que devuelve 'pg_dump (PostgreSQL) 16.2'—. En las dos
    el primer numero suelto es el mayor.
    """
    match = _VERSION_MAJOR.search(version)
    if not match:
        raise TaskError(f"No se pudo leer la version de Postgres: {version!r}")
    return int(match.group(1))


def check_tool_version(ctx, tool: Path, client: str, server: str) -> None:
    """Corta si el binario local es mas viejo que el servidor.

    `pg_dump` y `pg_restore` se niegan a trabajar contra un servidor mas nuevo
    que ellos, y lo dicen con un «server version mismatch» crudo a mitad de la
    corrida. Comprobarlo antes deja un mensaje que nombra las dos versiones y el
    binario exacto que se eligio, que es lo que hace falta para arreglarlo.
    """
    if major_of(client) >= major_of(server):
        return
    raise TaskError(
        f"{tool.name} es de PostgreSQL {major_of(client)} y el servidor es {major_of(server)}: "
        f"las herramientas cliente no leen un servidor mas nuevo. "
        f"Instala PostgreSQL {major_of(server)} o posterior en esta maquina ({tool})."
    )


def resolve_admin(ctx, scope: str = LOCAL) -> Admin:
    """El canal de superusuario del ambito pedido."""
    if scope == REMOTE:
        return Admin(REMOTE, remote=ssh.resolve_remote(ctx.config))

    superuser = ctx.config.get("PG_SUPERUSER")  # Setting.default='postgres' ya cubre el vacio
    password = ctx.config.require("PG_PASSWORD")
    ctx.guard(password)
    argv = [str(pg_tool("psql")), "-U", superuser, "-h", "127.0.0.1", "-p", str(local_port())]
    return Admin(LOCAL, argv=argv, env={"PGPASSWORD": password})
