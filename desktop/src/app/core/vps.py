"""Deployment paths, systemd, journal and server health on the VPS."""

from __future__ import annotations

from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.ssh import Remote, capture, quote, reachable, succeeds

SUDO = "sudo -n"


# --- deployment paths ---


def repo_name(config: Config) -> str:
    """Return the repo's name as it stays on the VPS.

    It derives from GIT_REPO_URL, the only source that matches what `git
    clone` creates on the other side; the local folder's name may
    differ, so it is not used as a silent default.
    """
    url = config.get("GIT_REPO_URL")
    if url:
        return url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    if config.repo_name:
        return config.repo_name
    raise TaskError("No se puede deducir el nombre del repo: falta GIT_REPO_URL.")


def deploy_root(config: Config) -> str:
    """Return `<VPS_DEPLOY_DIR>/<repo>`, its folder on the VPS."""
    base = config.require("VPS_DEPLOY_DIR").rstrip("/")
    return f"{base}/{repo_name(config)}"


def remote_path(config: Config, *parts: str) -> str:
    """Return a remote path with the local repo's hierarchy."""
    tail = "/".join(p.strip("/").replace("\\", "/") for p in parts if p)
    root = deploy_root(config)
    return f"{root}/{tail}" if tail else root


# --- systemd ---
#
# canone's `install.py` installs a VPS's units: the repo declares none,
# and they go by their `<app>` (ADR-0068). A package's units have fixed
# names. Restarting them or reading their journal asks for no new
# buttons: it asks that the existing ones know where to point.

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
# The receiver asks for the backup through `backup-request`, which
# checks its tunnel first. Started from here, restic would retry for
# hours without it (ADR-0073).
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
    """Return the unit name behind a `service` axis value."""
    if which in PACKAGE_SERVICES:
        return which
    if which not in _APP_UNITS:
        raise TaskError(f"Servicio desconocido: {which}")
    return _APP_UNITS[which].format(app=app)


def installed_services(remote: Remote, app: str) -> list[str]:
    """Which services of the axis exist on THIS VPS, in a single query.

    Offering them all would offer to restart a coturn that is not
    installed. Asking is one SSH round trip, so all are asked together
    and `core/catalog.py` caches the answer. It raises if it cannot ask:
    offering them all then would hide that the VPS does not answer
    (ADR-0076).
    """
    axes = [*_APP_UNITS, *PACKAGE_SERVICES]
    names = {resolve_service(app, s): s for s in axes}
    if not reachable(remote):
        raise TaskError(
            f"No se entra al VPS como {remote.target}: no se puede preguntar qué servicios tiene."
        )
    listing = " ".join(quote(n) for n in names)
    # `true`: the exit code of the loop is that of its last unit, and a
    # missing one is fine.
    output = capture(
        remote,
        f'for s in {listing}; do systemctl cat "$s" >/dev/null 2>&1 && echo "$s"; done; true',
    )
    return [names[line] for line in output.split() if line in names]


def unit_installed(remote: Remote, service: str) -> bool:
    """Return whether systemd knows the unit, wherever its file is.

    Those of an apt package, such as coturn and caddy, live in
    /lib/systemd/system: looking only at /etc/systemd/system reported
    them `missing` while installed and running.
    """
    return succeeds(remote, f"systemctl cat {quote(service)}")


def service_state(remote: Remote, service: str) -> str:
    """Return `missing`, `active`, `inactive` or `failed`.

    The distinction lets a step skip with a notice instead of dying with
    a systemctl error.
    """
    if not unit_installed(remote, service):
        return "missing"
    return (
        capture(remote, f"systemctl is-active {quote(service)}", check=False).strip() or "inactive"
    )


def systemctl_command(action: str, service: str) -> str:
    """Return a systemd action on a VPS service, without `sudo`."""
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
    """Return the `journalctl` command for Ver logs, without `sudo`.

    It is a sibling of `systemctl`, not a value of it: filters make no
    sense for start or stop, and `logs` stopped being a systemd action
    (ADR-0023).
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


# --- the VPS's postgres ---


def postgres_port(remote: Remote) -> int:
    """Return Postgres's real port on the VPS, asking the server."""
    raw = capture(remote, f'{SUDO} -u postgres psql -tAc "SHOW port;"').strip()
    if not raw.isdigit():
        raise TaskError(f"Respuesta inesperada al pedir el puerto de Postgres: {raw!r}")
    return int(raw)


# A GET to the server over loopback, where it always listens (ADR-0077
# of canone). It is in Python because that is all `install.py` ensures:
# curl is not among the machine's packages. The token enters by stdin so
# it does not stay in `ps`.
_SERVER_GET = (
    "import http.client, sys; "
    "c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=10); "
    "token = sys.stdin.readline().strip(); "
    "c.request('GET', sys.argv[1], headers={'Authorization': 'Bearer ' + token}); "
    "r = c.getresponse(); print(r.status); print(r.read().decode())"
)


def server_get(remote: Remote, path: str, token: str = "") -> tuple[str, str]:
    """Return the server's status and body for `GET <path>`.

    Without an answer, the status stays empty.
    """
    output = capture(
        remote,
        f"python3 -c {quote(_SERVER_GET)} {quote(path)}",
        check=False,
        stdin_text=f"{token}\n",
    )
    state, _, body = output.partition("\n")
    return state, body


def health(remote: Remote, service: str) -> dict[str, str]:
    """Return a one-glance summary: service, API, disk and memory."""
    return {
        "acceso": f"ok ({remote.target})",
        "service": service_state(remote, service),
        "api": server_get(remote, "/api/health")[0],
        "uptime": capture(remote, "uptime -p", check=False),
        "carga": capture(remote, "uptime | sed 's/.*load average: //'", check=False),
        "disco": capture(remote, "df -h / | awk 'NR==2 {print $5\" usado de \"$2}'", check=False),
        "memoria": capture(remote, "free -h | awk 'NR==2 {print $3\" / \"$2}'", check=False),
    }
