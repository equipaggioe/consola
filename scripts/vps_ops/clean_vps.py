from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

"""
Deja el VPS lo más cerca posible de "recién formateado", sin asumir qué se corrió antes
ni cuántas veces: cada paso primero detecta si el recurso existe y solo actúa si lo
encuentra. Así funciona igual si corriste bootstrap_vps.py completo, a medias, varias
veces, o nunca.

Esto NO es una garantía absoluta de "SO recién instalado": cambios de `apt-get upgrade`
al sistema base, red o kernel no son rastreables ni reversibles por este script. Para
esa garantía total, la única opción real es reinstalar el sistema operativo desde el
panel del proveedor del VPS.

Pasos, cada uno controlado por STEPS más abajo (todos detectan antes de actuar):
1) remove_systemd_service: si existe /etc/systemd/system/{repo_name}.service, lo para,
   deshabilita y borra.
2) drop_database: si existen la base de datos / el rol de la app, los borra; si existe
   la regla en pg_hba.conf o la regla de ufw sobre el puerto de Postgres, las revierte.
   Se salta entero si postgres no está instalado en el VPS.
3) remove_deployed_repo: si existe el directorio del repo clonado (VPS_DEPLOY_DIR), lo borra.
4) revoke_github_key: si hay GITHUB_TOKEN configurado y existe una llave en GitHub con
   título GITHUB_KEY_TITLE, la borra; si existe el par de llaves en el VPS, lo borra.
5) uninstall_packages: purga los paquetes de PACKAGES_TO_REMOVE que sigan instalados
   (se corre antes de remove_vps_user, porque necesita el sudo del usuario de la app).
6) remove_vps_user: si existe el usuario del sistema, lo elimina (conecta como ROOT_USER,
   no como el usuario que se borra). Va al final porque los pasos anteriores dependen de
   su sudo.

Variables de configuración (edita esta constante):
- STEPS: qué pasos correr. Pon en False el que no quieras ejecutar.
- PACKAGES_TO_REMOVE: paquetes apt a purgar si están instalados (ver install_base_software.py).

Variables requeridas en scripts/.env (local):
- VPS_IP, VPS_USER, VPS_KEY_NAME, VPS_DEPLOY_DIR, GIT_REPO_URL, SERVER_DIR, DB_NAME
- ROOT_USER (para remove_vps_user); ROOT_PASSWORD opcional (si falta, ssh la pide en línea)
- GITHUB_KEY_TITLE (para revoke_github_key); GITHUB_TOKEN opcional (si falta, se salta
  solo la parte de GitHub y se limpia igual la llave local)
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    find_project_root,
    force_env_vars,
    github_api_request,
    load_vps_config,
    optional_env,
    print_header,
    repo_name_from_git_url,
    require_env,
    run_ssh,
    run_ssh_checked,
)

STEPS: dict[str, bool] = {
    "remove_systemd_service": True,
    "drop_database": True,
    "remove_deployed_repo": True,
    "revoke_github_key": True,
    "uninstall_packages": True,
    "remove_vps_user": True,
}

PACKAGES_TO_REMOVE = (
    "python3 python3-venv python3-pip "
    "git "
    "postgresql postgresql-contrib "
    "postgis postgresql-postgis-scripts "
    "caddy "
    "redis-server "
    "curl htop"
)


def _print_result(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())


def remove_systemd_service(*, identity_file: Path, user: str, host: str, repo_name: str) -> None:
    print_header(f"Servicio systemd: {repo_name}")
    exists = run_ssh_checked(
        f'[ -f "/etc/systemd/system/{repo_name}.service" ] && echo YES || echo NO',
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if exists != "YES":
        print("[OK] No existe; nada que limpiar.")
        return

    cmd = (
        f"sudo -n systemctl stop {repo_name} 2>/dev/null; "
        f"sudo -n systemctl disable {repo_name} 2>/dev/null; "
        f"sudo -n rm -f /etc/systemd/system/{repo_name}.service; "
        "sudo -n systemctl daemon-reload; "
        "echo OK"
    )
    _print_result(run_ssh(cmd, identity_file=identity_file, user=user, host=host))


def drop_database(*, repo_root: Path, identity_file: Path, user: str, host: str, db_name: str, db_user: str) -> None:
    print_header(f"Base de datos '{db_name}' / rol '{db_user}'")

    has_postgres = run_ssh_checked(
        "command -v psql >/dev/null 2>&1 && echo YES || echo NO",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if has_postgres != "YES":
        print("[OK] Postgres no está instalado en el VPS; nada que limpiar.")
        return

    db_exists = run_ssh_checked(
        f"sudo -n -u postgres psql -tAc \"SELECT 1 FROM pg_database WHERE datname = '{db_name}';\"",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip() == "1"
    role_exists = run_ssh_checked(
        f"sudo -n -u postgres psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname = '{db_user}';\"",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip() == "1"

    if db_exists or role_exists:
        print("[INFO] Corriendo scripts/database/teardown_db.py...")
        force_env_vars({"RUN_REMOTE": "true"})
        result = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "database" / "teardown_db.py")],
        )
        if result.returncode != 0:
            print(f"[ERROR] teardown_db.py falló (exit {result.returncode}).")
    else:
        print("[OK] Ni la base ni el rol existen; nada que borrar.")

    hba_path = run_ssh_checked(
        "sudo -n -u postgres psql -tAc 'SHOW hba_file;'",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    rule = f"host    {db_name}    {db_user}    127.0.0.1/32    scram-sha-256"
    if hba_path:
        rule_present = run_ssh_checked(
            f"sudo -n grep -qxF '{rule}' {hba_path} && echo YES || echo NO",
            identity_file=identity_file,
            user=user,
            host=host,
        ).strip()
        if rule_present == "YES":
            print("[INFO] Quitando regla de pg_hba.conf...")
            cleanup_cmd = (
                f"sudo -n cp {hba_path} {hba_path}.bak-clean && "
                f"sudo -n sed -i "
                f"-e '/^# Acceso por túnel SSH para pruebas locales$/d' "
                f"-e '\\|^{rule}$|d' "
                f"{hba_path} && "
                "sudo -n -u postgres psql -c 'SELECT pg_reload_conf();'"
            )
            _print_result(run_ssh(cleanup_cmd, identity_file=identity_file, user=user, host=host))
        else:
            print("[OK] La regla de pg_hba.conf no está presente.")

    port = run_ssh_checked(
        "sudo -n -u postgres psql -tAc 'SHOW port;'",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if port.isdigit():
        ufw_present = run_ssh_checked(
            f"sudo -n ufw status | grep -q '{port}/tcp.*DENY' && echo YES || echo NO",
            identity_file=identity_file,
            user=user,
            host=host,
        ).strip()
        if ufw_present == "YES":
            print("[INFO] Quitando regla de ufw...")
            _print_result(
                run_ssh(f"sudo -n ufw delete deny {port}/tcp", identity_file=identity_file, user=user, host=host)
            )
        else:
            print("[OK] La regla de ufw no está presente.")


def remove_deployed_repo(*, identity_file: Path, user: str, host: str, remote_repo_path: str) -> None:
    print_header(f"Repo desplegado: {remote_repo_path}")
    exists = run_ssh_checked(
        f'[ -d "{remote_repo_path}" ] && echo YES || echo NO',
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if exists != "YES":
        print("[OK] No existe; nada que limpiar.")
        return
    _print_result(
        run_ssh(f'sudo -n rm -rf "{remote_repo_path}"', identity_file=identity_file, user=user, host=host)
    )


def revoke_github_key(*, identity_file: Path, user: str, host: str) -> None:
    print_header("Llave SSH de GitHub")
    github_token = optional_env("GITHUB_TOKEN", "")
    key_title = optional_env("GITHUB_KEY_TITLE", "")

    if github_token and key_title:
        status, payload = github_api_request("GET", "https://api.github.com/user/keys", token=github_token)
        if status != 200 or not isinstance(payload, list):
            print(f"[ERROR] No se pudo listar llaves de GitHub (status {status}): {payload}")
        else:
            match = next((k for k in payload if isinstance(k, dict) and k.get("title") == key_title), None)
            if match is None:
                print(f"[OK] No hay ninguna llave en GitHub con título '{key_title}'.")
            else:
                del_status, del_payload = github_api_request(
                    "DELETE", f"https://api.github.com/user/keys/{match['id']}", token=github_token
                )
                if del_status == 204:
                    print(f"[OK] Llave '{key_title}' eliminada de GitHub.")
                else:
                    print(f"[ERROR] No se pudo eliminar la llave (status {del_status}): {del_payload}")
    else:
        print("[OK] GITHUB_TOKEN/GITHUB_KEY_TITLE no configurados; se salta la parte de GitHub.")

    key_exists = run_ssh_checked(
        "[ -f ~/.ssh/id_ed25519 ] && echo YES || echo NO",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if key_exists == "YES":
        _print_result(
            run_ssh(
                "rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub",
                identity_file=identity_file,
                user=user,
                host=host,
            )
        )
    else:
        print("[OK] No hay llave local en el VPS (~/.ssh/id_ed25519); nada que borrar.")


def uninstall_packages(*, identity_file: Path, user: str, host: str) -> None:
    print_header("Paquetes apt")
    installed = run_ssh_checked(
        f"dpkg-query -W -f='${{Package}} ' {PACKAGES_TO_REMOVE} 2>/dev/null || true",
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if not installed:
        print("[OK] Ninguno de los paquetes conocidos está instalado.")
        return

    print(f"[INFO] Instalados: {installed}")
    cmd = (
        f"sudo -n apt-get -y purge {installed}; "
        "sudo -n apt-get -y autoremove; "
        "sudo -n apt-get -y autoclean; "
        "echo OK"
    )
    _print_result(run_ssh(cmd, identity_file=identity_file, user=user, host=host))


def remove_vps_user(*, host: str, vps_user: str) -> None:
    print_header(f"Usuario del sistema: {vps_user}")
    root_user = require_env("ROOT_USER")
    root_password = optional_env("ROOT_PASSWORD", "")
    ssh_opts = ["-o", "StrictHostKeyChecking=no"]

    def _run(remote_cmd: str) -> subprocess.CompletedProcess[str]:
        if root_password:
            sshpass_bin = shutil.which("sshpass")
            if not sshpass_bin:
                print("[ERROR] ROOT_PASSWORD está definida pero no se encontró 'sshpass' instalado.")
                raise SystemExit(1)
            cmd = [sshpass_bin, "-p", root_password, "ssh", *ssh_opts, f"{root_user}@{host}", remote_cmd]
        else:
            cmd = ["ssh", *ssh_opts, f"{root_user}@{host}", remote_cmd]
        return subprocess.run(cmd, capture_output=True, text=True)

    exists = _run(f"id -u {vps_user} >/dev/null 2>&1 && echo YES || echo NO")
    if exists.stdout.strip() != "YES":
        print("[OK] El usuario no existe; nada que limpiar.")
        return

    remote_cmd = (
        f"pkill -u {vps_user} 2>/dev/null; "
        "sleep 1; "
        f"userdel -r {vps_user} 2>&1 || true; "
        f"rm -f /etc/sudoers.d/vettore-{vps_user}; "
        "echo OK"
    )
    _print_result(_run(remote_cmd))


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    git_repo_url = require_env("GIT_REPO_URL")
    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    db_name = optional_env("DB_NAME", f"{vps_user}_db")

    repo_name = repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{vps_deploy_dir.rstrip('/')}/{repo_name}"

    if STEPS.get("remove_systemd_service"):
        remove_systemd_service(identity_file=identity_file, user=vps_user, host=vps_ip, repo_name=repo_name)

    if STEPS.get("drop_database"):
        drop_database(
            repo_root=repo_root, identity_file=identity_file, user=vps_user, host=vps_ip,
            db_name=db_name, db_user=vps_user,
        )

    if STEPS.get("remove_deployed_repo"):
        remove_deployed_repo(identity_file=identity_file, user=vps_user, host=vps_ip, remote_repo_path=remote_repo_path)

    if STEPS.get("revoke_github_key"):
        revoke_github_key(identity_file=identity_file, user=vps_user, host=vps_ip)

    if STEPS.get("uninstall_packages"):
        uninstall_packages(identity_file=identity_file, user=vps_user, host=vps_ip)

    if STEPS.get("remove_vps_user"):
        remove_vps_user(host=vps_ip, vps_user=vps_user)

    print("\n[OK] Limpieza completada.")


if __name__ == "__main__":
    main()
