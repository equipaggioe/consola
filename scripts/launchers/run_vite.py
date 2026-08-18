from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

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


def _require_int_env(name: str) -> int:
    raw = _require_env(name)
    try:
        value = int(raw)
    except ValueError as exc:
        print(f"[ERROR] {name} no es numérico: {raw}")
        raise SystemExit(1) from exc
    if value < 1 or value > 65535:
        print(f"[ERROR] {name} fuera de rango: {value}")
        raise SystemExit(1)
    return value


def _require_bool_env(name: str) -> bool:
    raw = _require_env(name).lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    print(f"[ERROR] {name} inválido (usa true/false, 1/0, yes/no): {raw}")
    raise SystemExit(1)


def _resolve_npm() -> str:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("No se encontró npm en PATH.")


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
        return True


def _pick_port(*, preferred_port: int, search_if_busy: bool, port_name: str) -> int:
    if _is_port_free(preferred_port):
        return preferred_port

    if not search_if_busy:
        print(f"[ERROR] Puerto en uso: {port_name}={preferred_port}")
        raise SystemExit(1)

    for port in range(preferred_port + 1, 65536):
        if _is_port_free(port):
            return port

    print("[ERROR] No se encontró ningún puerto disponible.")
    raise SystemExit(1)


def main() -> None:
    project_dir_name = DEFAULT_PROJECT_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        project_dir_name = sys.argv[1].strip()

    env_prefix = ENV_PREFIX
    if len(sys.argv) >= 3 and sys.argv[2].strip():
        env_prefix = sys.argv[2].strip()
    if not env_prefix:
        env_prefix = project_dir_name.upper()

    repo_root = Path(__file__).resolve().parent.parent.parent
    project_dir = repo_root / project_dir_name
    if not (project_dir / "package.json").exists():
        print(f"[ERROR] No existe package.json en: {project_dir}")
        raise SystemExit(1)

    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    server_port = _require_int_env("SERVER_PORT")
    api_url = (os.getenv("API_URL") or "").strip()
    host = _require_env(f"{env_prefix}_HOST")
    preferred_port_name = f"{env_prefix}_PREFERRED_PORT"
    preferred_port = _require_int_env(preferred_port_name)
    search_if_busy = _require_bool_env(f"{env_prefix}_PORT_SEARCH")
    port = _pick_port(preferred_port=preferred_port, search_if_busy=search_if_busy, port_name=preferred_port_name)

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
