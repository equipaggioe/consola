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
    repo_name_from_git_url,
    require_env,
    restart_systemd_service,
    upsert_env_var,
    windows_postgres_port,
)

"""
Bootstrap de PostgreSQL, soporta Linux (VPS) y Windows (desarrollo local):

- Si RUN_REMOTE=true (scripts/.env), se reenvía a sí mismo por SSH para correr en el VPS
  (ver common.maybe_dispatch_remote) y termina localmente con el mismo exit code.
- Crea el rol de la app (mismo nombre que VPS_USER) si no existe y le asigna contraseña.
  La contraseña del rol (DB_PASSWORD) se lee siempre desde scripts/.env; si falta, error.
- Crea la base de datos si no existe y asegura el owner.
- Otorga privilegios básicos.
- Agrega una regla "host" en pg_hba.conf que permite autenticación por contraseña
  (scram-sha-256) desde 127.0.0.1.
- Bloquea el acceso externo al puerto de Postgres (defensa en profundidad; las conexiones
  locales/loopback no se ven afectadas).
- Escribe DATABASE_URL en server/.env, salvo que UPDATE_ENV = False más abajo;
  útil si server/.env ya apunta a otro destino (por ejemplo, un túnel SSH al VPS) y no quieres
  perder ese valor al correr el bootstrap.
- Si corre en el VPS (Linux) y se escribió DATABASE_URL, reinicia el servicio systemd
  (mismo REPO_NAME que usa install_systemd_service.py / run_systemd_action.py) para que
  tome la nueva URL. Si el servicio todavía no existe, solo avisa.

Linux (VPS):
- El rol conecta por peer (sin contraseña) desde el socket Unix local; DB_PASSWORD solo se
  usa para conexiones por TCP (por ejemplo, a través de un túnel SSH).
- Las operaciones administrativas corren como el superusuario "postgres" vía `sudo -u postgres`
  (autenticación peer, sin pedir contraseña de superusuario).
- No se modifica la contraseña del superusuario "postgres".
- Puerto y socket de Postgres: los configurados en el servidor (`SHOW port` /
  `SHOW unix_socket_directories`).

Windows (desarrollo local):
- Se asume una instalación por defecto de PostgreSQL 17 en
  `C:\\Program Files\\PostgreSQL\\17`. El puerto se detecta leyendo 'port' desde
  postgresql.conf en esa instalación (no se asume un puerto fijo).
- Todo el acceso es por TCP a 127.0.0.1, con contraseña (no hay socket Unix/peer).
- Se conecta solo a localhost, así que no hace falta tocar pg_hba.conf (viene habilitado
  por defecto para 127.0.0.1) ni el firewall de Windows (no filtra tráfico loopback).
  Por lo mismo, no requiere privilegios de administrador ni elevación.
- Usuario y contraseña del superusuario de Postgres, ya que en Windows no hay `sudo -u postgres`:
  PG_SUPERUSER (scripts/.env, default "postgres" si falta o está vacía) y la contraseña,
  resuelta en este orden: argumento de línea de comando > PG_PASSWORD (scripts/.env)
  > interactivo (getpass).

Uso (argumento posicional, sin banderas):
- Sin argumentos: en Windows usa PG_PASSWORD (scripts/.env); si falta, la pide de
  forma interactiva (en Linux no aplica).
- 1 argumento: PG_PASSWORD, tiene prioridad sobre scripts/.env (solo efecto en Windows).
"""

UPDATE_ENV = True


# Variables de scripts/.env que necesita la rama remota (Linux/VPS) de este script.
# Se declaran acá, al lado del código que las usa, y se le pasan a maybe_dispatch_remote().
REMOTE_ENV_KEYS = {"VPS_USER", "SERVER_DIR", "DB_NAME", "GIT_REPO_URL"}
HBA_RULE_COMMENT = "# Acceso por túnel SSH para pruebas locales"
WIN_PG_VERSION = "17"
WIN_PG_INSTALL_DIR = Path(r"C:\Program Files\PostgreSQL") / WIN_PG_VERSION
WIN_PG_BIN_DIR = WIN_PG_INSTALL_DIR / "bin"
WIN_PG_DATA_DIR = WIN_PG_INSTALL_DIR / "data"

@dataclass(frozen=True)
class Config:
    db_name: str
    db_user: str
    db_user_password: str


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


# --- Linux (VPS): operaciones vía `sudo -u postgres` ---------------------------------------


