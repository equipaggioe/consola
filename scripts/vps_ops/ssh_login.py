from __future__ import annotations

import subprocess
import sys
from pathlib import Path

"""
Abre una sesión SSH al VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env, VPS_IP y VPS_USER (default: nombre del repo si no está definida).
3) Lee y valida VPS_KEY_NAME.
4) Si existe ~/.ssh/<VPS_KEY_NAME>, conecta con -i; si no, conecta sin llave (pedirá contraseña).
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_ip_user, require_env


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user = load_vps_ip_user(repo_root)
    vps_key_name = require_env("VPS_KEY_NAME")

    identity_file = Path.home() / ".ssh" / vps_key_name

    if identity_file.is_file():
        subprocess.run(["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}"], check=False)
        return

    subprocess.run(["ssh", f"{vps_user}@{vps_ip}"], check=False)


if __name__ == "__main__":
    main()
