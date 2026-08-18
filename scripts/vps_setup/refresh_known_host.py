from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Actualiza la clave del host SSH guardada en known_hosts para evitar el error:
REMOTE HOST IDENTIFICATION HAS CHANGED!

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP y VPS_USER.
4) Elimina entradas existentes de known_hosts para esa IP.
5) Hace un intento de conexión SSH en modo batch para que SSH registre la clave actual del host en known_hosts.
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


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"[ERROR] No se encontró el comando: {args[0]}")
        raise SystemExit(1)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    ip = _require_env("VPS_IP")
    user = _require_env("VPS_USER")
    ssh_dir = Path.home() / ".ssh"
    known_hosts = ssh_dir / "known_hosts"

    print("[WARN] Solo haz esto si confirmaste que el VPS es el correcto.")
    print(f"[INFO] known_hosts: {known_hosts}")
    print(f"[INFO] VPS_IP: {ip}")

    if not ssh_dir.exists():
        print(f"[ERROR] No existe la carpeta ~/.ssh: {ssh_dir}")
        raise SystemExit(1)

    print("[INFO] Eliminando entradas previas de known_hosts para esa IP...")
    remove = _run(["ssh-keygen", "-f", str(known_hosts), "-R", ip])
    if remove.stdout:
        print(remove.stdout.rstrip("\n"))
    if remove.stderr:
        print(remove.stderr.rstrip("\n"))
    if remove.returncode != 0 and known_hosts.exists():
        print("[ERROR] No se pudo limpiar known_hosts.")
        raise SystemExit(1)

    print("[INFO] Registrando la clave actual del host con ssh (sin pedir contraseña)...")
    if not known_hosts.exists():
        known_hosts.write_text("", encoding="utf-8")

    ssh_args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "NumberOfPasswordPrompts=0",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "ConnectTimeout=10",
        f"{user}@{ip}",
        "exit",
    ]
    ssh_result = _run(ssh_args)
    if ssh_result.stdout:
        print(ssh_result.stdout.rstrip("\n"))
    if ssh_result.stderr:
        print(ssh_result.stderr.rstrip("\n"))

    check = _run(["ssh-keygen", "-f", str(known_hosts), "-F", ip])
    if not check.stdout.strip():
        print("[ERROR] No se encontró una entrada para esa IP en known_hosts.")
        raise SystemExit(1)

    print("[OK] Clave actualizada en known_hosts.")
    print("[INFO] Entrada registrada:")
    print(check.stdout.rstrip("\n"))

    if ssh_result.returncode == 0:
        return
    print(
        "[WARN] El intento de conexión terminó con error. Si ves 'Permission denied', es normal: "
        "el objetivo era registrar la clave del host, no autenticar."
    )


if __name__ == "__main__":
    main()

