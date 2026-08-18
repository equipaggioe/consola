from __future__ import annotations

import os
import subprocess
from pathlib import Path

"""
Instala una llave SSH en el VPS para poder entrar sin contraseña.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, ROOT_USER, VPS_USER y VPS_KEY_NAME.
4) Conecta al VPS como ROOT_USER.
5) Crea el usuario VPS_USER si no existe, lo añade al grupo sudo y configura sudo NOPASSWD para apt/apt-get/dpkg, systemctl, tee, journalctl, mkdir/chown/chmod.
6) Asegura ~/.ssh y genera la llave si no existe (localmente).
7) Agrega la llave pública a ~/.ssh/authorized_keys en el VPS para el VPS_USER.
8) Prueba el login por SSH usando la llave con el VPS_USER.
"""

SUDO_NOPASSWD_MODE = "all"  # all | specific | none


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


def _sh_single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)

    ip = _require_env("VPS_IP")
    root_usuario = _require_env("ROOT_USER")
    usuario = _require_env("VPS_USER")
    key_name = _require_env("VPS_KEY_NAME")

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
        sudoers_segment = (
            'sudoers="/etc/sudoers.d/vettore-$user"; '
            'rule_root="$user ALL=(root) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/bin/dpkg, /usr/bin/systemctl, /usr/bin/tee, /usr/bin/journalctl, /bin/mkdir, /bin/chown, /bin/chmod"; '
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

    subprocess.run(["ssh", f"{root_usuario}@{ip}", remote_cmd], check=True)

    print("[INFO] Probando login sin contraseña...")
    subprocess.run(["ssh", "-i", str(private_key), f"{usuario}@{ip}", "echo LOGIN SSH EXITOSO"], check=True)
    print("[OK] Listo.")


if __name__ == "__main__":
    main()
