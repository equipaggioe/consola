from __future__ import annotations

import sys
from pathlib import Path

"""
Verifica la salud general del servidor en el VPS.

Muestra:
  - Espacio en disco (total, usado, disponible, tamaño por directorio)
  - Memoria RAM (total, usado, disponible)
  - CPU (uptime, load average, procesos pesados)
  - Conexiones activas (puertos abiertos, conexiones establecidas)
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, run_ssh_checked


def run_remote_checked(command: str, timeout: int = 10) -> str:
    return run_ssh_checked(command, identity_file=LOCAL_IDENTITY_FILE, user=VPS_USER, host=VPS_IP, timeout=timeout)


def _run_step(label: str, command: str, *, timeout: int = 10, empty_message: str | None = None) -> None:
    if label:
        print(label)
    try:
        output = run_remote_checked(command, timeout=timeout)
        if output:
            print(output)
        elif empty_message:
            print(empty_message)
    except Exception as e:
        print(f"⚠️  Error: {e}")


def check_disk_space():
    print("\n" + "=" * 50)
    print("ESPACIO EN DISCO")
    print("=" * 50)

    _run_step("", "df -h /srv", timeout=10)
    _run_step("\nTamaño por directorio:", "du -sh /srv/* 2>/dev/null | sort -hr | head -10", timeout=15)


def check_memory():
    print("\n" + "=" * 50)
    print("MEMORIA RAM")
    print("=" * 50)

    _run_step("", "free -h", timeout=10)


def check_cpu():
    print("\n" + "=" * 50)
    print("CPU Y CARGA")
    print("=" * 50)

    _run_step("", "uptime", timeout=10)
    _run_step(
        "\nTop 5 procesos por CPU:",
        "ps aux --sort=-%cpu | head -6 | awk '{print $1, $3, $11}'",
        timeout=10,
    )


def check_connections():
    print("\n" + "=" * 50)
    print("CONEXIONES ACTIVAS")
    print("=" * 50)

    _run_step("", "ss -tulpn | grep LISTEN", timeout=10)
    _run_step("\nConexiones establecidas:", "ss -tulpn | grep ESTABLISHED | wc -l", timeout=10)


def check_recent_errors():
    print("\n" + "=" * 50)
    print("ERRORES RECIENTES (últimas 24h)")
    print("=" * 50)

    _run_step(
        "",
        "sudo journalctl -p err --since '24 hours ago' -n 20 --no-pager",
        timeout=10,
        empty_message="✓ Sin errores del sistema",
    )


def main():
    global VPS_IP, VPS_USER, LOCAL_IDENTITY_FILE

    VPS_IP, VPS_USER, LOCAL_IDENTITY_FILE = load_vps_config(find_project_root(Path(__file__).resolve().parent))

    print(f"\n[INFO] Conectando a {VPS_IP}...")

    try:
        check_disk_space()
        check_memory()
        check_cpu()
        check_connections()
        check_recent_errors()

        print("\n" + "=" * 50)
        print("REVISIÓN COMPLETADA")
        print("=" * 50 + "\n")

    except KeyboardInterrupt:
        print("\n\n[INFO] Cancelado por el usuario.")
        raise SystemExit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
