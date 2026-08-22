from __future__ import annotations

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
  start      - Inicia el servicio
  stop       - Detiene el servicio
  restart    - Reinicia el servicio (acción por defecto)
  status     - Muestra el estado del servicio
  enable     - Habilita el servicio para arranque automático
  disable    - Deshabilita el servicio para arranque automático
  reload     - Recarga la configuración del servicio (si lo soporta)
  is-active  - Verifica si el servicio está activo
  is-enabled - Verifica si el servicio está habilitado

Para ver los logs en vivo, usa view_logs.py.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, repo_name_from_git_url, require_env, run_ssh

DEFAULT_SYSTEMD_ACTION = "restart"  # Acción por defecto si no se pasa ninguna


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")

    repo_name = repo_name_from_git_url(git_repo_url)
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
    }:
        print(
            "[ERROR] Acción inválida. Usa: start | stop | restart | status | enable | disable | reload | "
            "is-active | is-enabled"
        )
        raise SystemExit(2)

    status_args = " --no-pager -l" if action == "status" else ""
    remote_cmd = f"sudo systemctl {action} {service_name}{status_args}"

    print("[INFO] Administrando systemd en el VPS...")
    print(f"[INFO] Servicio: {service_name}")
    print(f"[INFO] Acción: {action}")

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
