from __future__ import annotations

from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.ssh import Remote, capture, quote, reachable, succeeds

SUDO = "sudo -n"


# --- rutas del despliegue --------------------------------------------------


def repo_name(config: Config) -> str:
    """Nombre del repo tal como queda en el VPS.

    Se deriva de GIT_REPO_URL, que es la unica fuente que coincide con lo que
    `git clone` va a crear del otro lado; el nombre de la carpeta local puede
    no coincidir y por eso no se usa como default silencioso.
    """
    url = config.get("GIT_REPO_URL")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    if config.repo_name:
        return config.repo_name
    raise TaskError("No se puede deducir el nombre del repo: falta GIT_REPO_URL.")


def deploy_root(config: Config) -> str:
    """Carpeta del repo en el VPS: `<VPS_DEPLOY_DIR>/<repo>`."""
    base = config.require("VPS_DEPLOY_DIR").rstrip("/")
    return f"{base}/{repo_name(config)}"


def remote_path(config: Config, *parts: str) -> str:
    """Ruta remota que respeta la misma jerarquia relativa que el repo local."""
    tail = "/".join(p.strip("/").replace("\\", "/") for p in parts if p)
    root = deploy_root(config)
    return f"{root}/{tail}" if tail else root


def remote_python(config: Config) -> str:
    """Interprete del venv del server, dentro del repo desplegado."""
    return remote_path(config, config.require("VPS_PYTHON"))


# --- systemd ---------------------------------------------------------------
#
# Las unidades de un VPS las instala `install.py` de canone: el repo no declara
# ninguna, y se llaman por su `<app>` (ADR-0068). Las de un paquete tienen nombre
# fijo. Reiniciarlas o leerles el journal no pide botones nuevos: pide que los
# que ya existen sepan a cual apuntar.

MAIN_SERVICE = "server"
_APP_UNITS = {
    MAIN_SERVICE: "{app}",
    "valkey": "valkey-server@{app}",
    "sweep": "{app}-sweep",
    "purge": "{app}-purge",
    "dump": "{app}-dump",
    "backup": "{app}-backup",
}
PACKAGE_SERVICES = ("caddy", "coturn")
# The receiver asks for the backup through `backup-request`, which checks its tunnel first.
# Started from here, restic would retry for hours without it (ADR-0073).
RECEIVER_SERVICE = "backup"
STARTING_ACTIONS = ("start", "restart")
SERVICE_LABELS = {
    MAIN_SERVICE: "Servidor",
    "valkey": "Valkey",
    "sweep": "Barrido",
    "purge": "Purga",
    "dump": "Volcado",
    "backup": "Respaldo",
    "caddy": "Caddy",
    "coturn": "Coturn",
}


def resolve_service(app: str, which: str = MAIN_SERVICE) -> str:
    """El nombre real de la unidad detras del valor del eje `service`."""
    if which in PACKAGE_SERVICES:
        return which
    if which not in _APP_UNITS:
        raise TaskError(f"Servicio desconocido: {which}")
    return _APP_UNITS[which].format(app=app)


def installed_services(remote: Remote, app: str) -> list[str]:
    """Which services of the axis exist on THIS VPS, in a single query.

    Offering them all would offer to restart a coturn that is not installed. Asking is one
    SSH round trip, so all are asked together and `core/catalog.py` caches the answer. It
    raises if it cannot ask: offering them all then would hide that the VPS does not answer
    (ADR-0076).
    """
    ejes = [*_APP_UNITS, *PACKAGE_SERVICES]
    nombres = {resolve_service(app, s): s for s in ejes}
    if not reachable(remote):
        raise TaskError(
            f"No se entra al VPS como {remote.target}: no se puede preguntar qué servicios tiene."
        )
    lista = " ".join(quote(n) for n in nombres)
    # `true`: the exit code of the loop is that of its last unit, and a missing one is fine.
    salida = capture(
        remote, f'for s in {lista}; do systemctl cat "$s" >/dev/null 2>&1 && echo "$s"; done; true'
    )
    return [nombres[linea] for linea in salida.split() if linea in nombres]


