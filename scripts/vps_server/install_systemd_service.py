from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

"""
Instala el servicio systemd en el VPS para ejecutar el backend automáticamente.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME y GIT_REPO_URL.
4) Genera el contenido del servicio systemd con las rutas del VPS.
5) Crea el archivo de servicio en /etc/systemd/system/ del VPS.
6) Recarga systemd, habilita e inicia el servicio.
7) Muestra el estado del servicio para verificar la instalación.
"""

# =========================================================
# SERVICE SETTINGS
# =========================================================

SERVER_HOST = "0.0.0.0"
SERVER_PORT = "443"
RESTART = "on-failure"
RESTART_SEC = "3"
TIMEOUT_STOP_SEC = "30"
START_LIMIT_INTERVAL_SEC = "60"
START_LIMIT_BURST = "10"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, repo_name_from_git_url, require_env, run_ssh


@dataclass(frozen=True)
class ServiceConfig:
    vps_ip: str
    vps_user: str
    identity_file: Path
    repo_name: str
    remote_server_path: str
    remote_venv_path: str
    remote_cert_file: str
    remote_key_file: str
    systemd_service_name: str
    uvicorn_app: str


def _load_config() -> ServiceConfig:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")

    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    server_dir = require_env("SERVER_DIR")
    cert_file_path = require_env("CERT_FILE_PATH")
    key_file_path = require_env("KEY_FILE_PATH")
    uvicorn_app = require_env("UVICORN_APP")

    repo_name = repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_deploy_dir}/{repo_name}"
    remote_server_path = f"{remote_repo_path}/{server_dir}"

    return ServiceConfig(
        vps_ip=vps_ip,
        vps_user=vps_user,
        identity_file=identity_file,
        repo_name=repo_name,
        remote_server_path=remote_server_path,
        remote_venv_path=f"{remote_server_path}/.venv",
        remote_cert_file=f"{remote_repo_path}/{cert_file_path}",
        remote_key_file=f"{remote_repo_path}/{key_file_path}",
        systemd_service_name=repo_name,
        uvicorn_app=uvicorn_app,
    )


def run_remote(cfg: ServiceConfig, command: str):
    return run_ssh(command, identity_file=cfg.identity_file, user=cfg.vps_user, host=cfg.vps_ip)


def run_remote_checked(cfg: ServiceConfig, command: str):
    result = run_remote(cfg, command)
    if result.returncode != 0:
        raise RuntimeError(f"\nCOMANDO REMOTO FALLÓ\n\n{result.stderr}")
    return result


def generate_service_text(cfg: ServiceConfig) -> str:
    exec_start = (
        f"{cfg.remote_venv_path}/bin/python -m uvicorn "
        f"{cfg.uvicorn_app} "
        f"--host {SERVER_HOST} "
        f"--port {SERVER_PORT} "
        f"--ssl-keyfile {cfg.remote_key_file} "
        f"--ssl-certfile {cfg.remote_cert_file} "
        "--no-access-log"
    )

    return f"""
[Unit]
Description={cfg.repo_name} backend (uvicorn)
After=network.target
StartLimitIntervalSec={START_LIMIT_INTERVAL_SEC}
StartLimitBurst={START_LIMIT_BURST}

[Service]
Type=simple
User={cfg.vps_user}
WorkingDirectory={cfg.remote_server_path}
ExecStart={exec_start}
Restart={RESTART}
RestartSec={RESTART_SEC}
TimeoutStopSec={TIMEOUT_STOP_SEC}
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
""".strip()


def install_service(cfg: ServiceConfig) -> None:
    print("Instalando servicio...")

    service_text = generate_service_text(cfg)

    install_command = f"""
sudo tee "/etc/systemd/system/{cfg.systemd_service_name}.service" >/dev/null <<'UNIT'
{service_text}
UNIT

sudo systemctl daemon-reload

sudo systemctl enable {cfg.systemd_service_name}

sudo systemctl restart {cfg.systemd_service_name}
"""

    result = run_remote_checked(cfg, install_command)
    print(result.stdout)

    active_result = run_remote(cfg, f"sudo systemctl is-active {cfg.systemd_service_name}")
    if active_result.stdout.strip():
        print(active_result.stdout)
    if active_result.stderr.strip():
        print(active_result.stderr)

    status_result = run_remote(cfg, f"sudo systemctl status {cfg.systemd_service_name} --no-pager -l")
    if status_result.stdout.strip():
        print(status_result.stdout)
    if status_result.stderr.strip():
        print(status_result.stderr)

    if active_result.returncode != 0:
        journal_result = run_remote(cfg, f"sudo journalctl -u {cfg.systemd_service_name} -n 200 --no-pager")
        if journal_result.stdout.strip():
            print(journal_result.stdout)
        if journal_result.stderr.strip():
            print(journal_result.stderr)

        raise RuntimeError(
            f"\nSERVICIO NO ACTIVO (exit {active_result.returncode}).\n"
            "Revisa el status y logs impresos arriba."
        )


def main() -> None:
    cfg = _load_config()
    install_service(cfg)
    print("\nSERVICE INSTALADO")


if __name__ == "__main__":
    main()
