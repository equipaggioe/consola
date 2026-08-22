from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

"""
Actualiza el código del backend en el VPS y configura el entorno.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER, VPS_KEY_NAME y GIT_REPO_URL.
4) Verifica que existan los archivos locales necesarios.
5) Clona o actualiza el repositorio en el VPS (controlado por PULL_REPOSITORY).
6) Si se actualizó el repo: crea/verifica venv Python e instala dependencias.
7) Si UPLOAD_FILES=True: copia .env y archivos de server/ (cert.pem, key.pem, firebase-service-account.json).
8) Si se actualizó el repo y GENERATE_MIGRATION=True: corre scripts/database/migrate_db.py
   LOCALMENTE (no por SSH; se conecta al VPS por túnel). Este script fuerza RUN_REMOTE=true
   en el entorno del proceso antes de lanzarlo (common.force_env_vars(), no toca scripts/.env)
   para garantizar que la migración se aplique siempre al VPS, sin importar el valor de
   RUN_REMOTE guardado en el .env local. Se saltea, avisando en vez de fallar, si todavía no
   existe ninguna migración inicial en el repo local (falta scripts/database/rebuild_db.py).
9) Reinicia el servicio, salvo que todavía no exista (VPS nuevo): en ese caso avisa y no
   hace nada, en vez de fallar.

Manejo de errores:
- Si hay cambios sin commitear en el VPS: pregunta descartar o guardar con stash antes de pull.
"""

# =========================================================
# SCRIPT SETTINGS
# =========================================================

PULL_REPOSITORY = True  # True para actualizar el repo en el VPS (pull). False para saltearlo.
GENERATE_MIGRATION = True  # True: genera y aplica una migración de Alembic en el VPS. False: no hace nada de esto.
UPLOAD_FILES = True  # True para copiar .env y archivos remotos al VPS. False para saltear.

FILES_TO_UPLOAD = [
    "cert.pem",
    "key.pem",
    "firebase-service-account.json",
]


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    copy_to_vps,
    find_project_root,
    force_env_vars,
    load_vps_config,
    multiplex_ssh_args,
    repo_name_from_git_url,
    require_env,
    restart_systemd_service,
)

# =========================================================
# CONFIG (asignado en main() al arrancar; ver _load_config())
# =========================================================

VPS_IP = ""
VPS_USER = ""
GIT_REPO_URL = ""
PROJECT_ROOT = Path()
LOCAL_IDENTITY_FILE = Path()
VPS_DEPLOY_DIR = ""
SERVER_DIR = ""
REPO_NAME = ""
REMOTE_REPO_PATH = ""
REMOTE_SERVER_PATH = ""
REMOTE_VENV_PATH = ""
REMOTE_REQUIREMENTS_PATH = ""

# =========================================================
# HELPERS
# =========================================================


def run_remote(command: str, quiet: bool = False, timeout: float | None = None):

    mux = multiplex_ssh_args(identity_file=LOCAL_IDENTITY_FILE, user=VPS_USER, host=VPS_IP)

    return _run_streaming(
        [
            "ssh",
            *mux,
            "-i",
            str(LOCAL_IDENTITY_FILE),
            f"{VPS_USER}@{VPS_IP}",
            command,
        ],
        quiet=quiet,
        timeout=timeout,
    )


def run_remote_checked(command: str, quiet: bool = False, timeout: float | None = None):

    result = run_remote(command, quiet=quiet, timeout=timeout)

    if result.returncode != 0:

        raise RuntimeError(
            f"\nCOMANDO REMOTO FALLÓ\n\n"
            f"{result.stdout}"
        )

    return result


