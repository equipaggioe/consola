from __future__ import annotations

import sys
from pathlib import Path

"""
Deshace el setup:
- elimina SSH key del VPS
- elimina public key del VPS
- elimina key de GitHub (por title)
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, github_api_request, load_vps_config, require_env, run_ssh_checked


def main() -> None:
    vps_ip, vps_user, identity_file = load_vps_config(find_project_root(Path(__file__).resolve().parent))

    github_token = require_env("GITHUB_TOKEN")
    key_title = require_env("GITHUB_KEY_TITLE")

    print("[INFO] Eliminando SSH keys del VPS...")
    try:
        run_ssh_checked(
            "rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub",
            identity_file=identity_file,
            user=vps_user,
            host=vps_ip,
        )
    except RuntimeError as exc:
        print(f"[ERROR] No se pudieron eliminar las keys del VPS: {exc}")
        raise SystemExit(1)
    print("[OK] Keys eliminadas del VPS.")

    print("[INFO] Buscando keys en GitHub...")
    status, keys = github_api_request("GET", "https://api.github.com/user/keys", token=github_token)
    if status != 200 or not isinstance(keys, list):
        print(f"[ERROR] No se pudo listar las keys de GitHub (status {status}): {keys}")
        raise SystemExit(1)

    key_id = None
    for k in keys:
        if isinstance(k, dict) and k.get("title") == key_title:
            key_id = k.get("id")
            break

    if key_id is None:
        print("[INFO] No se encontró la key en GitHub.")
    else:
        print(f"[INFO] Eliminando key en GitHub (ID: {key_id})...")
        status, payload = github_api_request(
            "DELETE", f"https://api.github.com/user/keys/{key_id}", token=github_token
        )
        if status != 204:
            print(f"[ERROR] No se pudo eliminar la key de GitHub (status {status}): {payload}")
            raise SystemExit(1)
        print("[OK] Key eliminada de GitHub.")

    print("\n[OK] CLEANUP COMPLETADO")


if __name__ == "__main__":
    main()
