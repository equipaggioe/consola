from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

def _repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("No se encontró la raíz del repo (.git).")

sys.path.insert(0, str(_repo_root(Path(__file__).resolve()) / "scripts"))
from common import (
    detect_os,
    load_vps_ip_user,
    maybe_dispatch_remote,
    optional_env,
    require_env,
    windows_postgres_port,
)

"""
Teardown de PostgreSQL, soporta Linux (VPS) y Windows (desarrollo local):

- Si RUN_REMOTE=true (scripts/.env), se reenvía a sí mismo por SSH para correr en el VPS
  (ver common.maybe_dispatch_remote) y termina localmente con el mismo exit code.
- Termina las conexiones activas a la base de datos de la app.
- Elimina la base de datos (DROP DATABASE IF EXISTS).
- Elimina el rol de la app (DROP ROLE IF EXISTS).
- Quita la línea DATABASE_URL de server/.env si está presente.

No modifica pg_hba.conf, reglas de firewall ni la contraseña del superusuario.

Linux (VPS):
- Las operaciones corren como el superusuario "postgres" vía `sudo -u postgres`
  (autenticación peer, sin pedir contraseña de superusuario).

Windows (desarrollo local):
- Se asume una instalación por defecto de PostgreSQL 17 en
  `C:\\Program Files\\PostgreSQL\\17`. El puerto se detecta leyendo 'port' desde
  postgresql.conf en esa instalación (no se asume un puerto fijo).
- Usuario y contraseña del superusuario de Postgres, ya que en Windows no hay `sudo -u postgres`:
  PG_SUPERUSER (scripts/.env, default "postgres" si falta o está vacía) y la contraseña,
  resuelta en este orden: argumento de línea de comando > PG_PASSWORD (scripts/.env)
  > interactivo (getpass).

Uso (argumento posicional, sin banderas):
- Sin argumentos: en Windows usa PG_PASSWORD (scripts/.env); si falta, la pide de
  forma interactiva (en Linux no aplica).
- 1 argumento: PG_PASSWORD, tiene prioridad sobre scripts/.env (solo efecto en Windows).
"""


# Variables de scripts/.env que necesita la rama remota (Linux/VPS) de este script.
# Se declaran acá, al lado del código que las usa, y se le pasan a maybe_dispatch_remote().
REMOTE_ENV_KEYS = {"VPS_USER", "SERVER_DIR", "DB_NAME"}
WIN_PG_VERSION = "17"
WIN_PG_INSTALL_DIR = Path(r"C:\Program Files\PostgreSQL") / WIN_PG_VERSION
WIN_PG_BIN_DIR = WIN_PG_INSTALL_DIR / "bin"
WIN_PG_DATA_DIR = WIN_PG_INSTALL_DIR / "data"

@dataclass(frozen=True)
class Config:
    db_name: str
    db_user: str


@dataclass(frozen=True)
class WindowsSuperuser:
    name: str
    password: str


def _require_ident(name: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise SystemExit(f"[ERROR] Falta valor: {name}")
    if not re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
        raise SystemExit(
            f"[ERROR] {name} inválido: {v}. Usa solo letras, números y '_' y no empieces con número."
        )
    return v


def _require_password(name: str, value: str) -> str:
    v = (value or "").strip()
    if not v:
        v = getpass.getpass(f"{name}: ").strip()
    if not v:
        raise SystemExit(f"[ERROR] Falta valor: {name}")
    return v


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _teardown_sql(db_name_ident: str, db_name_lit: str, db_user_ident: str) -> str:
    return "\n".join(
        [
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = {db_name_lit} AND pid <> pg_backend_pid();",
            f"DROP DATABASE IF EXISTS {db_name_ident};",
            f"DROP ROLE IF EXISTS {db_user_ident};",
            "",
        ]
    )


def _remove_database_url(env_path: Path) -> str:
    if not env_path.is_file():
        return "sin cambios (no existe el archivo)"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    output = [line for line in lines if not line.startswith("DATABASE_URL=")]
    if len(output) == len(lines):
        return "sin cambios (no estaba presente)"
    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return "eliminada"


# --- Linux (VPS): operaciones vía `sudo -u postgres` ---------------------------------------


def _psql_as_postgres(sql: str) -> None:
    args = ["sudo", "-n", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-d", "postgres"]
    result = subprocess.run(
        args,
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout.strip():
        print(result.stdout.rstrip("\n"))
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló el comando (exit {result.returncode}).")


def apply_linux(cfg: Config) -> None:
    db_name_ident = _quote_ident(cfg.db_name)
    db_name_lit = _quote_literal(cfg.db_name)
    db_user_ident = _quote_ident(cfg.db_user)

    _psql_as_postgres(_teardown_sql(db_name_ident, db_name_lit, db_user_ident))

    print("[OK] Teardown completado (Linux).")


# --- Windows (desarrollo local): operaciones vía TCP con el superusuario --------------------


def _win_postgres_port() -> str:
    try:
        return windows_postgres_port(version=WIN_PG_VERSION)
    except (FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"[ERROR] {exc}")


def _run_psql_windows(superuser: WindowsSuperuser, db: str, sql: str, *, port: str) -> None:
    psql_exe = str(WIN_PG_BIN_DIR / "psql.exe")
    env = {**os.environ, "PGPASSWORD": superuser.password}
    result = subprocess.run(
        [
            psql_exe,
            "-U",
            superuser.name,
            "-h",
            "127.0.0.1",
            "-p",
            port,
            "-v",
            "ON_ERROR_STOP=1",
            "-X",
            "-q",
            "-d",
            db,
        ],
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip("\n"))
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló el comando (exit {result.returncode}).")


def apply_windows(cfg: Config, superuser: WindowsSuperuser) -> None:
    port = _win_postgres_port()
    db_name_ident = _quote_ident(cfg.db_name)
    db_name_lit = _quote_literal(cfg.db_name)
    db_user_ident = _quote_ident(cfg.db_user)

    _run_psql_windows(superuser, "postgres", _teardown_sql(db_name_ident, db_name_lit, db_user_ident), port=port)

    print("[OK] Teardown completado (Windows).")


def _parse_password_arg(args: list[str]) -> str:
    if not args:
        return optional_env("PG_PASSWORD", "")
    if len(args) == 1:
        return args[0]
    raise SystemExit(
        f"[ERROR] Argumentos inválidos. Uso: {Path(sys.argv[0]).name} [PG_PASSWORD]"
    )


def main() -> None:
    maybe_dispatch_remote(Path(__file__), sys.argv[1:], REMOTE_ENV_KEYS)

    repo_root = _repo_root(Path(__file__).resolve())
    _vps_ip, vps_user = load_vps_ip_user(repo_root)
    server_root = repo_root / require_env("SERVER_DIR")

    db_name = optional_env("DB_NAME", f"{vps_user}_db")

    cfg = Config(
        db_name=_require_ident("DB_NAME", db_name),
        db_user=_require_ident("VPS_USER", vps_user),
    )

    os_key = detect_os()

    if os_key == "windows":
        superuser_name = optional_env("PG_SUPERUSER", "postgres")
        superuser_password = _require_password(
            f"SUPERUSER_PASSWORD ({superuser_name})",
            _parse_password_arg(sys.argv[1:])
        )
        superuser = WindowsSuperuser(name=superuser_name, password=superuser_password)
        apply_windows(cfg, superuser)
    else:
        apply_linux(cfg)

    env_path = server_root / ".env"
    action = _remove_database_url(env_path)
    print(f"[OK] DATABASE_URL {action} en {env_path}")


if __name__ == "__main__":
    main()