def _run_streaming(
    cmd: list[str],
    timeout: float | None = None,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:

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

    def _read_output():
        for line in proc.stdout:
            if not quiet:
                print(line, end="", flush=True)
            out_lines.append(line)

    reader = threading.Thread(target=_read_output, daemon=True)
    reader.start()

    try:
        return_code = proc.wait(timeout=timeout)

    except subprocess.TimeoutExpired:

        proc.kill()
        proc.wait()
        raise TimeoutError(
            f"Comando sin respuesta tras {timeout}s: {' '.join(cmd)}"
        )

    reader.join()
    return subprocess.CompletedProcess(cmd, return_code, "".join(out_lines), None)


def upload_preserving_structure(
    local_path: Path,
    *,
    ensure_remote_dir: bool = True,
    chmod_after: str | None = "600",
):

    relative_path = local_path.relative_to(
        PROJECT_ROOT
    )

    return copy_to_vps(
        local_path,
        remote_rel_path=relative_path.as_posix(),
        remote_dir_base=VPS_DEPLOY_DIR,
        git_repo_url=GIT_REPO_URL,
        vps_ip=VPS_IP,
        vps_user=VPS_USER,
        identity_file=LOCAL_IDENTITY_FILE,
        chmod_after=chmod_after,
        ensure_remote_dir=ensure_remote_dir,
    )

# =========================================================
# DISCOVERY
# =========================================================

def find_env_files():

    return list(
        PROJECT_ROOT.rglob(".env")
    )



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
sudo -n mkdir -p "{VPS_DEPLOY_DIR}" &&
sudo -n mkdir -p "{REMOTE_REPO_PATH}" &&
sudo -n chown -R "{VPS_USER}:{VPS_USER}" "{REMOTE_REPO_PATH}" &&
git clone "{GIT_REPO_URL}" "{REMOTE_REPO_PATH}"
'''
    )


def get_remote_status() -> list[str]:

    result = run_remote_checked(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git status --porcelain --untracked-files=all
''',
        quiet=True,
    )

    return [
        line
        for line in result.stdout.splitlines()
        if line.strip()
    ]


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


