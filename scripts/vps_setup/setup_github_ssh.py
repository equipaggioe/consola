import os
import subprocess
import urllib.request
import urllib.error
import json
from pathlib import Path

"""
Se conecta al VPS
Genera SSH key en el VPS
Lee la llave pública
La registra automáticamente en GitHub
Prueba conexión SSH GitHub
"""

# =========================================================
# CONFIGURACION
# =========================================================

# Token GitHub (classic)
# Permisos necesarios:
# - admin:public_key
# - repo (opcional)
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

# Nombre visible en GitHub
KEY_TITLE = _require("GITHUB_KEY_TITLE")

LOCAL_IDENTITY_FILE = Path.home() / ".ssh" / _require("VPS_KEY_NAME")

# =========================================================
# HELPERS
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
        capture_output=True,
        text=True
    )

# =========================================================
# 1. VERIFICAR SSH KEY
# =========================================================

print("Verificando llave SSH en VPS...")

check_key = run_remote("if [ -f ~/.ssh/id_ed25519.pub ]; then echo EXISTS; else echo MISSING; fi")

if "EXISTS" not in check_key.stdout:

    print("Generando llave SSH en VPS...")

    run_remote(
        'mkdir -p ~/.ssh && '
        'chmod 700 ~/.ssh && '
        'ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""'
    )

else:
    print("La llave ya existe.")

# =========================================================
# 2. LEER LLAVE PUBLICA
# =========================================================

print("Leyendo llave publica...")

pubkey_result = run_remote(
    "cat ~/.ssh/id_ed25519.pub"
)

PUBLIC_KEY = pubkey_result.stdout.strip()

if not PUBLIC_KEY:
    raise Exception("No se pudo leer la llave publica del VPS.")

# =========================================================
# 3. REGISTRAR EN GITHUB
# =========================================================

print("Registrando llave en GitHub...")

payload = json.dumps({
    "title": KEY_TITLE,
    "key": PUBLIC_KEY
}).encode("utf-8")

request = urllib.request.Request(
    "https://api.github.com/user/keys",
    data=payload,
    headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json"
    },
    method="POST"
)

try:

    with urllib.request.urlopen(request) as response:

        if response.status == 201:
            print("Llave registrada correctamente.")

except urllib.error.HTTPError as e:

    if e.code == 422:
        print("La llave ya existe en GitHub.")

    else:
        print(e.read().decode())
        raise

# =========================================================
# 4. PROBAR CONEXION GITHUB
# =========================================================

print("Probando conexion GitHub...")

test_result = run_remote(
    "ssh -o StrictHostKeyChecking=no -T git@github.com || true"
)

print(test_result.stdout)
print(test_result.stderr)

# =========================================================
# FINAL
# =========================================================

print("\nSETUP SSH GITHUB COMPLETADO")
