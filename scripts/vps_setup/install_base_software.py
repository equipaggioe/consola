from __future__ import annotations

import subprocess
import sys
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config

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
    "caddy": {
        "enabled": True,
        "apt": ["caddy"],
        "verify": ["caddy version"],
    },
    "ufw": {
        "enabled": True,
        "apt": ["ufw"],
        "verify": ["sudo -n ufw version"],
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
    repo_root = find_project_root(Path(__file__).resolve().parent)
    ip, usuario, identity_file = load_vps_config(repo_root)
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

    subprocess.run(["ssh", "-i", str(identity_file), f"{usuario}@{ip}", remote_cmd], check=True)
    print("[OK] Listo.")


if __name__ == "__main__":
    main()
