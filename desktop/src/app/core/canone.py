from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core import envfile, fields, process
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.settings import get_setting

"""
Lo que Consola le pasa a los programas de canone (ADR-0059).

canone fija cada programa por su interfaz: `install.py` por sus argumentos,
`credentials.py` por las lineas que lee de stdin, `deploy.py` por el tag y los
nombres de los archivos del release, y lo que la maquina tiene que tener antes
de `install.py` (sus paquetes y el swap) lo deja a quien la prepara.
Aca se arma eso desde `config.env` y desde el repo, sin efectos: es lo que se
puede probar sin un VPS.
"""

# Lo que `install.py` da por instalado (despliegue.md de canone, «Maquina»).
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

# Las piezas que `install.py --without` puede dejar fuera, salvo `sweep`: para
# esa no hay una señal en el repo, y la plantilla trae la tarea siempre.
SURFACES = ("web", "panel", "landing")
RELEASE = Path(".github") / "workflows" / "release.yml"
_DESKTOP = re.compile(r"^  desktop-(linux|windows|macos):", re.M)
_GITHUB = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")
# Un tag que despliega `deploy.py` (despliegue.md de canone, «Versiones»).
_TAG = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
PARTS = ("major", "minor", "patch")


def infra_dir(config: Config) -> Path:
    """`plantilla/infra/` de la copia local de canone (`CANONE_DIR`)."""
    carpeta = Path(config.require("CANONE_DIR")) / "plantilla" / "infra"
    if not (carpeta / "install.py").is_file():
        raise TaskError(
            f"No hay install.py en {carpeta}: CANONE_DIR tiene que ser la carpeta de canone."
        )
    return carpeta


def spa_template(config: Config) -> Path:
    """`plantilla/sveltekit/` of the local copy of canone (`CANONE_DIR`)."""
    folder = Path(config.require("CANONE_DIR")) / "plantilla" / "sveltekit"
    if not (folder / "vite.config.ts").is_file():
        raise TaskError(
            f"No hay vite.config.ts en {folder}: CANONE_DIR tiene que ser la carpeta de canone."
        )
    return folder


def origin(root: Path) -> tuple[str, str]:
    """El dueño y el nombre del repo en GitHub, de `git remote get-url origin`.

    El nombre es el `<app>` de canone: nombra la cuenta, la base, las unidades
    y las carpetas del VPS.
    """
    url = process.capture(["git", "remote", "get-url", "origin"], cwd=root)
    encontrado = _GITHUB.search(url.strip())
    if encontrado is None:
        raise TaskError(f"origin no es un repo de GitHub: {url}")
    return encontrado.group(1), encontrado.group(2)


def packages(config: Config) -> list[str]:
    """Los paquetes que la maquina necesita para este repo."""
    paquetes = list(BASE_PACKAGES)
    if "postgis" in envfile.split_list(config.get("DB_EXTENSIONS")):
        paquetes.append(POSTGIS_PACKAGE)
    if config.flag("TURN"):
        paquetes += TURN_PACKAGES
    if _logs(config):
        paquetes += LOGS_PACKAGES
    return paquetes


def desktops(root: Path) -> list[str]:
    """Cada `desktop-<sistema>` del `release.yml` del repo, o ninguno si no lo tiene."""
    release = root / RELEASE
    if not release.is_file():
        return []
    return _DESKTOP.findall(release.read_text(encoding="utf-8"))


def without(root: Path) -> list[str]:
    """Las piezas que el repo no tiene, por su carpeta en la raiz."""
    return [pieza for pieza in SURFACES if not (root / pieza).is_dir()]


def _logs(config: Config) -> tuple[str, str, str] | None:
    """`--logs`, `--logs-key` y `--logs-ip`: los tres o ninguno (ADR-0100 de canone)."""
    logs, key, ip = (config.get(k) for k in ("LOGS", "LOGS_KEY", "LOGS_IP"))
    if not (logs or key or ip):
        return None
    if not (logs and key and ip):
        raise TaskError("LOGS, LOGS_KEY y LOGS_IP van los tres juntos o ninguno.")
    return logs, key, ip


