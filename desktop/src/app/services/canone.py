"""What Consola passes to canone's programs (ADR-0059).

canone fixes each program by its interface: `install.py` by its
arguments, `credentials.py` by the lines it reads from stdin,
`deploy.py` by the tag and the release's file names, `packages.py` by
the options it shares with `install.py` (ADR-0131 of canone). The swap
the machine needs before `install.py` is left to whoever prepares it.
All that is built here from `config.env` and the repo, with no effects
but asking `packages.py --list`: it can be tested without a VPS.
"""

from __future__ import annotations

import ast
import base64
import re
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from PySide6.QtCore import QCoreApplication

from app.services import envfile, fields, process, toolchain
from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.settings import get_setting, names

# The web pieces `install.py --without` leaves out, by their folder.
SURFACES = ("web", "panel", "landing")
# The prefix of each piece's host on the app's domain.
_HOST = {"web": "app.", "panel": "panel.", "landing": ""}
# The tasks of the server, `python -m app.tasks <task>`. A server
# without `sweep` keeps no files of its users, and installs without
# its timer; `TIMERS` gives the others their calendar, and
# `BROWSER_TIMERS` that of those that drive Chromium (ADR-0172 of
# canone).
TASKS = Path("src") / "app" / "tasks.py"
RELEASE = Path(".github") / "workflows" / "release.yml"
# The browser features the app uses, one per line (ADR-0136 of canone).
PERMISSIONS = Path("permissions")
_DESKTOP = re.compile(r"^\s+archivo: desktop-(linux|windows|macos)\.", re.M)
# Each app of mobile/ that the release brings as its universal APK
# (despliegue.md of canone, «Versiones»).
_MOBILE = re.compile(r'gh release upload "\$GITHUB_REF_NAME" (mobile(?:-[a-z]+)?)\.apk')
# Each piece in Java that release.yml builds with canone's
# `scripts/java.py` (java.md of canone).
_JAVA = re.compile(r"scripts/java\.py ([a-z][a-z0-9-]*) ")
_GITHUB = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")
# A tag `deploy.py` deploys (despliegue.md of canone, «Versiones»).
_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
PARTS = ("major", "minor", "patch")
# The state, in a line of its own of the README (repositorio.md of
# canone).
_STATE = re.compile(r"^Estado: (en desarrollo|en producción)$", re.M)
DEVELOPMENT = "en desarrollo"
# What `database.py` receives (despliegue.md of canone, «PostgreSQL»).
DATABASE_COMMANDS = ("empty", "migrate", "seed", "seed --mock")


def infra_dir(config: Config) -> Path:
    """Return `plantilla/infra/` of the local canone copy.

    See `CANONE_DIR`.
    """
    folder = Path(config.require("CANONE_DIR")) / "plantilla" / "infra"
    if not (folder / "install.py").is_file():
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "No hay install.py en {0}: «Carpeta de canone» tiene que ser "
                "la carpeta de canone.",
            ).format(folder)
        )
    return folder


def script(config: Config, name: str) -> Path:
    """Return a program of `scripts/` of the local canone copy.

    See `CANONE_DIR`.
    """
    program = Path(config.require("CANONE_DIR")) / "scripts" / name
    if not program.is_file():
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "No hay {0}: «Carpeta de canone» tiene que ser la carpeta de canone.",
            ).format(program)
        )
    return program


def spa_template(config: Config) -> Path:
    """`plantilla/sveltekit/` of the local copy of canone.

    See `CANONE_DIR`.
    """
    folder = Path(config.require("CANONE_DIR")) / "plantilla" / "sveltekit"
    if not (folder / "vite.config.ts").is_file():
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "No hay vite.config.ts en {0}: «Carpeta de canone» tiene que ser "
                "la carpeta de canone.",
            ).format(folder)
        )
    return folder


def origin(root: Path) -> tuple[str, str]:
    """Return the repo's GitHub owner and name, from its origin remote.

    The name is canone's `<app>`: it names the account, the database,
    the units and the VPS's folders.
    """
    url = process.capture(["git", "remote", "get-url", "origin"], cwd=root)
    found = _GITHUB.search(url.strip())
    if found is None:
        raise TaskError(
            QCoreApplication.translate("canone", "origin no es un repo de GitHub: {0}").format(url)
        )
    return found.group(1), found.group(2)


