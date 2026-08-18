from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

"""
Arranca el frontend de backoffice (npm run dev) configurando el backend.

Flujo:
1) Valida backoffice/package.json.
2) Carga variables desde la raíz/.env a os.environ.
3) Lee BACKOFFICE_HOST, BACKOFFICE_PREFERRED_PORT, BACKOFFICE_PORT_SEARCH, SERVER_PORT y API_URL (opcional) desde os.environ.
4) Exporta VITE_SERVER_PORT y VITE_SERVER_URL para el proceso hijo. Si falta API_URL, usa http://localhost:{SERVER_PORT}.
5) Si BACKOFFICE_PREFERRED_PORT está ocupado:
   - BACKOFFICE_PORT_SEARCH=false: termina con error.
   - BACKOFFICE_PORT_SEARCH=true: busca el siguiente puerto libre.
6) Ejecuta npm run dev.
"""


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
    repo_root = Path(__file__).resolve().parent.parent
    backoffice_dir = repo_root / "backoffice"
    if not (backoffice_dir / "package.json").exists():
        print(f"[ERROR] No existe package.json en: {backoffice_dir}")
        raise SystemExit(1)

    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    server_port = _require_int_env("SERVER_PORT")
    api_url = (os.getenv("API_URL") or "").strip()
    host = _require_env("BACKOFFICE_HOST")
    preferred_port = _require_int_env("BACKOFFICE_PREFERRED_PORT")
    search_if_busy = _require_bool_env("BACKOFFICE_PORT_SEARCH")
    port = _pick_port(preferred_port=preferred_port, search_if_busy=search_if_busy, port_name="BACKOFFICE_PREFERRED_PORT")

    child_env = os.environ.copy()
    child_env["VITE_SERVER_PORT"] = str(server_port)
    child_env["VITE_SERVER_URL"] = api_url.rstrip("/") if api_url else f"http://localhost:{server_port}"

    npm = _resolve_npm()
    cmd = [npm, "run", "dev", "--", "--host", host, "--port", str(port)]

    print("[INFO] Iniciando backoffice frontend...")
    print(f"[INFO] Directorio: {backoffice_dir}")
    print(f"[INFO] Host: {host}")
    print(f"[Frontend INFO] Puerto backoffice: {port}")
    print(f"[INFO] Backend para backoffice: {child_env['VITE_SERVER_URL']}")
    print(f"[INFO] Comando: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, cwd=str(backoffice_dir), check=True, env=child_env)
    except KeyboardInterrupt:
        print("\n[INFO] Backoffice detenido por el usuario.")
        raise SystemExit(0)
    except FileNotFoundError as exc:
        print("[ERROR] No se pudo ejecutar npm. Verifica instalación y PATH.")
        raise SystemExit(1) from exc
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Falló la ejecución de npm: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