def install_args(
    root: Path, config: Config, app: str, owner: str, keys: tuple[str, str]
) -> list[str]:
    """Los argumentos de `install.py`, sin el programa.

    `keys` son las dos llaves publicas: la de `VPS_KEY_NAME` y la guardada fuera.
    Son las dos `--key` de la cuenta y las dos `--signer` de los releases. En una
    maquina que ya las tiene, `install.py` no agrega nada.
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
    for llave in keys:
        args += ["--key", llave]
    for llave in keys:
        args += ["--signer", llave]
    if config.flag("PRIVATE"):
        args.append("--private")
    for sistema in desktops(root):
        args += ["--desktop", sistema]
    for pieza in without(root):
        args += ["--without", pieza]
    for funcion in envfile.split_list(config.get("PERMISSIONS_ALLOW")):
        args += ["--allow", funcion]
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
    """El tag que sigue al mas alto de `tags`, subiendo `part`.

    Los que no son `vX.Y.Z` no cuentan. Sin ninguno se sube desde `v0.0.0`.
    """
    if part not in PARTS:
        raise TaskError(f"No se sube {part!r}: es una de {', '.join(PARTS)}.")
    versiones = [tuple(map(int, m.groups())) for m in map(_TAG.fullmatch, tags) if m]
    major, minor, patch = max(versiones, default=(0, 0, 0))
    if part == "major":
        return f"v{major + 1}.0.0"
    if part == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def checksum(app: str, tag: str) -> str:
    """El `.sha256` del release, que lleva el SHA-256 de cada archivo."""
    return f"{app}-{tag}.sha256"


def signature(app: str, tag: str) -> str:
    """La firma del `.sha256`, el nombre que busca `deploy.py`."""
    return f"{checksum(app, tag)}.sig"


def signed(app: str, releases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Los releases publicados que traen su firma, en el orden de `releases`.

    `releases` es la respuesta de `GET /repos/{dueño}/{repo}/releases`.
    """
    return [
        r
        for r in releases
        if not r["draft"] and signature(app, r["tag_name"]) in {a["name"] for a in r["assets"]}
    ]


def events_summary(eventos: dict[str, Any]) -> dict[str, str]:
    """Lo que responde `GET /api/health/events`, con los nombres que lleva el log."""
    libre, total = eventos["diskFreeBytes"] / 10**9, eventos["diskTotalBytes"] / 10**9
    return {
        "último evento": eventos["lastEventAt"] or "ninguno",
        "último crítico": eventos["lastCriticalAt"] or "ninguno",
        "último respaldo": eventos["lastBackupAt"] or "ninguno",
        "disco libre": f"{libre:.1f} GB de {total:.1f} GB",
    }


def deploy_command(app: str, tag: str) -> str:
    """`deploy.py`, que instala `install.py` con los datos de la app (ADR-0106 de canone)."""
    if not _TAG.fullmatch(tag):
        raise TaskError(f"{tag!r} no es un tag como v1.4.0.")
    return f"python3 /usr/local/lib/{app}/deploy.py {tag}"


def owner_url(url: str) -> str:
    """La misma base como el dueño del esquema: el rol `<rol>_owner` de `install.py`."""
    partes = urlsplit(url)
    if not partes.username:
        raise TaskError("DATABASE_URL no nombra su rol: hace falta para entrar como el dueño.")
    dueno = partes.netloc.replace(partes.username, f"{partes.username}_owner", 1)
    return urlunsplit(partes._replace(netloc=dueno))


def credential_files(server: Path, config: Config, *, owner: bool = False) -> dict[str, str]:
    """Los archivos `app_<campo>` de desarrollo, con los valores de `config.env` (ADR-0069).

    Son los mismos de produccion, salvo `database_url`, que es `DATABASE_URL`: la
    base local. Con `owner`, entra como el dueño del esquema, que es lo que usa
    Alembic. Corta antes de escribir nada si falta el valor de un campo.
    """
    campos = fields.settings_fields(server)
    faltan = [campo.upper() for campo in campos if not config.get(campo.upper())]
    if faltan:
        raise TaskError(f"Faltan en config.env: {', '.join(faltan)}.")
    archivos = {f"app_{campo}": config.get(campo.upper()) for campo in campos}
    if owner:
        archivos["app_database_url"] = owner_url(config.require("DATABASE_URL"))
    return archivos


def credential_lines(root: Path, config: Config) -> str:
    """Las lineas `campo=valor` que lee `credentials.py`, por la fuente de cada clave (ADR-0063).

    Corta antes de enviar nada si una clave de `config.env` no cae en ninguna
    fuente, o si falta el valor de un campo.
    """
    servidor = root / config.get("SERVER_DIR")
    campos = fields.field_settings(servidor)
    if not campos:
        raise TaskError(f"No hay campos de Settings en {servidor / fields.CONFIG}.")
    conocidas = {s.key for s in campos}
    ajenas = sorted(
        k for k in envfile.load_config(str(root)) if k not in conocidas and get_setting(k) is None
    )
    if ajenas:
        raise TaskError(
            "Estas claves de config.env no son de Consola ni campos de Settings: "
            f"{', '.join(ajenas)}. Bórralas antes de cargar las credenciales."
        )
    pares = [(s.label, s.key) for s in campos]
    pares.append(("restic_password", "RESTIC_PASSWORD"))
    if config.flag("PRIVATE"):
        pares.append(("github_token", "GITHUB_TOKEN"))
    faltan = [clave for _, clave in pares if not config.get(clave)]
    if faltan:
        raise TaskError(f"Faltan en config.env: {', '.join(faltan)}.")
    for campo, clave in pares:
        if "\n" in config.get(clave):
            raise TaskError(f"{clave} tiene un salto de linea: credentials.py lee una por linea.")
    return "".join(f"{campo}={config.get(clave)}\n" for campo, clave in pares)
