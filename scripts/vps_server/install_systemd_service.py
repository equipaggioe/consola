import os
import subprocess
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

VPS_REMOTE_DIR = "/srv"
SERVER_DIR = "server"
UVICORN_APP = "app.main:app"

SERVER_HOST = "0.0.0.0"
SERVER_PORT = "443"
CERT_FILE_PATH = "certs/cert.pem"
KEY_FILE_PATH = "certs/key.pem"

RESTART = "on-failure"
RESTART_SEC = "3"
TIMEOUT_STOP_SEC = "30"
START_LIMIT_INTERVAL_SEC = "60"
START_LIMIT_BURST = "10"

# =========================================================
# ENV LOADER
# =========================================================

def _find_env_file() -> Path:

    start = Path(__file__).resolve().parent

    for path in [start, *start.parents]:

        candidate = path / ".env"

        if candidate.is_file():
            return candidate

    raise RuntimeError(
        "No se encontró .env."
    )


def _load_env(path: Path) -> None:

    for raw in path.read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip()

        if key and key not in os.environ:
            os.environ[key] = value


_load_env(_find_env_file())

# =========================================================
# HELPERS
# =========================================================

def _require(name: str) -> str:

    value = os.getenv(name)

    if not value:

        raise RuntimeError(
            f"Falta variable requerida: {name}"
        )

    return value


def run_remote(command: str):

    return subprocess.run(
        [
            "ssh",
            "-i",
            str(LOCAL_IDENTITY_FILE),
            f"{VPS_USER}@{VPS_IP}",
            command
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_remote_checked(command: str):

    result = run_remote(command)

    if result.returncode != 0:

        raise RuntimeError(
            f"\nCOMANDO REMOTO FALLÓ\n\n"
            f"{result.stderr}"
        )

    return result

# =========================================================
# CONFIG (.env)
# =========================================================

VPS_IP = _require("VPS_IP")

VPS_USER = _require("VPS_USER")

VPS_KEY_NAME = _require("VPS_KEY_NAME")

GIT_REPO_URL = _require("GIT_REPO_URL")

# =========================================================
# DERIVED
# =========================================================

LOCAL_IDENTITY_FILE = (
    Path.home()
    / ".ssh"
    / VPS_KEY_NAME
)

REPO_NAME = (
    GIT_REPO_URL
    .split("/")[-1]
    .replace(".git", "")
)

REMOTE_REPO_PATH = (
    f"{VPS_REMOTE_DIR}/{REPO_NAME}"
)

REMOTE_SERVER_PATH = (
    f"{REMOTE_REPO_PATH}/{SERVER_DIR}"
)

REMOTE_VENV_PATH = (
    f"{REMOTE_SERVER_PATH}/.venv"
)

REMOTE_CERT_FILE = (
    f"{REMOTE_SERVER_PATH}/{CERT_FILE_PATH}"
)

REMOTE_KEY_FILE = (
    f"{REMOTE_SERVER_PATH}/{KEY_FILE_PATH}"
)

SYSTEMD_SERVICE_NAME = REPO_NAME

# =========================================================
# SYSTEMD
# =========================================================

def generate_service_text() -> str:

    exec_start = (
        f"{REMOTE_VENV_PATH}/bin/python -m uvicorn "
        f"{UVICORN_APP} "
        f"--host {SERVER_HOST} "
        f"--port {SERVER_PORT} "
        f"--ssl-keyfile {REMOTE_KEY_FILE} "
        f"--ssl-certfile {REMOTE_CERT_FILE} "
        "--no-access-log"
    )

    return f"""
[Unit]
Description={REPO_NAME} backend (uvicorn)
After=network.target
StartLimitIntervalSec={START_LIMIT_INTERVAL_SEC}
StartLimitBurst={START_LIMIT_BURST}

[Service]
Type=simple
User={VPS_USER}
WorkingDirectory={REMOTE_SERVER_PATH}
ExecStart={exec_start}
Restart={RESTART}
RestartSec={RESTART_SEC}
TimeoutStopSec={TIMEOUT_STOP_SEC}
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
""".strip()


def install_service():

    print(
        "Instalando servicio..."
    )

    service_text = (
        generate_service_text()
    )

    install_command = f"""
sudo tee "/etc/systemd/system/{SYSTEMD_SERVICE_NAME}.service" >/dev/null <<'UNIT'
{service_text}
UNIT

sudo systemctl daemon-reload

sudo systemctl enable {SYSTEMD_SERVICE_NAME}

sudo systemctl restart {SYSTEMD_SERVICE_NAME}
"""

    result = run_remote_checked(
        install_command
    )

    print(result.stdout)

    active_result = run_remote(
        f"sudo systemctl is-active {SYSTEMD_SERVICE_NAME}"
    )
    if active_result.stdout.strip():
        print(active_result.stdout)
    if active_result.stderr.strip():
        print(active_result.stderr)

    status_result = run_remote(
        f"sudo systemctl status {SYSTEMD_SERVICE_NAME} --no-pager -l"
    )
    if status_result.stdout.strip():
        print(status_result.stdout)
    if status_result.stderr.strip():
        print(status_result.stderr)

    if active_result.returncode != 0:
        journal_result = run_remote(
            f"sudo journalctl -u {SYSTEMD_SERVICE_NAME} -n 200 --no-pager"
        )
        if journal_result.stdout.strip():
            print(journal_result.stdout)
        if journal_result.stderr.strip():
            print(journal_result.stderr)

        raise RuntimeError(
            f"\nSERVICIO NO ACTIVO (exit {active_result.returncode}).\n"
            "Revisa el status y logs impresos arriba."
        )


# =========================================================
# MAIN
# =========================================================

def main():

    install_service()

    print(
        "\\nSERVICE INSTALADO"
    )


if __name__ == "__main__":

    main()