def state(root: Path) -> str:
    """Return the state the repo's README declares.

    It is the only place it is declared: «Configurar VPS» marks the
    machine for development by it, and Consola does not empty a database
    whose repo is in production. A README that does not declare it
    stops: no state is assumed.
    """
    readme = root / "README.md"
    found = _STATE.search(readme.read_text(encoding="utf-8")) if readme.is_file() else None
    if found is None:
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "{0} no declara su estado: falta una línea «Estado: en desarrollo» o "
                "«Estado: en producción».",
            ).format(readme)
        )
    return found.group(1)


def database_command(app: str, command: str) -> str:
    """Return `database.py` with a command; `install.py` installs it."""
    if command not in DATABASE_COMMANDS:
        raise TaskError(
            QCoreApplication.translate("canone", "database.py no tiene el comando {0!r}.").format(
                command
            )
        )
    return f"/usr/local/sbin/{app}-database {command}"


def calls(root: Path, config: Config) -> bool:
    """Return whether the app relays calls: `install.py --turn`.

    The repo says so in its code: an app with calls reads `turn_secret`,
    which `install.py` writes only with `--turn`, and canone makes every
    `Settings` field required (ADR-0085).
    """
    return fields.TURN in fields.settings_fields(root / config.get("SERVER_DIR"))


def package_args(root: Path, config: Config) -> list[str]:
    """Return the options of `packages.py`.

    Those of `install.py` that add a package, with the same names.
    """
    args: list[str] = []
    for extension in envfile.split_list(config.get("DB_EXTENSIONS")):
        args += ["--extension", extension]
    if calls(root, config):
        args.append("--turn")
    if _logs(config):
        args.append("--logs")
    for piece in java_pieces(root):
        args += ["--java", piece]
    server = root / config.get("SERVER_DIR")
    # A repo without the tasks of canone has no task that drives
    # Chromium; `install_args` stops on it.
    if (server / TASKS).is_file():
        for task, calendar in browsers(server):
            args += ["--browser", f"{task}={calendar}"]
    return args


def packages(root: Path, config: Config) -> list[str]:
    """Return the packages `packages.py` installs for this repo.

    It asks `packages.py --list` of the local canone copy, with the
    local Python: the list lives only in canone (despliegue.md of
    canone, «Máquina»; ADR-0131 of canone).
    """
    return _listed(config, package_args(root, config))


def installable(config: Config) -> list[str]:
    """Return every package `packages.py` can install (`--all`)."""
    return _listed(config, ["--all"])


def _listed(config: Config, options: list[str]) -> list[str]:
    """Return what `packages.py --list` prints with those options."""
    program = infra_dir(config) / "packages.py"
    if not program.is_file():
        raise TaskError(
            QCoreApplication.translate(
                "canone", "No hay packages.py en {0}: actualiza la copia de canone."
            ).format(program.parent)
        )
    argv = [*toolchain.python_cmd(), str(program), "--list", *options]
    return process.capture(argv, timeout=30).split()


def desktops(root: Path) -> list[str]:
    """Return each `desktop-<system>` of the repo's `release.yml`."""
    release = root / RELEASE
    if not release.is_file():
        return []
    return _DESKTOP.findall(release.read_text(encoding="utf-8"))


def mobiles(root: Path) -> list[str]:
    """Return each app of mobile/ whose APK `release.yml` uploads."""
    release = root / RELEASE
    if not release.is_file():
        return []
    return list(dict.fromkeys(_MOBILE.findall(release.read_text(encoding="utf-8"))))


def java_pieces(root: Path) -> list[str]:
    """Return each piece in Java that `release.yml` builds."""
    release = root / RELEASE
    if not release.is_file():
        return []
    return list(dict.fromkeys(_JAVA.findall(release.read_text(encoding="utf-8"))))


