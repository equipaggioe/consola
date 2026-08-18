import os
import subprocess
from pathlib import Path

"""
Actualiza el código del backend en el VPS y configura el entorno.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME y GIT_REPO_URL.
4) Verifica que existan los archivos locales necesarios.
5) Clona o actualiza el repositorio en el VPS (opcionalmente puede saltar el pull con SKIP_GIT_PULL).
6) Crea/verifica el entorno virtual Python en el VPS.
7) Instala las dependencias desde requirements.txt.
8) Copia archivos .env y certificados SSL al VPS.
9) Copia server/firebase-service-account.json al VPS.
"""

# =========================================================
# SCRIPT SETTINGS
# =========================================================

SKIP_GIT_PULL = True

VPS_REMOTE_DIR = "/srv"
SERVER_DIR = "server"
CERT_FILE_NAME = "cert.pem"
KEY_FILE_NAME = "key.pem"


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


def find_project_root() -> Path:

    start = Path(__file__).resolve().parent

    for path in [start, *start.parents]:

        if (path / ".git").exists():

            return path

    raise RuntimeError(
        "No se encontró .git."
    )


def run_remote(command: str):

    return _run_streaming(
        [
            "ssh",
            "-i",
            str(LOCAL_IDENTITY_FILE),
            f"{VPS_USER}@{VPS_IP}",
            command,
        ]
    )


def run_remote_checked(command: str):

    result = run_remote(command)

    if result.returncode != 0:

        raise RuntimeError(
            f"\nCOMANDO REMOTO FALLÓ\n\n"
            f"{result.stdout}"
        )

    return result


def _run_streaming(cmd: list[str]) -> subprocess.CompletedProcess[str]:

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    out_lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="", flush=True)
        out_lines.append(line)

    return_code = proc.wait()
    return subprocess.CompletedProcess(cmd, return_code, "".join(out_lines), None)


def upload_file(
    local_path: Path,
    remote_path: str
):

    result = _run_streaming(
        [
            "scp",
            "-i",
            str(LOCAL_IDENTITY_FILE),
            str(local_path),
            f"{VPS_USER}@{VPS_IP}:{remote_path}",
        ]
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"\nSCP FALLÓ\n\n"
            f"{result.stdout}"
        )


def upload_preserving_structure(
    local_path: Path
):

    relative_path = local_path.relative_to(
        PROJECT_ROOT
    )

    remote_path = (
        f"{REMOTE_REPO_PATH}/"
        f"{relative_path.as_posix()}"
    )

    remote_dir = (
        Path(remote_path)
        .parent
        .as_posix()
    )

    run_remote_checked(
        f'mkdir -p "{remote_dir}"'
    )

    upload_file(
        local_path,
        remote_path
    )

# =========================================================
# CONFIG
# =========================================================

VPS_IP = _require(
    "VPS_IP"
)

VPS_USER = _require(
    "VPS_USER"
)

VPS_KEY_NAME = _require(
    "VPS_KEY_NAME"
)

GIT_REPO_URL = _require(
    "GIT_REPO_URL"
)

# =========================================================
# DERIVED
# =========================================================

PROJECT_ROOT = (
    find_project_root()
)

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

REMOTE_REQUIREMENTS_PATH = (
    f"{REMOTE_SERVER_PATH}/requirements.txt"
)

# =========================================================
# DISCOVERY
# =========================================================

def find_env_files():

    return list(
        PROJECT_ROOT.rglob(".env")
    )


def find_certificate_files():

    files = []

    files.extend(
        PROJECT_ROOT.rglob(
            CERT_FILE_NAME
        )
    )

    files.extend(
        PROJECT_ROOT.rglob(
            KEY_FILE_NAME
        )
    )

    return files

# =========================================================
# VALIDATION
# =========================================================

def validate_local_files():

    server_dir = (
        PROJECT_ROOT
        / SERVER_DIR
    )

    if not server_dir.is_dir():

        raise RuntimeError(
            f"No existe: {server_dir}"
        )

    requirements = (
        server_dir
        / "requirements.txt"
    )

    if not requirements.is_file():

        raise RuntimeError(
            f"No existe: {requirements}"
        )

    firebase_service_account = (
        server_dir
        / "firebase-service-account.json"
    )

    if not firebase_service_account.is_file():

        raise RuntimeError(
            f"No existe: {firebase_service_account}"
        )