def _run_checked(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        input=input_text,
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
    return result


def _psql_as_postgres(sql: str) -> None:
    args = ["sudo", "-n", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-d", "postgres"]
    _run_checked(args, input_text=sql)


def _psql_as_postgres_capture(sql: str) -> str:
    result = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-X",
            "-tA",
            "-q",
            "-d",
            "postgres",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló el comando (exit {result.returncode}).")
    return result.stdout


def _psql_as_postgres_db(db: str, sql: str) -> None:
    args = ["sudo", "-n", "-u", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-X", "-q", "-d", db]
    _run_checked(args, input_text=sql)


def _hba_file_path() -> str:
    path = _psql_as_postgres_capture("SHOW hba_file;").strip()
    if not path:
        raise SystemExit("[ERROR] No se pudo obtener la ruta de pg_hba.conf (SHOW hba_file).")
    return path


def _read_as_postgres(path: str) -> str:
    result = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "cat", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] No se pudo leer {path} (exit {result.returncode}). {result.stderr.strip()}")
    return result.stdout


def _append_as_postgres(path: str, text: str) -> None:
    result = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "tee", "-a", path],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] No se pudo escribir en {path} (exit {result.returncode}). {result.stderr.strip()}")


def _ensure_hba_rule(db_name: str, db_user: str) -> None:
    hba_path = _hba_file_path()
    content = _read_as_postgres(hba_path)

    for existing_line in content.splitlines():
        parts = existing_line.split()
        if (
            len(parts) >= 4
            and parts[0] == "host"
            and parts[1] == db_name
            and parts[2] == db_user
            and parts[3] == "127.0.0.1/32"
        ):
            print(f"[OK] Regla ya presente en {hba_path}, no se duplica.")
            return

    rule = f"host    {db_name}    {db_user}    127.0.0.1/32    scram-sha-256"
    _append_as_postgres(hba_path, f"\n{HBA_RULE_COMMENT}\n{rule}\n")
    print(f"[OK] Regla agregada a {hba_path}: {rule}")


def _reload_postgres() -> None:
    _psql_as_postgres("SELECT pg_reload_conf();\n")


def _postgres_port() -> str:
    port = _psql_as_postgres_capture("SHOW port;").strip()
    if not port or not port.isdigit():
        raise SystemExit("[ERROR] No se pudo obtener el puerto de Postgres (SHOW port).")
    return port


def _postgres_socket_dir() -> str:
    raw = _psql_as_postgres_capture("SHOW unix_socket_directories;").strip()
    dirs = [d.strip() for d in raw.split(",") if d.strip()]
    if not dirs:
        raise SystemExit(
            "[ERROR] No se pudo obtener el directorio del socket de Postgres "
            "(SHOW unix_socket_directories)."
        )
    return dirs[0]


def _configure_firewall(port: str) -> None:
    result = subprocess.run(
        ["sudo", "-n", "ufw", "deny", f"{port}/tcp"],
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
        raise SystemExit(f"[ERROR] Falló ufw (exit {result.returncode}).")
    print(f"[OK] UFW: bloqueado acceso externo a {port}/tcp (el túnel SSH usa loopback y no se ve afectado).")


def _run_local_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def apply_linux(cfg: Config) -> str:
    db_user_lit = _quote_literal(cfg.db_user)
    db_user_password_lit = _quote_literal(cfg.db_user_password)
    db_name_ident = _quote_ident(cfg.db_name)
    db_user_ident = _quote_ident(cfg.db_user)

    _psql_as_postgres(
        "\n".join(
            [
                "SET standard_conforming_strings = on;",
                "DO $$",
                "BEGIN",
                f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {db_user_lit}) THEN",
                f"    EXECUTE format('CREATE ROLE %I LOGIN', {db_user_lit});",
                "  END IF;",
                "END $$;",
                f"ALTER ROLE {db_user_ident} WITH PASSWORD {db_user_password_lit};",
                "",
            ]
        )
    )

    db_exists = _psql_as_postgres_capture(
        f"SELECT 1 FROM pg_database WHERE datname = {_quote_literal(cfg.db_name)} LIMIT 1;"
    ).strip() == "1"

    if db_exists:
        _psql_as_postgres(f"ALTER DATABASE {db_name_ident} OWNER TO {db_user_ident};\n")
    else:
        _psql_as_postgres(f"CREATE DATABASE {db_name_ident} OWNER {db_user_ident};\n")

    _psql_as_postgres(f"GRANT ALL PRIVILEGES ON DATABASE {db_name_ident} TO {db_user_ident};\n")
    _psql_as_postgres_db(cfg.db_name, f"GRANT ALL ON SCHEMA public TO {db_user_ident};\n")

    _ensure_hba_rule(cfg.db_name, cfg.db_user)
    _reload_postgres()
    _configure_firewall(_postgres_port())

    print("[OK] Bootstrap completado (Linux).")

    socket_dir = _postgres_socket_dir()
    return f"postgresql://{cfg.db_user}@/{cfg.db_name}?host={socket_dir}"


