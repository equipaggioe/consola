from __future__ import annotations

import subprocess
import sys
from pathlib import Path

"""
Actualiza la clave del host SSH guardada en known_hosts para evitar el error:
REMOTE HOST IDENTIFICATION HAS CHANGED!

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env, VPS_IP y VPS_USER (default: nombre del repo si no está definida).
3) Elimina entradas existentes de known_hosts para esa IP.
4) Hace un intento de conexión SSH en modo batch para que SSH registre la clave actual del host en known_hosts.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_ip_user


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"[ERROR] No se encontró el comando: {args[0]}")
        raise SystemExit(1)


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    ip, user = load_vps_ip_user(repo_root)
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

