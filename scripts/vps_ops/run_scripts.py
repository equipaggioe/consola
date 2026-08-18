from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

"""
Ejecuta scripts de setup dentro del VPS (Opción A: correr en el servidor vía SSH).

Flujo:
- Lee credenciales y ruta remota desde scripts/.env (local).
- Resuelve el path del repo en el VPS usando GIT_REPO_URL y VPS_REMOTE_DIR.
- Ejecuta, en el orden indicado, los scripts listados en SETUP_SCRIPTS dentro del repo remoto.

Variables de configuración (edita estas constantes):
- SETUP_SCRIPTS: lista ordenada de comandos tipo línea de comandos (ruta + args), relativos al root del repo.
- REMOTE_PYTHON: comando de Python en el VPS (ej. "python3" o "server/.venv/bin/python").

Variables requeridas en scripts/.env (local):
- VPS_IP, VPS_USER, VPS_KEY_NAME, VPS_REMOTE_DIR, GIT_REPO_URL

Advertencia:
- Varios scripts en server/scripts/setup validan un venv con ruta tipo Windows (".venv/Scripts/python.exe").
  Si tu VPS es Linux, esos scripts van a fallar hasta que los adaptes.
"""

SETUP_SCRIPTS: list[str] = [
    #"server/scripts/setup/bootstrap_db.py depechemode",
    "server/scripts/setup/rebuild_db.py",
    #"server/scripts/inspect_db.py",
    #"scripts/utils/update_cloudflare.py"
]

REMOTE_PYTHON = "server/.venv/bin/python"


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


def _find_project_root() -> Path:
    start = Path(__file__).resolve().parent
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    print("[ERROR] No se encontró .git.")
    raise SystemExit(1)


def _require_setup_scripts() -> list[str]:
    scripts = [s.strip() for s in SETUP_SCRIPTS if (s or "").strip()]
    if not scripts:
        print("[ERROR] SETUP_SCRIPTS está vacío.")
        raise SystemExit(1)
    return scripts


def _run_ssh_command(*, identity_file: Path, target: str, remote_cmd: str) -> None:
    result = subprocess.run(
        ["ssh", "-i", str(identity_file), target, remote_cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout.strip():
        print(result.stdout.rstrip("\n"))
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló SSH (exit {result.returncode}).")


def main() -> None:
    repo_root = _find_project_root()
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    vps_ip = _require_env("VPS_IP")
    vps_user = _require_env("VPS_USER")
    vps_key_name = _require_env("VPS_KEY_NAME")
    vps_remote_dir = _require_env("VPS_REMOTE_DIR")
    git_repo_url = _require_env("GIT_REPO_URL")

    scripts = _require_setup_scripts()

    identity_file = Path.home() / ".ssh" / vps_key_name
    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave privada local: {identity_file}")
        raise SystemExit(1)

    repo_name = _repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_remote_dir.rstrip('/')}/{repo_name}"
    target = f"{vps_user}@{vps_ip}"

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
            f" && {shlex.quote(REMOTE_PYTHON)} {shlex.quote(script_rel)}{args_str}"
        )
        print(f"[INFO] Ejecutando en VPS: {script_cmdline}")
        _run_ssh_command(identity_file=identity_file, target=target, remote_cmd=remote_cmd)

    print("[OK] Setup remoto completado.")


if __name__ == "__main__":
    main()
