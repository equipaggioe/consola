from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_env_file, optional_env, pick_port, require_bool_env, require_env, require_port_env

"""
Arranca un frontend Vite (npm run dev) configurando el backend.

Uso: run_vite.py [project_dir] [env_prefix]
  project_dir: carpeta del proyecto relativa a la raíz del repo (default: DEFAULT_PROJECT_DIR).
  env_prefix:  prefijo de las variables de entorno HOST/PREFERRED_PORT/PORT_SEARCH
               (default: ENV_PREFIX; si está vacío, se toma project_dir en mayúsculas).

Flujo:
1) Valida <project_dir>/package.json.
2) Carga variables desde scripts/.env a os.environ.
3) Lee {PREFIX}_HOST, {PREFIX}_PREFERRED_PORT, {PREFIX}_PORT_SEARCH, SERVER_PORT y API_URL (opcional).
4) Exporta VITE_SERVER_PORT y VITE_SERVER_URL para el proceso hijo. Si falta API_URL, usa http://localhost:{SERVER_PORT}.
5) Si {PREFIX}_PREFERRED_PORT está ocupado:
   - {PREFIX}_PORT_SEARCH=false: termina con error.
   - {PREFIX}_PORT_SEARCH=true: busca el siguiente puerto libre.
6) Ejecuta npm run dev.
"""

DEFAULT_PROJECT_DIR = "panel"
ENV_PREFIX = ""


def _resolve_npm() -> str:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("No se encontró npm en PATH.")


def main() -> None:
    project_dir_name = DEFAULT_PROJECT_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        project_dir_name = sys.argv[1].strip()

    env_prefix = ENV_PREFIX
    if len(sys.argv) >= 3 and sys.argv[2].strip():
        env_prefix = sys.argv[2].strip()
    if not env_prefix:
        env_prefix = project_dir_name.upper()

    repo_root = find_project_root(Path(__file__).resolve().parent)
    project_dir = repo_root / project_dir_name
    if not (project_dir / "package.json").exists():
        print(f"[ERROR] No existe package.json en: {project_dir}")
        raise SystemExit(1)

    env_path = repo_root / "scripts" / ".env"
    load_env_file(env_path)

    server_port = require_port_env("SERVER_PORT")
    api_url = optional_env("API_URL")
    host = require_env(f"{env_prefix}_HOST")
    preferred_port_name = f"{env_prefix}_PREFERRED_PORT"
    preferred_port = require_port_env(preferred_port_name)
    search_if_busy = require_bool_env(f"{env_prefix}_PORT_SEARCH")
    port = pick_port(preferred_port=preferred_port, search_if_busy=search_if_busy, port_name=preferred_port_name)

    child_env = os.environ.copy()
    child_env["VITE_SERVER_PORT"] = str(server_port)
    child_env["VITE_SERVER_URL"] = api_url.rstrip("/") if api_url else f"http://localhost:{server_port}"

    npm = _resolve_npm()
    cmd = [npm, "run", "dev", "--", "--host", host, "--port", str(port)]

    print(f"[INFO] Iniciando frontend '{project_dir_name}'...")
    print(f"[INFO] Directorio: {project_dir}")
    print(f"[INFO] Host: {host}")
    print(f"[Frontend INFO] Puerto {project_dir_name}: {port}")
    print(f"[INFO] Backend para {project_dir_name}: {child_env['VITE_SERVER_URL']}")
    print(f"[INFO] Comando: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, cwd=str(project_dir), check=True, env=child_env)
    except KeyboardInterrupt:
        print(f"\n[INFO] {project_dir_name} detenido por el usuario.")
        raise SystemExit(0)
    except FileNotFoundError as exc:
        print("[ERROR] No se pudo ejecutar npm. Verifica instalación y PATH.")
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Falló la ejecución de npm: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
