from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

"""
Abre un túnel SSH para PostgreSQL desde tu máquina local hacia el VPS.

Flujo:
1) Carga credenciales del VPS desde scripts/.env (local): VPS_IP, VPS_USER, VPS_KEY_NAME.
2) Valida que exista la llave privada local: ~/.ssh/<VPS_KEY_NAME>.
3) Abre un túnel SSH: <local_host>:<local_port> -> <remote_host>:<remote_port> en el VPS.
4) Opcional: si existe server/.env, lee DATABASE_URL para imprimir una URL sugerida usando el túnel (sin mostrar el password).

Uso:
python scripts/vps/ssh_tunnel_postgres.py --local-port 15432
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, peek_env_value

DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = 5432
DEFAULT_REMOTE_HOST = "127.0.0.1"
DEFAULT_REMOTE_PORT = 5432


def _mask_database_url(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return "(no se pudo parsear DATABASE_URL)"

    if not parsed.scheme:
        return "(DATABASE_URL inválida)"

    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.split("@", 1)
        if ":" in userinfo:
            user, _pw = userinfo.split(":", 1)
            userinfo = f"{user}:****"
        netloc = f"{userinfo}@{hostinfo}"

    safe = parsed._replace(netloc=netloc)
    return urlunparse(safe)


def _suggest_local_database_url(raw_url: str, *, local_host: str, local_port: int) -> str | None:
    try:
        parsed = urlparse(raw_url)
    except Exception:
        return None

    if parsed.scheme not in {"postgresql", "postgres"} and not parsed.scheme.startswith("postgresql+"):
        return None

    username = parsed.username or ""
    password = parsed.password or ""
    hostname = local_host
    port = local_port

    hostinfo = hostname
    if port:
        hostinfo = f"{hostname}:{port}"

    if username:
        userinfo = username
        if password:
            userinfo = f"{username}:{password}"
        netloc = f"{userinfo}@{hostinfo}"
    else:
        netloc = hostinfo

    suggested = parsed._replace(netloc=netloc)
    return urlunparse(suggested)


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre un túnel SSH hacia PostgreSQL en el VPS.")
    parser.add_argument("--local-host", type=str, default=DEFAULT_LOCAL_HOST)
    parser.add_argument("--local-port", type=int, default=DEFAULT_LOCAL_PORT)
    parser.add_argument("--remote-host", type=str, default=DEFAULT_REMOTE_HOST)
    parser.add_argument("--remote-port", type=int, default=DEFAULT_REMOTE_PORT)
    args = parser.parse_args()

    local_host = str(args.local_host).strip() or DEFAULT_LOCAL_HOST
    local_port = int(args.local_port)
    remote_host = str(args.remote_host).strip() or DEFAULT_REMOTE_HOST
    remote_port = int(args.remote_port)

    if not (1 <= local_port <= 65535):
        print("[ERROR] --local-port inválido.")
        raise SystemExit(2)
    if not (1 <= remote_port <= 65535):
        print("[ERROR] --remote-port inválido.")
        raise SystemExit(2)

    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    forward = f"{local_host}:{local_port}:{remote_host}:{remote_port}"
    target = f"{vps_user}@{vps_ip}"

    print("[INFO] Túnel SSH PostgreSQL")
    print(f"[INFO] VPS: {target}")
    print(f"[INFO] Forward: {forward}")
    print("[INFO] Para cerrar el túnel, presiona Ctrl+C en esta ventana.")

    server_env_path = repo_root / "server" / ".env"
    raw_database_url = peek_env_value(server_env_path, "DATABASE_URL")
    if raw_database_url:
        safe_url = _mask_database_url(raw_database_url)
        print(f"[INFO] server/.env DATABASE_URL (sin password): {safe_url}")

        suggested = _suggest_local_database_url(
            raw_database_url, local_host=local_host, local_port=local_port
        )
        if suggested:
            safe_suggested = _mask_database_url(suggested)
            print(f"[INFO] Sugerencia (con túnel, sin password): {safe_suggested}")

    cmd = [
        "ssh",
        "-i",
        str(identity_file),
        "-N",
        "-L",
        forward,
        target,
    ]
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()

