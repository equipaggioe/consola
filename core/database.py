from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from . import ports, ssh, vps
from .envfile import Config, read_value
from .errors import TaskError

LOCAL = 'local'
REMOTE = 'remoto'
SCOPES = (LOCAL, REMOTE)

_PG_WINDOWS = Path(r'C:\Program Files\PostgreSQL')
_PORT_LINE = re.compile(r"^port\s*=\s*'?(\d+)'?")
_URL_PASSWORD = re.compile(r'://([^:/@]+):([^@]+)@')


def build_url(*, user: str, password: str, host: str, port: int, name: str) -> str:
    return f'postgresql://{user}:{password}@{host}:{port}/{name}'


def mask_url(url: str) -> str:
    """La URL sin la contrasena, para poder mostrarla en la consola."""
    return _URL_PASSWORD.sub(r'://\1:******@', url)


def local_port() -> int:
    """Puerto de Postgres local, leido de su propia configuracion.

    Una instalacion de Windows con varias versiones no siempre queda en 5432;
    leer `postgresql.conf` evita el 'no conecta' silencioso contra el puerto
    equivocado.
    """
    if _PG_WINDOWS.is_dir():
        for version_dir in sorted(_PG_WINDOWS.iterdir(), reverse=True):
            conf = version_dir / 'data' / 'postgresql.conf'
            if not conf.is_file():
                continue
            for raw in conf.read_text(encoding='utf-8', errors='replace').splitlines():
                match = _PORT_LINE.match(raw.strip())
                if match:
                    return int(match.group(1))
    return 5432


def server_url(root: Path) -> str:
    """La DATABASE_URL que el propio server declara en `server/.env`.

    Es la unica lectura permitida de ese archivo: Consola nunca lo escribe
    (PLAN.md 9). Sirve para precargar el formulario del explorador.
    """
    return read_value(str(root / 'server' / '.env'), 'DATABASE_URL')


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

    def __enter__(self) -> 'Connection':
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def credentials(config: Config) -> tuple[str, str, str]:
    user = config.get('VPS_USER') or config.repo_name
    password = config.require('DB_PASSWORD')
    name = config.get('DB_NAME') or f'{user}_db'
    return user, password, name


def connect(ctx, scope: str = LOCAL) -> Connection:
    """Devuelve la conexion del ambito pedido, abriendo el tunel si es remota.

    Nunca se conecta a la IP publica del VPS: el trafico va siempre por
    `127.0.0.1` a traves del tunel SSH (PLAN.md 6).
    """
    if scope not in SCOPES:
        raise TaskError(f'Ambito invalido: {scope!r}. Usa {" | ".join(SCOPES)}.')

    user, password, name = credentials(ctx.config)
    ctx.guard(password)

    if scope == LOCAL:
        url = build_url(user=user, password=password, host='127.0.0.1',
                        port=local_port(), name=name)
        ctx.info(f'Base de datos LOCAL: {mask_url(url)}')
        return Connection(url, LOCAL)

    remote = ssh.resolve_remote(ctx.config)
    remoto = vps.postgres_port(remote)
    local = ports.resolve_port(remoto, label='puerto del tunel')

    ctx.warn(f'Base de datos REMOTA del VPS: los cambios afectan a {remote.host}.')
    tunnel = ssh.open_tunnel(remote, local_port=local, remote_port=remoto)
    ctx.info(f'Tunel SSH abierto: {tunnel.endpoint} -> {remote.host}:{remoto}')

    url = build_url(user=user, password=password, host='127.0.0.1', port=local, name=name)
    return Connection(url, REMOTE, tunnel)
