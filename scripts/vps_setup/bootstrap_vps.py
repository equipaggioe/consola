from __future__ import annotations

import subprocess
import sys
from pathlib import Path

"""
Bootstraps un VPS desde cero: aprovisionamiento del sistema + deploy inicial del backend.

Flujo:
- Cada script de BOOTSTRAP_SCRIPTS se ejecuta localmente (no en el VPS) con el mismo
  intérprete de Python que corre este archivo, uno por uno y en el orden indicado.
- Si un script falla (exit code distinto de 0), se detiene la ejecución.

Orden pensado para un VPS nuevo:
1) refresh_known_host / setup_ssh_key / install_base_software / setup_github_ssh:
   aprovisionamiento del sistema (usuario, llaves SSH, paquetes, acceso a GitHub).
2) update_remote: clona el repo, crea el venv, instala dependencias y sube .env/certs.
   En un VPS nuevo el servicio systemd todavía no existe, así que el reinicio final de
   update_remote.py se saltea solo (con aviso) en vez de fallar.
3) bootstrap_db: crea el rol y la base de datos en Postgres (se auto-despacha al VPS
   vía RUN_REMOTE, ver scripts/common.py).
4) rebuild_db: crea el esquema inicial (Alembic) y corre los seeders (conecta al VPS por
   túnel SSH, también vía RUN_REMOTE, ver scripts/common.py).
5) install_systemd_service: crea y arranca el servicio systemd.

bootstrap_db.py y rebuild_db.py normalmente se usan para desarrollo local (RUN_REMOTE en
false en scripts/.env), así que este script fuerza esa variable a "true" en el entorno del
propio proceso antes de correr nada (no toca el archivo .env). Como los scripts hijos
heredan ese entorno, apuntan al VPS y no a Postgres local. Si scripts/.env tiene guardado
un valor distinto, common.load_env_file() va a preguntar por consola cuál usar; el default
(Enter) ahora mantiene el valor del entorno (el forzado acá).

Variable de configuración (edita esta constante):
- BOOTSTRAP_SCRIPTS: lista ordenada de scripts a correr, relativos al root del repo.
  Agrega o quita líneas según cambien las necesidades de bootstrapping del VPS.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, force_env_vars

ENV_OVERRIDES: dict[str, str] = {
    "RUN_REMOTE": "true",
}

BOOTSTRAP_SCRIPTS: list[str] = [
    "scripts/vps_setup/refresh_known_host.py",
    "scripts/vps_setup/setup_ssh_key.py",
    "scripts/vps_setup/install_base_software.py",
    "scripts/vps_setup/setup_github_ssh.py",
    "scripts/vps_server/update_remote.py",
    "scripts/database/bootstrap_db.py",
    "scripts/database/rebuild_db.py",
    "scripts/vps_server/install_systemd_service.py",
]


def _require_bootstrap_scripts() -> list[str]:
    scripts = [s.strip() for s in BOOTSTRAP_SCRIPTS if (s or "").strip()]
    if not scripts:
        print("[ERROR] BOOTSTRAP_SCRIPTS está vacío.")
        raise SystemExit(1)
    return scripts


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    scripts = _require_bootstrap_scripts()

    force_env_vars(ENV_OVERRIDES)

    for script_rel in scripts:
        script_path = repo_root / script_rel
        if not script_path.is_file():
            print(f"[ERROR] No existe el script: {script_rel}")
            raise SystemExit(1)

        print(f"[INFO] Ejecutando: {script_rel}")
        result = subprocess.run([sys.executable, str(script_path)])
        if result.returncode != 0:
            print(f"[ERROR] Falló {script_rel} (exit {result.returncode}). Se detiene el bootstrap.")
            raise SystemExit(result.returncode)

    print("[OK] Bootstrap del VPS completado.")


if __name__ == "__main__":
    main()
