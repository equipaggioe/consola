from __future__ import annotations

import argparse
import subprocess
import sys
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_env_file, load_vps_config, require_env, run_ssh, run_ssh_checked, scp_transfer

DEFAULT_BACKUP_DIR = ".backups"
DEFAULT_KEEP_BACKUPS = 7
DEFAULT_REMOTE_TEMP_DIR = "/tmp"
DEFAULT_PG_DUMP_HOST = "localhost"
DEFAULT_SSH_TIMEOUT = 30


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

    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    server_env_path = repo_root / "server" / ".env"
    load_env_file(server_env_path)

    pg_db = require_env("POSTGRES_DB")
    pg_user = require_env("POSTGRES_USER")
    pg_password = require_env("POSTGRES_PASSWORD")

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
    check_result = run_ssh(
        "command -v pg_dump",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
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
        run_ssh_checked(
            dump_cmd,
            identity_file=identity_file,
            user=vps_user,
            host=vps_ip,
            timeout=120,
        )
    except RuntimeError as exc:
        print(f"[ERROR] Falló pg_dump en el VPS: {exc}")
        raise SystemExit(1)

    print(f"[INFO] Descargando dump a: {local_dump_path}")
    try:
        scp_transfer(
            local_dump_path,
            remote_dump_path,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
            direction="download",
        )
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Falló la descarga con scp: {exc}")
        print("[INFO] Limpiando archivo temporal en el VPS...")
        run_ssh(
            f"rm -f {remote_dump_path}",
            identity_file=identity_file,
            user=vps_user,
            host=vps_ip,
        )
        raise SystemExit(1)

    print("[INFO] Borrando archivo temporal en el VPS...")
    cleanup_result = run_ssh(
        f"rm -f {remote_dump_path}",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
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