def unit_installed(remote: Remote, service: str) -> bool:
    """Si systemd conoce la unidad, este donde este su archivo.

    Las de un paquete apt —coturn, caddy— viven en /lib/systemd/system: mirar
    solo /etc/systemd/system las daba por `missing` estando instaladas y
    corriendo.
    """
    return succeeds(remote, f"systemctl cat {quote(service)}")


def service_state(remote: Remote, service: str) -> str:
    """`missing` | `active` | `inactive` | `failed`.

    Los scripts asumian que el servicio existia y morian con un error de
    systemctl; aca la distincion permite saltear el paso con un aviso.
    """
    if not unit_installed(remote, service):
        return "missing"
    return (
        capture(remote, f"systemctl is-active {quote(service)}", check=False).strip() or "inactive"
    )


def systemctl_command(action: str, service: str) -> str:
    """Una accion de systemd sobre un servicio del VPS, sin `sudo`."""
    if action not in ALL_ACTIONS:
        raise TaskError(f"Accion de systemd desconocida: {action}")
    if action == "daemon-reload":
        return "systemctl daemon-reload"
    return f"systemctl {action} {quote(service)}"


BUTTON_ACTIONS = ("start", "stop", "restart", "status")
MENU_ACTIONS = ("enable", "disable", "reload", "is-active", "is-enabled", "daemon-reload")
ALL_ACTIONS = BUTTON_ACTIONS + MENU_ACTIONS


def journal_command(
    service: str,
    *,
    lines: int = 200,
    follow: bool = False,
    since: str = "",
    priority: str = "",
    grep: str = "",
) -> str:
    """Comando de `journalctl` con los filtros de la capacidad Ver logs, sin `sudo`.

    Es hermana de `systemctl`, no un valor suyo: los filtros no tienen sentido
    para start/stop y `logs` dejo de ser una accion de systemd (ADR-0023).
    """
    parts = [f"journalctl -u {quote(service)}", f"-n {int(lines)}"]
    if follow:
        parts.append("-f")
    if since:
        parts.append(f"--since {quote(since)}")
    if priority:
        parts.append(f"-p {quote(priority)}")
    if grep:
        parts.append(f"--grep {quote(grep)}")
    parts.append("--no-pager")
    return " ".join(parts)


# --- postgres del VPS ------------------------------------------------------


def postgres_port(remote: Remote) -> int:
    """Puerto real de Postgres en el VPS, preguntandoselo al propio servidor."""
    raw = capture(remote, f'{SUDO} -u postgres psql -tAc "SHOW port;"').strip()
    if not raw.isdigit():
        raise TaskError(f"Respuesta inesperada al pedir el puerto de Postgres: {raw!r}")
    return int(raw)


# Un GET al servidor por loopback, donde escucha siempre (ADR-0077 de canone). Va
# en Python porque es lo unico que `install.py` asegura: curl no esta entre los
# paquetes de la maquina. El token entra por stdin para no quedar en `ps`.
_SERVER_GET = (
    "import http.client, sys; "
    "c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=10); "
    "token = sys.stdin.readline().strip(); "
    "c.request('GET', sys.argv[1], headers={'Authorization': 'Bearer ' + token}); "
    "r = c.getresponse(); print(r.status); print(r.read().decode())"
)


def server_get(remote: Remote, path: str, token: str = "") -> tuple[str, str]:
    """`GET <path>` del servidor: su estado y su cuerpo. Sin respuesta, el estado va vacio."""
    salida = capture(
        remote,
        f"python3 -c {quote(_SERVER_GET)} {quote(path)}",
        check=False,
        stdin_text=f"{token}\n",
    )
    estado, _, cuerpo = salida.partition("\n")
    return estado, cuerpo


def health(remote: Remote, service: str) -> dict[str, str]:
    """Resumen de un vistazo para el chequeo de salud: servicio, API, disco y memoria."""
    return {
        "acceso": f"ok ({remote.target})",
        "servicio": service_state(remote, service),
        "api": server_get(remote, "/api/health")[0],
        "uptime": capture(remote, "uptime -p", check=False),
        "carga": capture(remote, "uptime | sed 's/.*load average: //'", check=False),
        "disco": capture(remote, "df -h / | awk 'NR==2 {print $5\" usado de \"$2}'", check=False),
        "memoria": capture(remote, "free -h | awk 'NR==2 {print $3\" / \"$2}'", check=False),
    }
