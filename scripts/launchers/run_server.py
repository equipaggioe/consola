from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

"""
Arranca el backend (Uvicorn) usando el venv de server/.

Flujo:
1) Asegura que se ejecute con server/.venv.
2) Carga variables desde la raíz/.env a os.environ.
3) Resuelve DATABASE_URL según RUN_REMOTE (scripts/.env) y la exporta a os.environ
   (pisa lo que tenga server/.env, solo para este proceso).
4) Lee SERVER_PREFERRED_PORT, SERVER_PORT_SEARCH, SERVER_HOST y SERVER_RELOAD desde os.environ.
5) Intenta usar SERVER_PREFERRED_PORT. Si está ocupado:
   - SERVER_PORT_SEARCH=false: termina con error.
   - SERVER_PORT_SEARCH=true: busca el siguiente puerto libre.
6) Escribe SERVER_PORT en la raíz/.env con el puerto elegido.
7) Arranca uvicorn con app.main:app, HOST y RELOAD.
8) Si existen certs/cert.pem y certs/key.pem en server/, habilita TLS.

Base de datos (RUN_REMOTE, scripts/.env):
- false: usa la BD local. El puerto se lee de postgresql.conf (no se asume un valor fijo).
  Usuario/password/nombre de BD salen de scripts/.env (VPS_USER, DB_PASSWORD, DB_NAME),
  mismos valores que usa scripts/database/bootstrap_db.py al crear la BD local.
- true: usa la BD remota del VPS. Antes de arrancar, consulta por SSH el puerto real de
  Postgres en el VPS (SHOW port, no se asume el puerto por defecto) y abre un túnel SSH en
  background hacia un puerto local libre.
- Si RUN_REMOTE=false pero no hay Postgres local instalado, cae automáticamente a la BD
  remota del VPS (con aviso). No hay fallback en la otra dirección: si RUN_REMOTE=true y
  el VPS no está disponible, el script termina con error.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    find_project_root,
    load_env_file,
    pick_port,
    require_bool_env,
    require_env,
    require_port_env,
    resolve_database_url,
    upsert_env_var,
    venv_python,
)


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    server_dir = repo_root / "server"
    env_path = repo_root / "scripts" / ".env"

    venv_python(server_dir / ".venv", restart=True)
    load_env_file(env_path)

    if not server_dir.exists():
        print(f"[ERROR] No existe el directorio del servidor: {server_dir}")
        raise SystemExit(1)

    os.chdir(server_dir)
    sys.path.insert(0, str(server_dir))

    database_url, tunnel = resolve_database_url(repo_root)
    os.environ["DATABASE_URL"] = database_url
    if tunnel is not None:
        atexit.register(tunnel.terminate)

    preferred_port = require_port_env("SERVER_PREFERRED_PORT")
    search_if_busy = require_bool_env("SERVER_PORT_SEARCH")
    port = pick_port(preferred_port=preferred_port, search_if_busy=search_if_busy, port_name="SERVER_PREFERRED_PORT")
    upsert_env_var(env_path, key="SERVER_PORT", value=str(port))

    app_module = "app.main:app"
    host = require_env("SERVER_HOST")
    reload_enabled = require_bool_env("SERVER_RELOAD")

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
