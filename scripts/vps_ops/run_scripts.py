from __future__ import annotations

import shlex
import sys
from pathlib import Path

"""
Ejecuta scripts de setup dentro del VPS (Opción A: correr en el servidor vía SSH).

Flujo:
- Lee credenciales y ruta remota desde scripts/.env (local).
- Resuelve el path del repo en el VPS usando GIT_REPO_URL y VPS_DEPLOY_DIR.
- Ejecuta, en el orden indicado, los scripts listados en SETUP_SCRIPTS dentro del repo remoto.

Variables de configuración (edita esta constante):
- SETUP_SCRIPTS: lista ordenada de comandos tipo línea de comandos (ruta + args), relativos al root del repo.

Variables requeridas en scripts/.env (local):
- VPS_IP, VPS_USER, VPS_KEY_NAME, VPS_DEPLOY_DIR, GIT_REPO_URL, VPS_PYTHON

Advertencia:
- Varios scripts en server/scripts/setup validan un venv con ruta tipo Windows (".venv/Scripts/python.exe").
  Si tu VPS es Linux, esos scripts van a fallar hasta que los adaptes.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, repo_name_from_git_url, require_env, run_ssh

SETUP_SCRIPTS: list[str] = [
    #"server/scripts/setup/bootstrap_db.py depechemode",
    "server/scripts/setup/rebuild_db.py",
    #"server/scripts/setup/migrate_db.py",   
    #"server/scripts/inspect_db.py",
    #"scripts/utils/update_cloudflare.py"
]


def _require_setup_scripts() -> list[str]:
    scripts = [s.strip() for s in SETUP_SCRIPTS if (s or "").strip()]
    if not scripts:
        print("[ERROR] SETUP_SCRIPTS está vacío.")
        raise SystemExit(1)
    return scripts


def _run_ssh_command(*, identity_file: Path, user: str, host: str, remote_cmd: str) -> None:
    result = run_ssh(remote_cmd, identity_file=identity_file, user=user, host=host)
    if result.stdout.strip():
        print(result.stdout.rstrip("\n"))
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló SSH (exit {result.returncode}).")


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    git_repo_url = require_env("GIT_REPO_URL")
    vps_python = require_env("VPS_PYTHON")

    scripts = _require_setup_scripts()

    repo_name = repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_deploy_dir.rstrip('/')}/{repo_name}"

    for script_cmdline in scripts:
        parts = shlex.split(script_cmdline, posix=True)
        if not parts:
            print(f"[ERROR] Comando vacío en SETUP_SCRIPTS: {script_cmdline!r}")
            raise SystemExit(1)

        script_rel = parts[0].replace("\\", "/")
        script_args = parts[1:]

        args_str = ""
        if script_args:
            args_str = " " + " ".join(shlex.quote(a) for a in script_args)

        remote_cmd = (
            f'cd {shlex.quote(remote_repo_path)}'
            f" && {shlex.quote(vps_python)} {shlex.quote(script_rel)}{args_str}"
        )
        print(f"[INFO] Ejecutando en VPS: {script_cmdline}")
        _run_ssh_command(identity_file=identity_file, user=vps_user, host=vps_ip, remote_cmd=remote_cmd)

    print("[OK] Setup remoto completado.")


if __name__ == "__main__":
    main()
