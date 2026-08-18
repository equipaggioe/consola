from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Abre una sesión SSH al VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER y VPS_KEY_NAME.
4) Si existe ~/.ssh/<VPS_KEY_NAME>, conecta con -i; si no, conecta sin llave (pedirá contraseña).
"""


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


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    vps_ip = _require_env("VPS_IP")
    vps_user = _require_env("VPS_USER")
    vps_key_name = _require_env("VPS_KEY_NAME")

    identity_file = Path.home() / ".ssh" / vps_key_name

    if identity_file.is_file():
        subprocess.run(["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}"], check=False)
        return

    subprocess.run(["ssh", f"{vps_user}@{vps_ip}"], check=False)


if __name__ == "__main__":
    main()