def stash_pull_repository():

    print(
        "Guardando cambios locales (git stash)..."
    )

    run_remote_checked(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git stash push -u -m "auto-stash pre-deploy"
'''
    )

    pull_repository()

    print(
        "Restaurando cambios locales guardados..."
    )

    result = run_remote(
        f'''
cd "{REMOTE_REPO_PATH}" &&
git stash pop
'''
    )

    if result.returncode != 0:

        raise RuntimeError(
            "\nEl pull se aplicó, pero no se pudo restaurar el stash automáticamente "
            "(probablemente hay conflictos con los archivos actualizados).\n"
            "Tus cambios locales siguen guardados en el stash del VPS.\n"
            "Conéctate por SSH y resuelve manualmente con 'git stash list' / 'git stash pop'.\n\n"
            f"{result.stdout}"
        )


def deploy_repository() -> bool:

    if not repository_exists():

        clone_repository()

        return True

    if not PULL_REPOSITORY:

        print(
            "\nPULL_REPOSITORY=False: continuando sin actualizar el repositorio (sin pull)."
        )
        return False

    changes = get_remote_status()

    if changes:

        print(
            "\nHay cambios locales sin commitear en el VPS:"
        )

        for line in changes:
            print(f"  {line}")

        while True:

            answer = input(
                "\n¿Qué hacer con estos cambios?\n"
                "[d] Descartar cambios locales y continuar\n"
                "[G] Guardar cambios (stash), actualizar y restaurarlos (default)\n"
                "Elige [d/G]: "
            ).strip().lower()

            if answer in ("d", "g", ""):
                if answer == "":
                    answer = "g"
                break

            print("Respuesta inválida, ingresa 'd' o 'G'.")

        if answer == "d":

            hard_reset_repository()
            pull_repository()

        else:

            stash_pull_repository()

        return True

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


def has_initial_migration() -> bool:

    versions_dir = PROJECT_ROOT / SERVER_DIR / "alembic" / "versions"

    return (
        versions_dir.is_dir()
        and any(versions_dir.glob("*.py"))
    )


def run_migrations():

    if not GENERATE_MIGRATION:
        return

    if not has_initial_migration():

        print(
            "[WARN] Todavía no hay ninguna migración inicial en alembic/versions/ "
            "(falta correr scripts/database/rebuild_db.py); no se generan migraciones."
        )
        return

    print(
        "Generando y aplicando migración (scripts/database/migrate_db.py, local con túnel SSH)..."
    )

    force_env_vars({"RUN_REMOTE": "true"})

    migrate_script = PROJECT_ROOT / "scripts" / "database" / "migrate_db.py"
    result = subprocess.run([sys.executable, str(migrate_script)])

    if result.returncode != 0:
        raise RuntimeError(
            f"\nFalló scripts/database/migrate_db.py (exit {result.returncode})."
        )

# =========================================================
# FILES
# =========================================================

def _remote_paths_for(files: list[Path]) -> list[tuple[Path, str, str]]:

    entries = []

    for file in files:
        remote_rel_posix = file.relative_to(PROJECT_ROOT).as_posix()
        remote_full_path = f"{REMOTE_REPO_PATH}/{remote_rel_posix}"
        remote_parent = f"{REMOTE_REPO_PATH}/{Path(remote_rel_posix).parent.as_posix()}"
        entries.append((file, remote_full_path, remote_parent))

    return entries


def upload_files_batched(files: list[Path], *, label: str):
    """Sube varios archivos abriendo una sola conexión ssh para crear todos los
    directorios remotos y otra para aplicar chmod a todos, en vez de dos conexiones
    ssh extra por archivo (además del scp). Reduce ráfagas de conexiones que pueden
    disparar rate-limiting/fail2ban en el VPS."""

    if not files:
        return

    print(f"Copiando {len(files)} {label}...")

    entries = _remote_paths_for(files)

    remote_parents = sorted({parent for _, _, parent in entries})
    mkdir_cmd = " && ".join(f'mkdir -p "{parent}"' for parent in remote_parents)
    run_remote_checked(mkdir_cmd, quiet=True)

    for i, (file, _remote_full_path, _parent) in enumerate(entries, start=1):

        rel = file.relative_to(PROJECT_ROOT).as_posix()
        print(f"[{i}/{len(entries)}] Subiendo {rel}...", flush=True)
        upload_preserving_structure(file, ensure_remote_dir=False, chmod_after=None)

    chmod_cmd = " && ".join(f'chmod 600 "{remote_full_path}"' for _, remote_full_path, _ in entries)
    run_remote_checked(chmod_cmd, quiet=True)


def upload_env_files():

    upload_files_batched(find_env_files(), label=".env")


def upload_remote_files():

    server_dir = (
        PROJECT_ROOT
        / SERVER_DIR
    )

    files_to_upload = []

    for file_pattern in FILES_TO_UPLOAD:

        matches = list(
            server_dir.rglob(file_pattern)
        )

        if not matches:

            print(
                f"No se encontró: {file_pattern}"
            )

        files_to_upload.extend(matches)

    upload_files_batched(files_to_upload, label="archivos remotos")

# =========================================================
# SERVICE
# =========================================================

def restart_service():

    restart_systemd_service(REPO_NAME, lambda cmd: run_remote(cmd, quiet=True))

# =========================================================
# MAIN
# =========================================================

def _load_config() -> None:
    global VPS_IP, VPS_USER, GIT_REPO_URL, PROJECT_ROOT, LOCAL_IDENTITY_FILE
    global REPO_NAME, REMOTE_REPO_PATH, REMOTE_SERVER_PATH, REMOTE_VENV_PATH, REMOTE_REQUIREMENTS_PATH
    global VPS_DEPLOY_DIR, SERVER_DIR

    PROJECT_ROOT = find_project_root(Path(__file__).resolve().parent)
    VPS_IP, VPS_USER, LOCAL_IDENTITY_FILE = load_vps_config(PROJECT_ROOT)
    GIT_REPO_URL = require_env("GIT_REPO_URL")

    VPS_DEPLOY_DIR = require_env("VPS_DEPLOY_DIR")
    SERVER_DIR = require_env("SERVER_DIR")

    REPO_NAME = repo_name_from_git_url(GIT_REPO_URL)
    REMOTE_REPO_PATH = f"{VPS_DEPLOY_DIR}/{REPO_NAME}"
    REMOTE_SERVER_PATH = f"{REMOTE_REPO_PATH}/{SERVER_DIR}"
    REMOTE_VENV_PATH = f"{REMOTE_SERVER_PATH}/.venv"
    REMOTE_REQUIREMENTS_PATH = f"{REMOTE_SERVER_PATH}/requirements.txt"


def main():
    _load_config()

    validate_local_files()

    repo_actualizado = deploy_repository()

    if repo_actualizado:

        ensure_venv()

        install_requirements()
    else:

        print(
            "Saltando venv/dependencias porque no se actualizó el repositorio."
        )

    if UPLOAD_FILES:

        upload_env_files()

        upload_remote_files()
    else:

        print(
            "Saltando subida de archivos (UPLOAD_FILES=False)."
        )

    if repo_actualizado:

        run_migrations()

    restart_service()

    print(
        "\nDEPLOY COMPLETADO"
    )


if __name__ == "__main__":

    main()
