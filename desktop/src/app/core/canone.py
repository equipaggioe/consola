"""What Consola passes to canone's programs (ADR-0059).

canone fixes each program by its interface: `install.py` by its
arguments, `credentials.py` by the lines it reads from stdin,
`deploy.py` by the tag and the release's file names. What the machine
has to have before `install.py`, its packages and swap, is left to
whoever prepares it. All that is built here from `config.env` and the
repo, with no effects: it can be tested without a VPS.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core import envfile, fields, process
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.settings import get_setting

# What `install.py` assumes installed (despliegue.md of canone,
# «Maquina»).
BASE_PACKAGES = (
    "caddy",
    "postgresql",
    "valkey-server",
    "restic",
    "sudo",
    "python3",
    "nftables",
    "unattended-upgrades",
    "systemd-timesyncd",
    "ca-certificates",
)
POSTGIS_PACKAGE = "postgresql-17-postgis-3"
TURN_PACKAGES = ("coturn",)
LOGS_PACKAGES = ("systemd-journal-remote", "wireguard-tools")

# The pieces `install.py --without` can leave out, except `sweep`: the
# repo has no signal for it, and the template always brings the task.
SURFACES = ("web", "panel", "landing")
RELEASE = Path(".github") / "workflows" / "release.yml"
_DESKTOP = re.compile(r"^  desktop-(linux|windows|macos):", re.M)
_GITHUB = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")
# A tag `deploy.py` deploys (despliegue.md of canone, «Versiones»).
_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
PARTS = ("major", "minor", "patch")


def infra_dir(config: Config) -> Path:
    """Return `plantilla/infra/` of the local canone copy.

    See `CANONE_DIR`.
    """
    folder = Path(config.require("CANONE_DIR")) / "plantilla" / "infra"
    if not (folder / "install.py").is_file():
        raise TaskError(
            f"No hay install.py en {folder}: CANONE_DIR tiene que ser la carpeta de canone."
        )
    return folder


def spa_template(config: Config) -> Path:
    """`plantilla/sveltekit/` of the local copy of canone.

    See `CANONE_DIR`.
    """
    folder = Path(config.require("CANONE_DIR")) / "plantilla" / "sveltekit"
    if not (folder / "vite.config.ts").is_file():
        raise TaskError(
            f"No hay vite.config.ts en {folder}: CANONE_DIR tiene que ser la carpeta de canone."
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
        raise TaskError(f"origin no es un repo de GitHub: {url}")
    return found.group(1), found.group(2)


def packages(config: Config) -> list[str]:
    """Return the packages the machine needs for this repo."""
    names = list(BASE_PACKAGES)
    if "postgis" in envfile.split_list(config.get("DB_EXTENSIONS")):
        names.append(POSTGIS_PACKAGE)
    if config.flag("TURN"):
        names += TURN_PACKAGES
    if _logs(config):
        names += LOGS_PACKAGES
    return names


def desktops(root: Path) -> list[str]:
    """Return each `desktop-<system>` of the repo's `release.yml`.

    If any.
    """
    release = root / RELEASE
    if not release.is_file():
        return []
    return _DESKTOP.findall(release.read_text(encoding="utf-8"))


def without(root: Path) -> list[str]:
    """Return the pieces the repo lacks, by their folder at the root."""
    return [piece for piece in SURFACES if not (root / piece).is_dir()]


def _logs(config: Config) -> tuple[str, str, str] | None:
    """Return `--logs`, `--logs-key` and `--logs-ip`: all three or none.

    ADR-0100 of canone.
    """
    logs, key, ip = (config.get(k) for k in ("LOGS", "LOGS_KEY", "LOGS_IP"))
    if not (logs or key or ip):
        return None
    if not (logs and key and ip):
        raise TaskError("LOGS, LOGS_KEY y LOGS_IP van los tres juntos o ninguno.")
    return logs, key, ip


def install_args(
    root: Path, config: Config, app: str, owner: str, keys: tuple[str, str]
) -> list[str]:
    """Return the arguments of `install.py`, without the program.

    `keys` are the two public keys: `VPS_KEY_NAME`'s and the one kept
    elsewhere. They are the account's two `--key` and the releases' two
    `--signer`. On a machine that has them, `install.py` adds nothing.
    """
    args = [
        app,
        config.require("DOMAIN"),
        config.require("VALKEY_MEMORY"),
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
    for system in desktops(root):
        args += ["--desktop", system]
    for piece in without(root):
        args += ["--without", piece]
    for function in envfile.split_list(config.get("PERMISSIONS_ALLOW")):
        args += ["--allow", function]
    for extension in envfile.split_list(config.get("DB_EXTENSIONS")):
        args += ["--extension", extension]
    if config.flag("TURN"):
        args.append("--turn")
        if config.get("TURN_IP"):
            args += ["--turn-ip", config.get("TURN_IP")]
    elif config.get("TURN_IP"):
        raise TaskError("TURN_IP sin TURN: --turn-ip necesita --turn.")
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
        raise TaskError(f"No se sube {part!r}: es una de {', '.join(PARTS)}.")
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


def events_summary(events: dict[str, Any]) -> dict[str, str]:
    """Return `GET /api/health/events` with the log's names."""
    free, total = events["diskFreeBytes"] / 10**9, events["diskTotalBytes"] / 10**9
    return {
        "último evento": events["lastEventAt"] or "ninguno",
        "último crítico": events["lastCriticalAt"] or "ninguno",
        "último respaldo": events["lastBackupAt"] or "ninguno",
        "disco libre": f"{free:.1f} GB de {total:.1f} GB",
    }