def permissions(root: Path) -> list[str]:
    """Return each line of the repo's `permissions`, for `--allow`.

    Without the file, the app allows none.
    """
    path = root / PERMISSIONS
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def valkey_memory(meminfo: str, percent: str) -> str:
    """Return that percent of `MemTotal`, as Valkey's `maxmemory` in MB.

    `meminfo` is the VPS's `/proc/meminfo`. ADR-0086.
    """
    found = re.search(r"^MemTotal:\s+(\d+) kB$", meminfo, re.M)
    if found is None:
        raise TaskError(
            QCoreApplication.translate("canone", "/proc/meminfo del VPS no trae MemTotal.")
        )
    try:
        share = float(percent)
    except ValueError:
        raise TaskError(
            QCoreApplication.translate(
                "canone", "{0} tiene que ser un número, como 12.5: {1!r}."
            ).format(names(["VALKEY_PERCENT"]), percent)
        ) from None
    if not 0 < share <= 100:
        raise TaskError(
            QCoreApplication.translate("canone", "{0} va de 0 a 100: {1}.").format(
                names(["VALKEY_PERCENT"]), percent
            )
        )
    return f"{max(1, int(int(found.group(1)) * share / 100 / 1024))}mb"


def _dictionary(path: Path, name: str) -> ast.Dict | None:
    """Return the literal dictionary `name` of the module at `path`.

    None if the module does not declare it as a literal.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            target = node.target
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        else:
            continue
        if isinstance(target, ast.Name) and target.id == name:
            return node.value if isinstance(node.value, ast.Dict) else None
    return None


def _tasks_file(server: Path) -> Path:
    path = server / TASKS
    if not path.is_file():
        raise TaskError(
            QCoreApplication.translate(
                "canone", "No hay {0}: el servidor no trae las tareas de canone."
            ).format(path)
        )
    return path


def tasks(server: Path) -> list[str]:
    """Return the keys of `TASKS` in the server's `tasks.py`.

    It is read with `ast`, like the `Settings` fields: importing it asks
    for the repo's venv and its credentials.
    """
    path = _tasks_file(server)
    found = _dictionary(path, "TASKS")
    if found is None:
        raise TaskError(
            QCoreApplication.translate("canone", "{0} no declara el diccionario TASKS.").format(
                path
            )
        )
    return [
        k.value for k in found.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
    ]


def timers(server: Path) -> list[tuple[str, str]]:
    """Return each task of `TIMERS` with its `OnCalendar=`.

    `TIMERS` names the tasks with a calendar of their own, which
    `install.py --task` gives a timer (fastapi.md of canone, «Tareas»).
    Without it there are none.
    """
    return _calendars(server, "TIMERS")


def browsers(server: Path) -> list[tuple[str, str]]:
    """Return each task of `BROWSER_TIMERS` with its `OnCalendar=`.

    `BROWSER_TIMERS` names the tasks that drive Chromium, which
    `install.py --browser` runs in the unit that lets Chromium run
    (ADR-0172 of canone). A task goes in only one of the two
    dictionaries. Without it there are none.
    """
    found = _calendars(server, "BROWSER_TIMERS")
    both = {task for task, _ in timers(server)} & {task for task, _ in found}
    if both:
        raise TaskError(
            QCoreApplication.translate(
                "canone", "{0}: {1} está en TIMERS y en BROWSER_TIMERS."
            ).format(server / TASKS, ", ".join(sorted(both)))
        )
    return found


def _calendars(server: Path, name: str) -> list[tuple[str, str]]:
    """Return each task of the dictionary `name` with its calendar."""
    path = _tasks_file(server)
    found = _dictionary(path, name)
    if found is None:
        return []
    declared = tasks(server)
    pairs = []
    for key, value in zip(found.keys, found.values, strict=True):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            raise TaskError(
                QCoreApplication.translate("canone", "{0}: cada tarea de {1} es un texto.").format(
                    path, name
                )
            )
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value):
            raise TaskError(
                QCoreApplication.translate(
                    "canone", "{0}: el calendario de {1} en {2} es un texto, como minutely."
                ).format(path, key.value, name)
            )
        if key.value not in declared:
            raise TaskError(
                QCoreApplication.translate("canone", "{0}: {1} está en {2} y no en TASKS.").format(
                    path, key.value, name
                )
            )
        pairs.append((key.value, value.value))
    return pairs


def without(root: Path, config: Config) -> list[str]:
    """Return the pieces the repo lacks.

    A web piece by its folder at the root, and `sweep` by the server's
    tasks.
    """
    missing = [piece for piece in SURFACES if not (root / piece).is_dir()]
    if "sweep" not in tasks(root / config.get("SERVER_DIR")):
        missing.append("sweep")
    return missing


def hosts(root: Path, config: Config) -> list[str]:
    """Return the host of each web piece the repo has.

    The landing is `DOMAIN`, the web `app.DOMAIN` and the panel
    `panel.DOMAIN` (despliegue.md of canone, «Caddy»), and each one
    points to the machine before `install.py` («Máquina»).
    """
    domain = config.require("DOMAIN")
    found = [f"{_HOST[piece]}{domain}" for piece in SURFACES if (root / piece).is_dir()]
    if not found:
        raise TaskError(
            QCoreApplication.translate(
                "canone", "{0} no tiene {1}: ningún host apunta al VPS."
            ).format(root, ", ".join(SURFACES))
        )
    return found


def _logs(config: Config) -> tuple[str, str, str] | None:
    """Return `--logs`, `--logs-key` and `--logs-ip`: all three or none.

    ADR-0100 of canone.
    """
    logs, key, ip = (config.get(k) for k in ("LOGS", "LOGS_KEY", "LOGS_IP"))
    if not (logs or key or ip):
        return None
    if not (logs and key and ip):
        raise TaskError(
            QCoreApplication.translate("canone", "{0} van los tres juntos o ninguno.").format(
                names(["LOGS", "LOGS_KEY", "LOGS_IP"])
            )
        )
    return logs, key, ip


def install_args(
    root: Path, config: Config, app: str, owner: str, keys: tuple[str, str], memory: str
) -> list[str]:
    """Return the arguments of `install.py`, without the program.

    `memory` is Valkey's `maxmemory`: `VALKEY_MEMORY`, or the share of
    the VPS's memory that `VALKEY_PERCENT` gives (`valkey_memory`).

    `keys` are the two public keys: `VPS_KEY_NAME`'s and the one kept
    elsewhere. They are the account's two `--key` and the releases' two
    `--signer`. On a machine that has them, `install.py` adds nothing.

    `--development` goes if the README says `Estado: en desarrollo`:
    `database.py` empties the database only on a machine with that mark,
    and `install.py` without it deletes it.
    """
    args = [
        app,
        config.require("DOMAIN"),
        memory,
        "--owner",
        owner,
        "--admin",
        config.require("VPS_USER"),
    ]
    for key in keys:
        args += ["--key", key]
    for key in keys:
        args += ["--signer", key]
    if config.flag("PRIVATE"):
        args.append("--private")
    if state(root) == DEVELOPMENT:
        args.append("--development")
    for system in desktops(root):
        args += ["--desktop", system]
    for piece in mobiles(root):
        args += ["--mobile", piece]
    for piece in without(root, config):
        args += ["--without", piece]
    for function in permissions(root):
        args += ["--allow", function]
    for piece in java_pieces(root):
        args += ["--java", piece]
    for task, calendar in timers(root / config.get("SERVER_DIR")):
        args += ["--task", f"{task}={calendar}"]
    for task, calendar in browsers(root / config.get("SERVER_DIR")):
        args += ["--browser", f"{task}={calendar}"]
    for extension in envfile.split_list(config.get("DB_EXTENSIONS")):
        args += ["--extension", extension]
    if calls(root, config):
        args.append("--turn")
        if config.get("TURN_IP"):
            args += ["--turn-ip", config.get("TURN_IP")]
    elif config.get("TURN_IP"):
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "{0} sin {1} en Settings: --turn-ip necesita --turn. Bórrala de config.env.",
            ).format(names(["TURN_IP"]), fields.TURN)
        )
    logs = _logs(config)
    if logs is not None:
        args += ["--logs", logs[0], "--logs-key", logs[1], "--logs-ip", logs[2]]
    return args


def next_tag(tags: list[str], part: str) -> str:
    """Return the tag after the highest of `tags`, bumping `part`.

    Those that are not `vX.Y.Z` do not count. With none it bumps from
    `v0.0.0`.
    """
    if part not in PARTS:
        raise TaskError(
            QCoreApplication.translate("canone", "No se sube {0!r}: es una de {1}.").format(
                part, ", ".join(PARTS)
            )
        )
    versions = [tuple(map(int, m.groups())) for m in map(_TAG.fullmatch, tags) if m]
    major, minor, patch = max(versions, default=(0, 0, 0))
    if part == "major":
        return f"v{major + 1}.0.0"
    if part == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def checksum(app: str, tag: str) -> str:
    """Return the release's `.sha256`, with each file's SHA-256."""
    return f"{app}-{tag}.sha256"


def signature(app: str, tag: str) -> str:
    """Return the signature's name, which `deploy.py` looks for."""
    return f"{checksum(app, tag)}.sig"


