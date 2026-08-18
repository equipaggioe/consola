from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Ejecuta un comando dentro del repo en el VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME, VPS_REMOTE_DIR, GIT_REPO_URL y VPS_RUN_COMMAND.
4) Valida que exista la llave privada local en ~/.ssh/<VPS_KEY_NAME>.
5) Calcula el path remoto del repo (VPS_REMOTE_DIR + nombre del repo).
6) Conecta por SSH y ejecuta el comando dentro del repo remoto.
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


def _repo_name_from_git_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail.removesuffix(".git")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    vps_ip = _require_env("VPS_IP")
    vps_user = _require_env("VPS_USER")
    vps_key_name = _require_env("VPS_KEY_NAME")
    vps_remote_dir = _require_env("VPS_REMOTE_DIR")
    git_repo_url = _require_env("GIT_REPO_URL")
    vps_run_command = _require_env("VPS_RUN_COMMAND")

    identity_file = Path.home() / ".ssh" / vps_key_name
    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave privada local: {identity_file}")
        raise SystemExit(1)

    repo_name = _repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_remote_dir.rstrip('/')}/{repo_name}"

    remote_cmd = (
        f'if [ ! -d "{remote_repo_path}" ]; then '
        f'echo "No existe el repo en el VPS: {remote_repo_path}" 1>&2; exit 2; '
        "fi; "
        f'cd "{remote_repo_path}" && {vps_run_command}'
    )

    print("[INFO] Ejecutando comando en el VPS...")
    print(f"[INFO] Directorio: {remote_repo_path}")
    print(f"[INFO] Comando: {vps_run_command}")

    result = subprocess.run(
        ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", remote_cmd],
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print(f"[ERROR] Falló el comando en el VPS (exit {result.returncode}).")
        raise SystemExit(1)

    print("[OK] LISTO")


if __name__ == "__main__":
    main()
