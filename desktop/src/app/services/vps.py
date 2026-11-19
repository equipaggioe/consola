"""Deployment paths, systemd, journal and server health on the VPS."""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.ssh import Remote, capture, quote, reachable, succeeds

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
# names. Each piece in Java runs in its instance of `<app>-java@`, named
# after its folder, and the VPS says which ones it has. Restarting them
# or reading their journal asks for no new buttons: it asks that the
# existing ones know where to point.

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
# The axis value of a piece in Java is `java:<piece>`, and the piece is
# named as canone's `scripts/java.py` asks.
JAVA = "java:"
_PIECE = re.compile(r"[a-z][a-z0-9-]*")
# The axis value of a task with its own timer is `task:<task>`, and its
# unit is its instance of `<app>-task@` (ADR-0151 of canone), named as
# `install.py --task` asks.
TASK = "task:"
_TASK = re.compile(r"[a-z][a-z0-9_]{0,30}")
# The axis value of a task that drives Chromium is `browser:<task>`, and
# its unit is its instance of `<app>-browser@` (ADR-0172 of canone).
BROWSER = "browser:"
# Each kind of task, by its axis prefix: its unit and its label.
_TASK_UNITS = {TASK: ("task", "Tarea"), BROWSER: ("browser", "Tarea con navegador")}


def _fixed_units(app: str) -> dict[str, str]:
    """Return the values with a fixed unit name, and their units."""
    found = {value: unit.format(app=app) for value, unit in _APP_UNITS.items()}
    return found | {service: service for service in PACKAGE_SERVICES}


def service_labels(values: Iterable[str]) -> dict[str, str]:
    """Return what the axis shows for each value."""
    pieces = {v: f"Java: {v.removeprefix(JAVA)}" for v in values if v.startswith(JAVA)}
    tasks = {
        v: f"{label}: {v.removeprefix(prefix)}"
        for v in values
        for prefix, (_, label) in _TASK_UNITS.items()
        if v.startswith(prefix)
    }
    return {**SERVICE_LABELS, **pieces, **tasks}


def resolve_service(app: str, which: str = MAIN_SERVICE) -> str:
    """Return the unit name behind a `service` axis value."""
    piece = which.removeprefix(JAVA)
    if which.startswith(JAVA) and _PIECE.fullmatch(piece):
        return f"{app}-java@{piece}"
    for prefix, (unit, _) in _TASK_UNITS.items():
        task = which.removeprefix(prefix)
        if which.startswith(prefix) and _TASK.fullmatch(task):
            return f"{app}-{unit}@{task}"
    found = _fixed_units(app)
    if which not in found:
        raise TaskError(f"Servicio desconocido: {which}")
    return found[which]


def installed_services(remote: Remote, app: str) -> list[str]:
    """Which services of the axis exist on THIS VPS, in a single query.

    Offering them all would offer to restart a coturn that is not
    installed. Asking is one SSH round trip, so all are asked together
    and `services/catalog.py` caches the answer. It raises if it cannot
    ask: offering them all then would hide that the VPS does not answer
    (ADR-0076).

    The pieces in Java and the tasks with their own timer are listed and
    not asked one by one: `systemctl cat` answers for any instance once
    the template is installed, and the VPS is what knows which ones
    `install.py` enabled.
    """
    names = {unit: value for value, unit in _fixed_units(app).items()}
    if not reachable(remote):
        raise TaskError(
            f"No se entra al VPS como {remote.target}: no se puede preguntar qué servicios tiene."
        )
    listing = " ".join(quote(n) for n in names)
    pieces = quote(f"{app}-java@*")
    tasks = " ".join(quote(f"{app}-{unit}@*.timer") for unit, _ in _TASK_UNITS.values())
    # `true`: the exit code of the loop is that of its last unit, and a
    # missing one is fine.
    output = capture(
        remote,
        f'for s in {listing}; do systemctl cat "$s" >/dev/null 2>&1 && echo "$s"; done; '
        f"systemctl list-units --all --no-legend --plain {pieces} {tasks}"
        " | awk '{print $1}'; true",
    )
    found = [value for line in output.split() if (value := _axis_value(app, line, names))]
    return list(dict.fromkeys(found))


def _axis_value(app: str, line: str, names: dict[str, str]) -> str:
    """Return the axis value of a unit the VPS answered, or `''`."""
    if line in names:
        return names[line]
    piece = line.removeprefix(f"{app}-java@").removesuffix(".service")
    if line.startswith(f"{app}-java@") and _PIECE.fullmatch(piece):
        return f"{JAVA}{piece}"
    for prefix, (unit, _) in _TASK_UNITS.items():
        task = line.removeprefix(f"{app}-{unit}@").removesuffix(".timer")
        if line.startswith(f"{app}-{unit}@") and line.endswith(".timer") and _TASK.fullmatch(task):
            return f"{prefix}{task}"
    return ""


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
