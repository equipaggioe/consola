from __future__ import annotations

import subprocess
import sys
from pathlib import Path

"""
Muestra los logs en vivo del servidor en el VPS.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, repo_name_from_git_url, require_env, ssh_argv

# =========================================================
# FILTROS (editar aca)
# =========================================================

LOG_LINES = 0
LOG_FOLLOW = True

LOG_SINCE: str | None = "now"   # Ejemplos: "now", "1 hour ago", "2024-01-01", "yesterday". None = sin filtro.
LOG_LEVEL: str | None = None    # emerg|alert|crit|err|warning|notice|info|debug. None = sin filtro.
LOG_GREP: str | None = None     # Texto a buscar en las lineas de log. None = sin filtro.


def _build_logs_cmd(service_name: str) -> str:
    parts = ["sudo", "journalctl", "-u", service_name, "-n", str(LOG_LINES), "--no-pager"]
    if LOG_FOLLOW:
        parts.append("-f")
    if LOG_SINCE:
        parts += ["--since", f'"{LOG_SINCE}"']
    if LOG_LEVEL:
        parts += ["-p", LOG_LEVEL]
    if LOG_GREP:
        parts += ["-g", f'"{LOG_GREP}"']
    return " ".join(parts)


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")

    service_name = repo_name_from_git_url(git_repo_url)
    remote_cmd = _build_logs_cmd(service_name)

    print(f"[INFO] Servicio: {service_name}")
    if LOG_FOLLOW:
        print("[INFO] Monitoreo en vivo (Ctrl+C para salir)...")

    result = subprocess.run(
        ssh_argv(remote_cmd, identity_file=identity_file, user=vps_user, host=vps_ip),
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
