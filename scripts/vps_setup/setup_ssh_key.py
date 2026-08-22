from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_ip_user, optional_env, require_env

"""
Instala una llave SSH en el VPS para poder entrar sin contraseña.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env, VPS_IP y VPS_USER (default: nombre del repo si no está definida).
3) Lee y valida ROOT_USER y VPS_KEY_NAME. Si ROOT_PASSWORD está definida
   en el .env, se usa con sshpass para no pedir la contraseña en línea; si no está, SSH
   la pide en línea como siempre.
4) Conecta al VPS como ROOT_USER.
5) Crea el usuario VPS_USER si no existe, lo añade al grupo sudo y configura sudo NOPASSWD según
   SUDO_NOPASSWD_MODE ("all" = todo; "specific" = solo los comandos listados en
   SUDO_SPECIFIC_COMMANDS, más psql sobre postgres; "none" = no configura NOPASSWD).
6) Asegura ~/.ssh y genera la llave si no existe (localmente).
7) Agrega la llave pública a ~/.ssh/authorized_keys en el VPS para el VPS_USER.
8) Prueba el login por SSH usando la llave con el VPS_USER.
"""

SUDO_NOPASSWD_MODE = "all"  # all | specific | none
SUDO_SPECIFIC_COMMANDS = (
    "/usr/bin/apt-get",     # instalar/actualizar paquetes
    "/usr/bin/apt",         # instalar/actualizar paquetes (interfaz alternativa)
    "/usr/bin/dpkg",        # instalar/consultar paquetes .deb
    "/usr/bin/systemctl",   # iniciar/detener/reiniciar servicios
    "/usr/bin/tee",         # escribir archivos como root (ej. configuraciones)
    "/usr/bin/journalctl",  # leer logs del sistema
    "/bin/mkdir",           # crear carpetas
    "/bin/chown",           # cambiar dueño de archivos/carpetas
    "/bin/chmod",           # cambiar permisos de archivos/carpetas
)


def _sh_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    ip, usuario = load_vps_ip_user(repo_root)

    root_usuario = require_env("ROOT_USER")
    root_password = optional_env("ROOT_PASSWORD", "")
    key_name = require_env("VPS_KEY_NAME")

    sudo_mode = (SUDO_NOPASSWD_MODE or "").strip().lower()
    if sudo_mode not in {"all", "specific", "none", "ninguno"}:
        print('[ERROR] Invalid SUDO_NOPASSWD_MODE. Use: "all" | "specific" | "none"')
        raise SystemExit(1)

    if sudo_mode in {"none", "ninguno"}:
        sudoers_segment = "echo SUDOERS_SKIPPED; "
    elif sudo_mode == "all":
        sudoers_segment = (
            'sudoers="/etc/sudoers.d/vettore-$user"; '
            'rule_all="$user ALL=(ALL) NOPASSWD: ALL"; '
            'printf "%s\\n" "$rule_all" > "$sudoers" && '
            'chmod 440 "$sudoers" && '
            'visudo -cf "$sudoers" && '
            "echo SUDOERS_OK; "
        )
    else:
        comandos_especificos = ", ".join(SUDO_SPECIFIC_COMMANDS)
        sudoers_segment = (
            'sudoers="/etc/sudoers.d/vettore-$user"; '
            f'rule_root="$user ALL=(root) NOPASSWD: {comandos_especificos}"; '
            'rule_postgres="$user ALL=(postgres) NOPASSWD: /usr/bin/psql"; '
            'printf "%s\\n%s\\n" "$rule_root" "$rule_postgres" > "$sudoers" && '
            'chmod 440 "$sudoers" && '
            'visudo -cf "$sudoers" && '
            "echo SUDOERS_OK; "
        )

    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)

    private_key = ssh_dir / key_name
    public_key = ssh_dir / f"{key_name}.pub"

    if not private_key.exists():
        print("[INFO] Generando llave SSH...")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(private_key), "-N", ""], check=True)
    else:
        print("[INFO] La llave ya existe.")

    if not public_key.is_file():
        print(f"[ERROR] No existe la llave pública: {public_key}")
        raise SystemExit(1)

    public_key_text = public_key.read_text(encoding="utf-8").strip()
    if not public_key_text:
        print(f"[ERROR] La llave pública está vacía: {public_key}")
        raise SystemExit(1)

    print("[INFO] Copiando llave al VPS...")

    if root_password:
        sshpass_bin = shutil.which("sshpass")
        if not sshpass_bin:
            print("[ERROR] ROOT_PASSWORD está definida pero no se encontró 'sshpass' instalado.")
            print("[ERROR] Instálalo (ej. apt install sshpass) o quita ROOT_PASSWORD del .env.")
            raise SystemExit(1)
        ssh_prefix = [sshpass_bin, "-p", root_password]
        print("[INFO] Usando la contraseña de ROOT_PASSWORD (no se pedirá en línea).")
    else:
        ssh_prefix = []
        print("[INFO] Te pedirá la contraseña una sola vez (usuario root).")

    remote_cmd = (
        f"user={_sh_single_quote(usuario)}; "
        f"key={_sh_single_quote(public_key_text)}; "
        'if id -u "$user" >/dev/null 2>&1; then '
        '  echo USER_EXISTS; '
        "else "
        '  useradd -m -s /bin/bash "$user" && echo USER_CREATED; '
        "fi; "
        'if getent group sudo >/dev/null 2>&1; then '
        '  usermod -aG sudo "$user" && echo SUDO_OK; '
        "else "
        '  echo SUDO_GROUP_MISSING; '
        "fi; "
        f"{sudoers_segment}"
        'home="$(getent passwd "$user" | cut -d: -f6)"; '
        'if [ -z "$home" ]; then echo NO_HOME; exit 1; fi; '
        'mkdir -p "$home/.ssh" && '
        'chmod 700 "$home/.ssh" && '
        'auth="$home/.ssh/authorized_keys"; '
        'if [ -f "$auth" ] && grep -qxF -- "$key" "$auth" >/dev/null 2>&1; then '
        '  echo KEY_ALREADY_PRESENT; '
        "else "
        '  printf "%s\\n" "$key" >> "$auth" && echo KEY_INSTALLED; '
        "fi; "
        'chmod 600 "$auth" && '
        'chown -R "$user:$user" "$home/.ssh" && '
        "echo SSH_OK"
    )

    ssh_opts = ["-o", "StrictHostKeyChecking=no"]

    subprocess.run([*ssh_prefix, "ssh", *ssh_opts, f"{root_usuario}@{ip}", remote_cmd], check=True)

    print("[INFO] Probando login sin contraseña...")
    subprocess.run(
        ["ssh", *ssh_opts, "-i", str(private_key), f"{usuario}@{ip}", "echo LOGIN SSH EXITOSO"],
        check=True,
    )
    print("[OK] Listo.")


if __name__ == "__main__":
    main()