# --- Windows (desarrollo local): operaciones vía TCP con el superusuario --------------------


def _win_postgres_port() -> str:
    try:
        return windows_postgres_port(version=WIN_PG_VERSION)
    except (FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"[ERROR] {exc}")


def _psql_windows_argv(superuser: WindowsSuperuser, db: str, port: str) -> list[str]:
    psql_exe = str(WIN_PG_BIN_DIR / "psql.exe")
    return [
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
    ]


def _run_psql_windows(superuser: WindowsSuperuser, db: str, sql: str, *, port: str) -> None:
    env = {**os.environ, "PGPASSWORD": superuser.password}
    result = subprocess.run(
        _psql_windows_argv(superuser, db, port),
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


def _run_psql_windows_capture(superuser: WindowsSuperuser, db: str, sql: str, *, port: str) -> str:
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
            "-tA",
            "-q",
            "-d",
            db,
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.stderr.strip():
        print(result.stderr.rstrip("\n"))
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló el comando (exit {result.returncode}).")
    return result.stdout


def apply_windows(cfg: Config, superuser: WindowsSuperuser) -> str:
    port = _win_postgres_port()
    db_user_lit = _quote_literal(cfg.db_user)
    db_user_password_lit = _quote_literal(cfg.db_user_password)
    db_name_ident = _quote_ident(cfg.db_name)
    db_user_ident = _quote_ident(cfg.db_user)

    _run_psql_windows(
        superuser,
        "postgres",
        "\n".join(
            [
                "SET standard_conforming_strings = on;",
                "DO $$",
                "BEGIN",
                f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {db_user_lit}) THEN",
                f"    EXECUTE format('CREATE ROLE %I LOGIN', {db_user_lit});",
                "  END IF;",
                "END $$;",
                f"ALTER ROLE {db_user_ident} WITH PASSWORD {db_user_password_lit};",
                "",
            ]
        ),
        port=port,
    )

    db_exists = _run_psql_windows_capture(
        superuser,
        "postgres",
        f"SELECT 1 FROM pg_database WHERE datname = {_quote_literal(cfg.db_name)} LIMIT 1;",
        port=port,
    ).strip() == "1"

    if db_exists:
        _run_psql_windows(superuser, "postgres", f"ALTER DATABASE {db_name_ident} OWNER TO {db_user_ident};\n", port=port)
    else:
        _run_psql_windows(superuser, "postgres", f"CREATE DATABASE {db_name_ident} OWNER {db_user_ident};\n", port=port)

    _run_psql_windows(superuser, "postgres", f"GRANT ALL PRIVILEGES ON DATABASE {db_name_ident} TO {db_user_ident};\n", port=port)
    _run_psql_windows(superuser, cfg.db_name, f"GRANT ALL ON SCHEMA public TO {db_user_ident};\n", port=port)

    print("[OK] Bootstrap completado (Windows).")

    return f"postgresql://{cfg.db_user}:{cfg.db_user_password}@127.0.0.1:{port}/{cfg.db_name}"


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
    db_user_password = require_env("DB_PASSWORD")

    cfg = Config(
        db_name=_require_ident("DB_NAME", db_name),
        db_user=_require_ident("VPS_USER", vps_user),
        db_user_password=db_user_password,
    )

    os_key = detect_os()

    if os_key == "windows":
        superuser_name = optional_env("PG_SUPERUSER", "postgres")
        superuser_password = _require_password(
            f"SUPERUSER_PASSWORD ({superuser_name})",
            _parse_password_arg(sys.argv[1:])
        )
        superuser = WindowsSuperuser(name=superuser_name, password=superuser_password)
        database_url = apply_windows(cfg, superuser)
    else:
        database_url = apply_linux(cfg)

    if not UPDATE_ENV:
        print("[INFO] UPDATE_ENV = False: no se modifica server/.env.")
        return

    env_path = server_root / ".env"
    action = upsert_env_var(env_path, key="DATABASE_URL", value=database_url)
    print(f"[OK] DATABASE_URL {action} en {env_path}")

    if os_key != "windows":
        repo_name = repo_name_from_git_url(require_env("GIT_REPO_URL"))
        restart_systemd_service(repo_name, _run_local_shell)


if __name__ == "__main__":
    main()
