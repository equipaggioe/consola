import os
import subprocess
import urllib.request
import urllib.error
import json
from pathlib import Path

"""
Deshace el setup:
- elimina SSH key del VPS
- elimina public key del VPS
- elimina key de GitHub (por title)
"""

# =========================================================
# CONFIG
# =========================================================

def _find_env_file() -> Path:
    start = Path(__file__).resolve().parent
    for p in [start, *start.parents]:
        candidate = p / ".env"
        if candidate.is_file():
            return candidate
    raise RuntimeError("No se encontró .env en la raíz del proyecto.")


def _load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


_load_env(_find_env_file())


def _require(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Falta variable requerida en .env: {name}")
    return v


VPS_IP = _require("VPS_IP")
VPS_USER = _require("VPS_USER")
GITHUB_TOKEN = _require("GITHUB_TOKEN")
KEY_TITLE = _require("GITHUB_KEY_TITLE")
LOCAL_IDENTITY_FILE = Path.home() / ".ssh" / _require("VPS_KEY_NAME")

# =========================================================
# SSH RUNNER
# =========================================================

def run_remote(command: str):

    return subprocess.run(
        [
            "ssh",
            "-i",
            str(LOCAL_IDENTITY_FILE),
            f"{VPS_USER}@{VPS_IP}",
            command
        ],
        text=True
    )

# =========================================================
# 1. BORRAR KEYS DEL VPS
# =========================================================

print("Eliminando SSH keys del VPS...")

run_remote(
    "rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub"
)

print("Keys eliminadas del VPS.")

# =========================================================
# 2. ELIMINAR KEY DE GITHUB
# =========================================================

print("Buscando keys en GitHub...")

req = urllib.request.Request(
    "https://api.github.com/user/keys",
    headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
)

try:
    with urllib.request.urlopen(req) as response:
        keys = json.loads(response.read().decode())

except urllib.error.HTTPError as e:
    raise Exception(e.read().decode())

# Buscar key por título
key_id = None

for k in keys:
    if k.get("title") == KEY_TITLE:
        key_id = k.get("id")
        break

if key_id:

    print(f"Eliminando key en GitHub (ID: {key_id})...")

    del_req = urllib.request.Request(
        f"https://api.github.com/user/keys/{key_id}",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        },
        method="DELETE"
    )

    try:
        urllib.request.urlopen(del_req)
        print("Key eliminada de GitHub.")

    except urllib.error.HTTPError as e:
        print(e.read().decode())
        raise

else:
    print("No se encontró la key en GitHub.")

# =========================================================
# FINAL
# =========================================================

print("\nCLEANUP COMPLETADO")
