from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

"""
Arranca el backend (Uvicorn) usando el venv de server/.

Flujo:
1) Asegura que se ejecute con server/.venv.
2) Carga variables desde la raíz/.env a os.environ.
3) Lee SERVER_PREFERRED_PORT, SERVER_PORT_SEARCH, SERVER_HOST y SERVER_RELOAD desde os.environ.
4) Intenta usar SERVER_PREFERRED_PORT. Si está ocupado:
   - SERVER_PORT_SEARCH=false: termina con error.
   - SERVER_PORT_SEARCH=true: busca el siguiente puerto libre.
5) Escribe SERVER_PORT en la raíz/.env con el puerto elegido.
6) Arranca uvicorn con app.main:app, HOST y RELOAD.
7) Si existen certs/cert.pem y certs/key.pem en server/, habilita TLS.
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


def _upsert_env_var(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{key}="
    out: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
        return True


def _pick_port(*, preferred_port: int, search_if_busy: bool) -> int:
    if _is_port_free(preferred_port):
        return preferred_port

    if not search_if_busy:
        print(f"[ERROR] Puerto en uso: PREFERRED_PORT={preferred_port}")
        raise SystemExit(1)

    for port in range(preferred_port + 1, 65536):
        if _is_port_free(port):
            return port

    print("[ERROR] No se encontró ningún puerto disponible.")
    raise SystemExit(1)


def _ensure_server_venv_python(repo_root: Path) -> None:
    venv_python = repo_root / "server" / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print(f"[ERROR] No existe el Python del venv: {venv_python}")
        raise SystemExit(1)

    current_python = Path(sys.executable).resolve()
    target_python = venv_python.resolve()
    if os.path.normcase(str(current_python)) != os.path.normcase(str(target_python)):
        print(f"[INFO] Reiniciando con el Python del venv: {target_python}")
        os.execv(str(target_python), [str(target_python), *sys.argv])


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    server_dir = repo_root / "server"
    env_path = repo_root / "scripts" / ".env"

    _ensure_server_venv_python(repo_root)
    _load_env_file(env_path)

    if not server_dir.exists():
        print(f"[ERROR] No existe el directorio del servidor: {server_dir}")
        raise SystemExit(1)

    os.chdir(server_dir)
    sys.path.insert(0, str(server_dir))

    preferred_port = _require_int_env("SERVER_PREFERRED_PORT")
    search_if_busy = _require_bool_env("SERVER_PORT_SEARCH")
    port = _pick_port(preferred_port=preferred_port, search_if_busy=search_if_busy)
    _upsert_env_var(env_path, "SERVER_PORT", str(port))

    app_module = "app.main:app"
    host = _require_env("SERVER_HOST")
    reload_enabled = _require_bool_env("SERVER_RELOAD")

    cert_file = server_dir / "certs" / "cert.pem"
    key_file = server_dir / "certs" / "key.pem"
    ssl_enabled = cert_file.exists() and key_file.exists()

    print("[INFO] Iniciando servidor backend...")
    print(f"[INFO] App: {app_module}")
    print(f"[INFO] Host: {host}")
    print(f"[INFO] Puerto: {port}")
    print(f"[INFO] Archivo de entorno: {env_path}")
    print(f"[INFO] Reload: {reload_enabled}")
    if ssl_enabled:
        print(f"[INFO] TLS: habilitado ({cert_file}, {key_file})")
    else:
        print("[INFO] TLS: deshabilitado (faltan certs/cert.pem o certs/key.pem)")

    try:
        import uvicorn

        kwargs: dict[str, object] = {"host": host, "port": port, "reload": reload_enabled}
        if ssl_enabled:
            kwargs["ssl_certfile"] = str(cert_file)
            kwargs["ssl_keyfile"] = str(key_file)
        uvicorn.run(app_module, **kwargs)
    except OSError as exc:
        print(f"[ERROR] No se pudo iniciar el servidor: {exc}")
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"[ERROR] Falló el arranque del servidor: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
