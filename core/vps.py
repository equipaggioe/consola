from __future__ import annotations

from .envfile import Config
from .errors import TaskError
from .ssh import Remote, capture, quote, reachable, run, succeeds

SUDO = 'sudo -n'


# --- rutas del despliegue --------------------------------------------------

def repo_name(config: Config) -> str:
    """Nombre del repo tal como queda en el VPS.

    Se deriva de GIT_REPO_URL, que es la unica fuente que coincide con lo que
    `git clone` va a crear del otro lado; el nombre de la carpeta local puede
    no coincidir y por eso no se usa como default silencioso.
    """
    url = config.get('GIT_REPO_URL')
    if url:
        return url.rstrip('/').rsplit('/', 1)[-1].removesuffix('.git')
    if config.repo_name:
        return config.repo_name
    raise TaskError('No se puede deducir el nombre del repo: falta GIT_REPO_URL.')


def deploy_root(config: Config) -> str:
    """Carpeta del repo en el VPS: `<VPS_DEPLOY_DIR>/<repo>`."""
    base = config.require('VPS_DEPLOY_DIR').rstrip('/')
    return f'{base}/{repo_name(config)}'


def remote_path(config: Config, *parts: str) -> str:
    """Ruta remota que respeta la misma jerarquia relativa que el repo local."""
    tail = '/'.join(p.strip('/').replace('\\', '/') for p in parts if p)
    root = deploy_root(config)
    return f'{root}/{tail}' if tail else root


def remote_python(config: Config) -> str:
    """Interprete del venv del server, dentro del repo desplegado."""
    return remote_path(config, config.require('VPS_PYTHON'))


# --- cuentas y paquetes ----------------------------------------------------

def user_exists(remote: Remote, user: str) -> bool:
    return succeeds(remote, f'id -u {quote(user)}')


def install_packages(ctx, remote: Remote, packages: list[str]) -> None:
    """Instala paquetes con apt, sin preguntas y sin reinstalar lo que ya esta."""
    faltan = [p for p in packages if not succeeds(remote, f'dpkg -s {quote(p)}')]
    if not faltan:
        ctx.ok('Todos los paquetes ya estaban instalados.')
        return

    ctx.info(f'Instalando: {", ".join(faltan)}')
    lista = ' '.join(quote(p) for p in faltan)
    run(ctx, remote, f'{SUDO} DEBIAN_FRONTEND=noninteractive apt-get update -qq')
    run(ctx, remote, f'{SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y {lista}')


# --- systemd ---------------------------------------------------------------

def service_name(config: Config) -> str:
    return repo_name(config)


def unit_path(service: str) -> str:
    return f'/etc/systemd/system/{service}.service'


def service_exists(remote: Remote, service: str) -> bool:
    return succeeds(remote, f'test -f {quote(unit_path(service))}')


def service_state(remote: Remote, service: str) -> str:
    """`missing` | `active` | `inactive` | `failed`.

    Los scripts asumian que el servicio existia y morian con un error de
    systemctl; aca la distincion permite saltear el paso con un aviso.
    """
    if not service_exists(remote, service):
        return 'missing'
    return capture(remote, f'systemctl is-active {quote(service)}', check=False).strip() or 'inactive'


def systemctl(ctx, remote: Remote, action: str, service: str, *, check: bool = True) -> int:
    """Una accion de systemd sobre el servicio del proyecto.

    Es la atomica que reusan `install_systemd` y `update_remote` en vez de
    reimplementar `enable`/`start` cada uno por su lado (PLAN.md 7, caso 7).
    """
    if action not in ALL_ACTIONS:
        raise TaskError(f'Accion de systemd desconocida: {action}')
    if action == 'daemon-reload':
        return run(ctx, remote, f'{SUDO} systemctl daemon-reload', check=check)
    return run(ctx, remote, f'{SUDO} systemctl {action} {quote(service)}', check=check)


