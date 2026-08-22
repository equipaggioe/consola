from __future__ import annotations

import sys
from pathlib import Path

"""
Ejecuta un comando dentro del repo en el VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME, VPS_DEPLOY_DIR, GIT_REPO_URL y VPS_RUN_COMMAND.
4) Valida que exista la llave privada local en ~/.ssh/<VPS_KEY_NAME>.
5) Calcula el path remoto del repo (VPS_DEPLOY_DIR + nombre del repo).
6) Conecta por SSH y ejecuta el comando dentro del repo remoto.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, repo_name_from_git_url, require_env, run_ssh


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    git_repo_url = require_env("GIT_REPO_URL")
    vps_run_command = require_env("VPS_RUN_COMMAND")

    repo_name = repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_deploy_dir.rstrip('/')}/{repo_name}"

    remote_cmd = (
        f'if [ ! -d "{remote_repo_path}" ]; then '
        f'echo "No existe el repo en el VPS: {remote_repo_path}" 1>&2; exit 2; '
        "fi; "
        f'cd "{remote_repo_path}" && {vps_run_command}'
    )

    print("[INFO] Ejecutando comando en el VPS...")
    print(f"[INFO] Directorio: {remote_repo_path}")
    print(f"[INFO] Comando: {vps_run_command}")

    result = run_ssh(remote_cmd, identity_file=identity_file, user=vps_user, host=vps_ip)

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