# =========================================================
# GIT
# =========================================================

def repository_exists() -> bool:

    result = run_remote(
        f'[ -d "{REMOTE_REPO_PATH}/.git" ] && echo YES'
    )

    return (
        "YES"
        in result.stdout
    )


def clone_repository():

    print(
        "Clonando repositorio..."
    )

    run_remote_checked(
        f'''
sudo -n mkdir -p "{VPS_REMOTE_DIR}" &&
sudo -n mkdir -p "{REMOTE_REPO_PATH}" &&
sudo -n chown -R "{VPS_USER}:{VPS_USER}" "{REMOTE_REPO_PATH}" &&
git clone "{GIT_REPO_URL}" "{REMOTE_REPO_PATH}"
'''
    )


def has_remote_changes() -> bool:

    result = run_remote_checked(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git status --porcelain
'''
    )

    return bool(
        result.stdout.strip()
    )


def hard_reset_repository():

    print(
        "Descartando cambios locales..."
    )

    run_remote_checked(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git fetch --all &&
git reset --hard HEAD &&
git clean -fd
'''
    )


def pull_repository():

    print(
        "Actualizando repositorio..."
    )

    run_remote_checked(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git pull
'''
    )


def deploy_repository() -> bool:

    if not repository_exists():

        clone_repository()

        return True

    if SKIP_GIT_PULL:

        print(
            "\nSKIP_GIT_PULL=True: continuando sin actualizar el repositorio (sin pull)."
        )
        return False

    if has_remote_changes():

        answer = input(
            "\nHay cambios locales en el VPS.\n"
            "¿Descartarlos y continuar?\n"
            "[y/N]: "
        ).strip().lower()

        if answer == "y":

            hard_reset_repository()

        else:

            print(
                "\nContinuando sin actualizar el repositorio (sin pull) para conservar cambios locales."
            )
            return False

    pull_repository()
    return True

# =========================================================
# PYTHON
# =========================================================

def ensure_venv():

    print(
        "Verificando .venv..."
    )

    run_remote_checked(
        f'''
if [ ! -d "{REMOTE_VENV_PATH}" ]; then
    python3 -m venv "{REMOTE_VENV_PATH}"
fi
'''
    )


def install_requirements():

    print(
        "Instalando dependencias..."
    )

    run_remote_checked(
        f'''
"{REMOTE_VENV_PATH}/bin/pip" install \
-r "{REMOTE_REQUIREMENTS_PATH}"
'''
    )

# =========================================================
# FILES
# =========================================================

def upload_env_files():

    env_files = (
        find_env_files()
    )

    print(
        f"Copiando {len(env_files)} .env..."
    )

    for i, file in enumerate(env_files, start=1):

        rel = file.relative_to(PROJECT_ROOT).as_posix()
        print(f"[{i}/{len(env_files)}] Subiendo {rel}...", flush=True)
        upload_preserving_structure(
            file
        )


def upload_certificates():

    cert_files = (
        find_certificate_files()
    )

    print(
        f"Copiando {len(cert_files)} certificados..."
    )

    for i, file in enumerate(cert_files, start=1):

        rel = file.relative_to(PROJECT_ROOT).as_posix()
        print(f"[{i}/{len(cert_files)}] Subiendo {rel}...", flush=True)
        upload_preserving_structure(
            file
        )

def upload_firebase_service_account():

    file = (
        PROJECT_ROOT
        / SERVER_DIR
        / "firebase-service-account.json"
    )

    print(
        "Copiando firebase-service-account.json..."
    )

    upload_preserving_structure(
        file
    )

    run_remote_checked(
        f'chmod 600 "{REMOTE_SERVER_PATH}/firebase-service-account.json"'
    )

# =========================================================
# SERVICE
# =========================================================

def restart_service():

    print(
        "Reiniciando servicio..."
    )

    run_remote_checked(
        f"sudo systemctl restart {REPO_NAME}"
    )

# =========================================================
# MAIN
# =========================================================

def main():

    validate_local_files()

    repo_actualizado = deploy_repository()

    if repo_actualizado:

        ensure_venv()

        install_requirements()
    else:

        print(
            "Saltando venv/dependencias porque no se actualizó el repositorio."
        )

    upload_env_files()

    upload_certificates()

    upload_firebase_service_account()

    restart_service()

    print(
        "\nDEPLOY COMPLETADO"
    )


if __name__ == "__main__":

    main()