def signed(app: str, releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the published releases with their signature, in order.

    `releases` is the answer of `GET /repos/{owner}/{repo}/releases`.
    """
    return [
        r
        for r in releases
        if not r["draft"] and signature(app, r["tag_name"]) in {a["name"] for a in r["assets"]}
    ]


# A public key as `ssh-keygen` writes it: type and base64. The base64 of
# a key always starts with `AAAA`, the length of its type.
_KEY = re.compile(r"(\S+) (AAAA[A-Za-z0-9+/]+=*)")


def public_keys(text: str) -> set[str]:
    """Return the public keys in a text, as `type base64`.

    It reads a `.pub` and an `allowed_signers`, whose lines put the
    principal and its options before the key. The comment is left out:
    the same key can carry another one.
    """
    return {f"{kind} {body}" for kind, body in _KEY.findall(text)}


def signer(armored: str) -> str:
    """Return the public key that made an SSH signature: `type base64`.

    It is the key that `ssh-keygen -Y find-principals` looks for in
    `allowed_signers`: the signature carries it after the `SSHSIG` mark
    and its version (PROTOCOL.sshsig of OpenSSH).
    """
    body = "".join(line for line in armored.splitlines() if not line.startswith("-----"))
    blob = base64.b64decode(body)
    if blob[:6] != b"SSHSIG":
        raise TaskError(QCoreApplication.translate("canone", "No es una firma SSH."))
    key = blob[14 : 14 + int.from_bytes(blob[10:14], "big")]
    kind = key[4 : 4 + int.from_bytes(key[:4], "big")].decode("ascii")
    return f"{kind} {base64.b64encode(key).decode('ascii')}"


def events_summary(events: dict[str, Any]) -> dict[str, str]:
    """Return `GET /api/health/events` with the log's names."""
    free, total = events["diskFreeBytes"] / 10**9, events["diskTotalBytes"] / 10**9
    none = QCoreApplication.translate("canone", "ninguno")
    return {
        QCoreApplication.translate("canone", "último evento"): events["lastEventAt"] or none,
        QCoreApplication.translate("canone", "último crítico"): events["lastCriticalAt"] or none,
        QCoreApplication.translate("canone", "último respaldo"): events["lastBackupAt"] or none,
        QCoreApplication.translate("canone", "disco libre"): QCoreApplication.translate(
            "canone", "{0:.1f} GB de {1:.1f} GB"
        ).format(free, total),
    }


def deploy_command(app: str, tag: str) -> str:
    """`deploy.py`, which `install.py` installs with the app's data.

    ADR-0106 of canone.
    """
    if not _TAG.fullmatch(tag):
        raise TaskError(
            QCoreApplication.translate("canone", "{0!r} no es un tag como v1.4.0.").format(tag)
        )
    return f"/usr/local/sbin/{app}-deploy {tag}"


def signers(app: str) -> str:
    """Return the VPS's `allowed_signers`: the keys `deploy.py` accepts.

    `install.py` writes it from its `--signer`, and only adds to it.
    """
    return f"/etc/{app}/allowed_signers"


def owner_url(url: str) -> str:
    """Return the same database as the schema's owner.

    That is the `<role>_owner` role of `install.py`.
    """
    parts = urlsplit(url)
    if not parts.username:
        raise TaskError(
            QCoreApplication.translate(
                "canone", "DATABASE_URL no nombra su rol: hace falta para entrar como el dueño."
            )
        )
    owner = parts.netloc.replace(parts.username, f"{parts.username}_owner", 1)
    return urlunsplit(parts._replace(netloc=owner))


def credential_files(server: Path, config: Config, *, owner: bool = False) -> dict[str, str]:
    """Return the development `app_<field>` files from `config.env`.

    They are the same as production (ADR-0069), except `database_url`,
    which is `DATABASE_URL`: the local database. With `owner`, it enters
    as the schema's owner, which Alembic uses. It stops before writing
    if a field's value is missing.
    """
    declared_fields = fields.settings_fields(server)
    missing = [field.upper() for field in declared_fields if not config.get(field.upper())]
    if missing:
        raise TaskError(
            QCoreApplication.translate("canone", "Faltan en config.env: {0}.").format(
                names(missing)
            )
        )
    files = {f"app_{field}": config.get(field.upper()) for field in declared_fields}
    if owner:
        files["app_database_url"] = owner_url(config.require("DATABASE_URL"))
    return files


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _token() -> str:
    """Return 32 random bytes in base64url, without padding."""
    return secrets.token_urlsafe(32)


# The secrets of canone's `Settings` that are only random, and their
# format (autenticacion.md and fastapi.md of canone). `equipaggio_key`
# is not here: Equipaggio gives it.
GENERATED: dict[str, Callable[[], str]] = {
    "health_token": _token,
    "page_token_key": _fernet_key,
    "refresh_key": _token,
    "vapid_key": _token,
}


def empty_secrets(root: Path, config: Config) -> list[str]:
    """Return the `GENERATED` fields the repo declares and has empty."""
    declared = fields.settings_fields(root / config.get("SERVER_DIR"))
    return [f for f in GENERATED if f in declared and not config.get(f.upper())]


def credential_lines(root: Path, config: Config) -> str:
    """Return the `field=value` lines `credentials.py` reads.

    They come from each key's source (ADR-0063). It stops before sending
    anything if a key of `config` falls in no source, or if a field's
    value is missing. It looks at `config`, the one the task runs with,
    and not at the file again: a config built in memory is checked the
    same.
    """
    server = root / config.get("SERVER_DIR")
    declared_fields = fields.field_settings(server)
    if not declared_fields:
        raise TaskError(
            QCoreApplication.translate("canone", "No hay campos de Settings en {0}.").format(
                server / fields.CONFIG
            )
        )
    known = {s.key for s in declared_fields}
    foreign = sorted(k for k in config.values if k not in known and get_setting(k) is None)
    if foreign:
        raise TaskError(
            QCoreApplication.translate(
                "canone",
                "Estas claves de config.env no son de Consola ni campos de Settings: "
                "{0}. Bórralas antes de cargar las credenciales.",
            ).format(", ".join(foreign))
        )
    pairs = [(s.label, s.key) for s in declared_fields]
    declared = fields.settings_fields(server)
    pairs.extend((field, field.upper()) for field in fields.FROM_CONSOLA if field in declared)
    pairs.append(("restic_password", "RESTIC_PASSWORD"))
    if config.flag("PRIVATE"):
        pairs.append(("github_token", "GITHUB_TOKEN"))
    missing = [key for _, key in pairs if not config.get(key)]
    if missing:
        raise TaskError(
            QCoreApplication.translate("canone", "Faltan en config.env: {0}.").format(
                names(missing)
            )
        )
    for field, key in pairs:
        if "\n" in config.get(key):
            raise TaskError(
                QCoreApplication.translate(
                    "canone", "{0} tiene un salto de linea: credentials.py lee una por linea."
                ).format(names([key]))
            )
    return "".join(f"{field}={config.get(key)}\n" for field, key in pairs)
