from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Verifica la salud general del servidor en el VPS.

Muestra:
  - Espacio en disco (total, usado, disponible, tamaño por directorio)
  - Memoria RAM (total, usado, disponible)
  - CPU (uptime, load average, procesos pesados)
  - Conexiones activas (puertos abiertos, conexiones establecidas)
"""


def _find_env_file() -> Path:
    start = Path(__file__).resolve().parent
    for path in [start, *start.parents]:
        candidate = path / ".env"
        if candidate.is_file():
            return candidate
    raise RuntimeError("No se encontró .env.")


def _load_env(path: Path) -> None:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(_find_env_file())


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta variable requerida: {name}")
    return value


def run_remote(command: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["ssh", "-i", str(LOCAL_IDENTITY_FILE), f"{VPS_USER}@{VPS_IP}", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Comando excedió timeout ({timeout}s)")


def run_remote_checked(command: str, timeout: int = 10) -> str:
    result = run_remote(command, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Comando falló: {result.stderr}")
    return result.stdout.strip()


VPS_IP = _require("VPS_IP")
VPS_USER = _require("VPS_USER")
VPS_KEY_NAME = _require("VPS_KEY_NAME")

LOCAL_IDENTITY_FILE = Path.home() / ".ssh" / VPS_KEY_NAME


def check_disk_space():
    print("\n" + "=" * 50)
    print("ESPACIO EN DISCO")
    print("=" * 50)

    try:
        output = run_remote_checked("df -h /srv", timeout=10)
        print(output)
    except Exception as e:
        print(f"⚠️  Error: {e}")

    print("\nTamaño por directorio:")
    try:
        output = run_remote_checked("du -sh /srv/* 2>/dev/null | sort -hr | head -10", timeout=15)
        print(output)
    except Exception as e:
        print(f"⚠️  Error: {e}")


def check_memory():
    print("\n" + "=" * 50)
    print("MEMORIA RAM")
    print("=" * 50)

    try:
        output = run_remote_checked("free -h", timeout=10)
        print(output)
    except Exception as e:
        print(f"⚠️  Error: {e}")


def check_cpu():
    print("\n" + "=" * 50)
    print("CPU Y CARGA")
    print("=" * 50)

    try:
        output = run_remote_checked("uptime", timeout=10)
        print(f"Uptime: {output}")
    except Exception as e:
        print(f"⚠️  Error: {e}")

    print("\nTop 5 procesos por CPU:")
    try:
        output = run_remote_checked(
            "ps aux --sort=-%cpu | head -6 | awk '{print $1, $3, $11}'", timeout=10
        )
        print(output)
    except Exception as e:
        print(f"⚠️  Error: {e}")


def check_connections():
    print("\n" + "=" * 50)
    print("CONEXIONES ACTIVAS")
    print("=" * 50)

    try:
        output = run_remote_checked("ss -tulpn | grep LISTEN", timeout=10)
        print(output)
    except Exception as e:
        print(f"⚠️  Error: {e}")

    print("\nConexiones establecidas:")
    try:
        count = run_remote_checked("ss -tulpn | grep ESTABLISHED | wc -l", timeout=10)
        print(f"Total: {count}")
    except Exception as e:
        print(f"⚠️  Error: {e}")


def check_recent_errors():
    print("\n" + "=" * 50)
    print("ERRORES RECIENTES (últimas 24h)")
    print("=" * 50)

    try:
        output = run_remote_checked(
            "sudo journalctl -p err --since '24 hours ago' -n 20 --no-pager",
            timeout=10
        )
        if output:
            print(output)
        else:
            print("✓ Sin errores del sistema")
    except Exception as e:
        print(f"⚠️  Error: {e}")


def main():
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
