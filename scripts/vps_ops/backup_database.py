from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path

"""
Respalda localmente la base de datos PostgreSQL que corre en el VPS.

Flujo:
1) Carga scripts/.env (VPS_IP, VPS_USER, VPS_KEY_NAME) y server/.env (POSTGRES_DB,
   POSTGRES_USER, POSTGRES_PASSWORD).
2) Ejecuta pg_dump en el VPS por SSH (formato custom -Fc) hacia un archivo temporal.
3) Descarga el dump con scp a la carpeta local de backups.
4) Borra el archivo temporal en el VPS.
5) Rota backups locales, conservando solo los últimos --keep.

Uso:
python scripts/vps_ops/backup_database.py
python scripts/vps_ops/backup_database.py --keep 14
python scripts/vps_ops/backup_database.py --backup-dir /ruta/custom --keep 10
"""


DEFAULT_BACKUP_DIR = ".backups"
DEFAULT_KEEP_BACKUPS = 7
DEFAULT_REMOTE_TEMP_DIR = "/tmp"
DEFAULT_PG_DUMP_HOST = "localhost"
DEFAULT_SSH_TIMEOUT = 30


def _find_env_file(start: Path) -> Path:
    for path in [start, *start.parents]:
        candidate = path / ".env"
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"No se encontró .env a partir de: {start}")


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


def run_remote(
    cmd: str,
    *,
    identity_file: Path,
    vps_user: str,
    vps_ip: str,
    timeout: int = DEFAULT_SSH_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Comando SSH excedió timeout ({timeout}s): {cmd}")


def run_remote_checked(
    cmd: str,
    *,
    identity_file: Path,
    vps_user: str,
    vps_ip: str,
    timeout: int = DEFAULT_SSH_TIMEOUT,
) -> str:
    result = run_remote(
        cmd, identity_file=identity_file, vps_user=vps_user, vps_ip=vps_ip, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(f"Comando remoto falló: {result.stderr.strip()}")
    return result.stdout.strip()


def rotate_backups(backup_dir: Path, keep: int, db_name: str) -> None:
    dumps = sorted(
        backup_dir.glob(f"{db_name}_*.dump"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_dump in dumps[keep:]:
        print(f"[INFO] Borrando backup antiguo: {old_dump.name}")
        old_dump.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Respalda la base de datos PostgreSQL del VPS.")
    parser.add_argument("--backup-dir", type=str, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP_BACKUPS)
    parser.add_argument("--remote-temp", type=str, default=DEFAULT_REMOTE_TEMP_DIR)
    parser.add_argument("--pg-host", type=str, default=DEFAULT_PG_DUMP_HOST)
    args = parser.parse_args()

    keep = int(args.keep)
    if keep < 1:
        print("[ERROR] --keep debe ser >= 1.")
        raise SystemExit(2)

    repo_root = Path(__file__).resolve().parents[2]

    scripts_env_path = repo_root / "scripts" / ".env"
    _load_env_file(scripts_env_path)

    vps_ip = _require_env("VPS_IP")
    vps_user = _require_env("VPS_USER")
    vps_key_name = _require_env("VPS_KEY_NAME")

    identity_file = Path.home() / ".ssh" / vps_key_name
    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave privada local: {identity_file}")
        raise SystemExit(1)

    server_env_path = repo_root / "server" / ".env"
    _load_env_file(server_env_path)

    pg_db = _require_env("POSTGRES_DB")
    pg_user = _require_env("POSTGRES_USER")
    pg_password = _require_env("POSTGRES_PASSWORD")

    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_absolute():
        backup_dir = repo_root / backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_filename = f"{pg_db}_{timestamp}.dump"
    remote_dump_path = f"{args.remote_temp.rstrip('/')}/{dump_filename}"
    local_dump_path = backup_dir / dump_filename

    print("[INFO] Respaldo de PostgreSQL en el VPS")
    print(f"[INFO] VPS: {vps_user}@{vps_ip}")
    print(f"[INFO] Base de datos: {pg_db}")
    print(f"[INFO] Carpeta local de backups: {backup_dir}")

    print("[INFO] Verificando que pg_dump exista en el VPS...")
    check_result = run_remote(
        "command -v pg_dump",
        identity_file=identity_file,
        vps_user=vps_user,
        vps_ip=vps_ip,
    )
    if check_result.returncode != 0:
        print("[ERROR] pg_dump no está disponible en el VPS.")
        raise SystemExit(1)

    print("[INFO] Generando dump en el VPS...")
    dump_cmd = (
        f"PGPASSWORD='{pg_password}' pg_dump -h {args.pg_host} -U {pg_user} "
        f"-d {pg_db} -Fc -f {remote_dump_path}"
    )
    try:
        run_remote_checked(
            dump_cmd,
            identity_file=identity_file,
            vps_user=vps_user,
            vps_ip=vps_ip,
            timeout=120,
        )
    except RuntimeError as exc:
        print(f"[ERROR] Falló pg_dump en el VPS: {exc}")
        raise SystemExit(1)

    print(f"[INFO] Descargando dump a: {local_dump_path}")
    scp_result = subprocess.run(
        ["scp", "-i", str(identity_file), f"{vps_user}@{vps_ip}:{remote_dump_path}", str(local_dump_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if scp_result.returncode != 0:
        print(f"[ERROR] Falló la descarga con scp: {scp_result.stderr.strip()}")
        print("[INFO] Limpiando archivo temporal en el VPS...")
        run_remote(
            f"rm -f {remote_dump_path}",
            identity_file=identity_file,
            vps_user=vps_user,
            vps_ip=vps_ip,
        )
        raise SystemExit(1)

    print("[INFO] Borrando archivo temporal en el VPS...")
    cleanup_result = run_remote(
        f"rm -f {remote_dump_path}",
        identity_file=identity_file,
        vps_user=vps_user,
        vps_ip=vps_ip,
    )
    if cleanup_result.returncode != 0:
        print(f"[WARN] No se pudo borrar el archivo temporal en el VPS: {remote_dump_path}")

    size_kb = local_dump_path.stat().st_size / 1024
    print(f"[OK] Backup descargado: {local_dump_path.name} ({size_kb:.1f} KB)")

    print(f"[INFO] Rotando backups locales (conservando últimos {keep})...")
    rotate_backups(backup_dir, keep, pg_db)

    print("[OK] LISTO")


if __name__ == "__main__":
    main()
