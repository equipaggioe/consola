from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Actualiza Debian e instala paquetes base en el VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER y VPS_KEY_NAME.
4) Valida que exista la llave local ~/.ssh/<VPS_KEY_NAME> (si no existe, termina con error).
5) Conecta al VPS por SSH como VPS_USER usando -i ~/.ssh/<VPS_KEY_NAME>.
6) Ejecuta: sudo apt-get update -> sudo apt-get upgrade -> sudo apt-get install <paquetes seleccionados>.
7) Imprime comandos de verificación según lo seleccionado.
"""


PACKAGES: dict[str, dict[str, object]] = {
    "python": {
        "enabled": True,
        "apt": ["python3", "python3-venv", "python3-pip"],
        "verify": ["python3 --version", "pip3 --version"],
    },
    "git": {
        "enabled": True,
        "apt": ["git"],
        "verify": ["git --version"],
    },
    "postgresql": {
        "enabled": True,
        "apt": ["postgresql", "postgresql-contrib"],
        "verify": ["psql --version"],
    },
    "postgis": {
        "enabled": False,
        "apt": ["postgis", "postgresql-postgis-scripts"],
        "verify": ["dpkg -s postgis | grep -i '^version'"],
    },
    "nginx": {
        "enabled": False,
        "apt": ["nginx"],
        "verify": ["nginx -v"],
    },

    "redis": {
        "enabled": False,
        "apt": ["redis-server"],
        "verify": ["redis-cli --version"],
    },
    "curl": {
        "enabled": False,
        "apt": ["curl"],
        "verify": ["curl --version"],
    },
    "htop": {
        "enabled": False,
        "apt": ["htop"],
        "verify": ["htop --version"],
    },
}


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        print(f"[ERROR] No existe el archivo .env: {env_path}")
        raise SystemExit(1)

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        k = key.strip()
        v = value.strip()
        if not k:
            continue
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        print(f"[ERROR] Falta variable de entorno: {name}")
        raise SystemExit(1)
    return value.strip()

def _sh_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _selected_packages() -> tuple[list[str], list[str]]:
    apt: list[str] = []
    verify: list[str] = []
    for cfg in PACKAGES.values():
        if not bool(cfg.get("enabled")):
            continue
        apt.extend([str(x) for x in (cfg.get("apt") or [])])
        verify.extend([str(x) for x in (cfg.get("verify") or [])])
    if not apt:
        print("[ERROR] No seleccionaste ningún paquete (habilita enabled=True en PACKAGES).")
        raise SystemExit(1)
    return apt, verify


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    ip = _require_env("VPS_IP")
    usuario = _require_env("VPS_USER")
    key_name = _require_env("VPS_KEY_NAME")
    identity_file = Path.home() / ".ssh" / key_name
    apt_packages, verify_cmds = _selected_packages()

    print("[INFO] Actualizando sistema e instalando paquetes seleccionados...")

    remote_cmd = (
        "set -e; "
        "export DEBIAN_FRONTEND=noninteractive; "
        "sudo -n /usr/bin/apt-get update; "
        "sudo -n /usr/bin/apt-get -y upgrade; "
        f"sudo -n /usr/bin/apt-get -y install {' '.join(apt_packages)}; "
        + "; ".join(verify_cmds)
    )

    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave local configurada en VPS_KEY_NAME: {identity_file}")
        raise SystemExit(1)

    subprocess.run(["ssh", "-i", str(identity_file), f"{usuario}@{ip}", remote_cmd], check=True)
    print("[OK] Listo.")


if __name__ == "__main__":
    main()