def deploy_command(app: str, tag: str) -> str:
    """`deploy.py`, which `install.py` installs with the app's data.

    ADR-0106 of canone.
    """
    if not _TAG.fullmatch(tag):
        raise TaskError(f"{tag!r} no es un tag como v1.4.0.")
    return f"python3 /usr/local/lib/{app}/deploy.py {tag}"


def owner_url(url: str) -> str:
    """Return the same database as the schema's owner.

    That is the `<role>_owner` role of `install.py`.
    """
    parts = urlsplit(url)
    if not parts.username:
        raise TaskError("DATABASE_URL no nombra su rol: hace falta para entrar como el dueño.")
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
        raise TaskError(f"Faltan en config.env: {', '.join(missing)}.")
    files = {f"app_{field}": config.get(field.upper()) for field in declared_fields}
    if owner:
        files["app_database_url"] = owner_url(config.require("DATABASE_URL"))
    return files


def credential_lines(root: Path, config: Config) -> str:
    """Return the `field=value` lines `credentials.py` reads.

    They come from each key's source (ADR-0063). It stops before sending
    anything if a `config.env` key falls in no source, or if a field's
    value is missing.
    """
    server = root / config.get("SERVER_DIR")
    declared_fields = fields.field_settings(server)
    if not declared_fields:
        raise TaskError(f"No hay campos de Settings en {server / fields.CONFIG}.")
    known = {s.key for s in declared_fields}
    foreign = sorted(
        k for k in envfile.load_config(str(root)) if k not in known and get_setting(k) is None
    )
    if foreign:
        raise TaskError(
            "Estas claves de config.env no son de Consola ni campos de Settings: "
            f"{', '.join(foreign)}. Bórralas antes de cargar las credenciales."
        )
    pairs = [(s.label, s.key) for s in declared_fields]
    pairs.append(("restic_password", "RESTIC_PASSWORD"))
    if config.flag("PRIVATE"):
        pairs.append(("github_token", "GITHUB_TOKEN"))
    missing = [key for _, key in pairs if not config.get(key)]
    if missing:
        raise TaskError(f"Faltan en config.env: {', '.join(missing)}.")
    for field, key in pairs:
        if "\n" in config.get(key):
            raise TaskError(f"{key} tiene un salto de linea: credentials.py lee una por linea.")
    return "".join(f"{field}={config.get(key)}\n" for field, key in pairs)
