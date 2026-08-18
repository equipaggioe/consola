from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

"""
Administra el servidor remoto (systemd) en el VPS.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME y GIT_REPO_URL.
4) Valida que exista la llave privada local en ~/.ssh/<VPS_KEY_NAME>.
5) Deriva el nombre del servicio systemd desde GIT_REPO_URL (REPO_NAME).
6) Conecta por SSH y ejecuta: sudo systemctl <action> <REPO_NAME>.

Acciones disponibles:
  start     - Inicia el servicio
  stop      - Detiene el servicio
  restart   - Reinicia el servicio (acción por defecto)
  status    - Muestra el estado del servicio
  enable    - Habilita el servicio para arranque automático
  disable   - Deshabilita el servicio para arranque automático
  reload    - Recarga la configuración del servicio (si lo soporta)
  is-active - Verifica si el servicio está activo
  is-enabled - Verifica si el servicio está habilitado
  logs      - Muestra los logs del servicio (journalctl -u <servicio>)
"""


DEFAULT_SYSTEMD_ACTION = "restart"


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
    git_repo_url = _require_env("GIT_REPO_URL")

    identity_file = Path.home() / ".ssh" / vps_key_name
    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave privada local: {identity_file}")
        raise SystemExit(1)

    repo_name = _repo_name_from_git_url(git_repo_url)
    service_name = repo_name

    action = DEFAULT_SYSTEMD_ACTION
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        action = sys.argv[1].strip().lower()

    if action not in {
        "start",
        "stop",
        "restart",
        "status",
        "enable",
        "disable",
        "reload",
        "is-active",
        "is-enabled",
        "logs",
    }:
        print(
            "[ERROR] Acción inválida. Usa: start | stop | restart | status | enable | disable | reload | "
            "is-active | is-enabled | logs"
        )
        raise SystemExit(2)

    if action == "logs":
        remote_cmd = f"sudo journalctl -u {service_name} -n 200 -f --no-pager"
    else:
        status_args = " --no-pager -l" if action == "status" else ""
        remote_cmd = f"sudo systemctl {action} {service_name}{status_args}"

    print("[INFO] Administrando systemd en el VPS...")
    print(f"[INFO] Servicio: {service_name}")
    print(f"[INFO] Acción: {action}")

    if action == "logs":
        print("[INFO] Monitoreo en vivo (Ctrl+C para salir)...")
        result = subprocess.run(
            ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", remote_cmd],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    else:
        result = subprocess.run(
            ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", remote_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

    if result.returncode != 0:
        print(f"[ERROR] Falló el comando en el VPS (exit {result.returncode}).")
        raise SystemExit(1)

    if action != "logs":
        print("[OK] LISTO")


if __name__ == "__main__":
    main()