BUTTON_ACTIONS = ('start', 'stop', 'restart', 'status')
MENU_ACTIONS = ('enable', 'disable', 'reload', 'is-active', 'is-enabled', 'daemon-reload')
ALL_ACTIONS = BUTTON_ACTIONS + MENU_ACTIONS


def render_unit(
    *,
    description: str,
    user: str,
    working_dir: str,
    exec_start: str,
    environment: dict[str, str] | None = None,
) -> str:
    """Texto de la unidad systemd. Se arma aca y se sube; no se edita a mano en el VPS."""
    env_lines = ''.join(
        f'Environment="{k}={v}"\n' for k, v in (environment or {}).items()
    )
    return (
        '[Unit]\n'
        f'Description={description}\n'
        'After=network.target postgresql.service\n'
        '\n'
        '[Service]\n'
        'Type=simple\n'
        f'User={user}\n'
        f'WorkingDirectory={working_dir}\n'
        f'{env_lines}'
        f'ExecStart={exec_start}\n'
        'Restart=always\n'
        'RestartSec=3\n'
        '\n'
        '[Install]\n'
        'WantedBy=multi-user.target\n'
    )


def write_unit(ctx, remote: Remote, service: str, content: str) -> str:
    """Escribe la unidad en el VPS y recarga systemd. No la habilita ni la arranca."""
    path = unit_path(service)
    heredoc = f'{SUDO} tee {quote(path)} > /dev/null <<"CONSOLA_UNIT"\n{content}CONSOLA_UNIT'
    run(ctx, remote, heredoc)
    run(ctx, remote, f'{SUDO} systemctl daemon-reload')
    ctx.ok(f'Unidad escrita: {path}')
    return path


def journal_command(
    service: str,
    *,
    lines: int = 200,
    follow: bool = False,
    since: str = '',
    priority: str = '',
    grep: str = '',
) -> str:
    """Comando de `journalctl` con los filtros de la capacidad Ver logs.

    Es hermana de `systemctl`, no un valor suyo: los filtros no tienen sentido
    para start/stop y `logs` dejo de ser una accion de systemd (PLAN.md 1).
    """
    parts = [f'{SUDO} journalctl -u {quote(service)}', f'-n {int(lines)}']
    if follow:
        parts.append('-f')
    if since:
        parts.append(f'--since {quote(since)}')
    if priority:
        parts.append(f'-p {quote(priority)}')
    if grep:
        parts.append(f'--grep {quote(grep)}')
    parts.append('--no-pager')
    return ' '.join(parts)


# --- postgres del VPS ------------------------------------------------------

def postgres_port(remote: Remote) -> int:
    """Puerto real de Postgres en el VPS, preguntandoselo al propio servidor."""
    raw = capture(remote, f'{SUDO} -u postgres psql -tAc "SHOW port;"').strip()
    if not raw.isdigit():
        raise TaskError(f'Respuesta inesperada al pedir el puerto de Postgres: {raw!r}')
    return int(raw)


def health(remote: Remote, service: str) -> dict[str, str]:
    """Resumen de un vistazo para el chequeo de salud: acceso, servicio, disco y memoria.

    `acceso` va primero y corta. Las otras cuatro consultas usan `check=False`,
    asi que con el SSH caido devolvian vacio y `service_state` caia en 'missing':
    el resumen anunciaba un servidor destruido cuando la verdad era que no se
    llegaba a la maquina, y mandaba a arreglar lo que no estaba roto.
    """
    if not reachable(remote):
        return {'acceso': f'SIN ACCESO SSH a {remote.target}'}
    return {
        'acceso': f'ok ({remote.target})',
        'servicio': service_state(remote, service),
        'uptime': capture(remote, 'uptime -p', check=False),
        'disco': capture(remote, "df -h / | awk 'NR==2 {print $5\" usado de \"$2}'", check=False),
        'memoria': capture(remote, "free -h | awk 'NR==2 {print $3\" / \"$2}'", check=False),
    }
