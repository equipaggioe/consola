from __future__ import annotations

import sys
from pathlib import Path

"""
Se conecta al VPS
Genera SSH key en el VPS
Lee la llave pública
La registra automáticamente en GitHub
Prueba conexión SSH GitHub

Token GitHub (classic). Permisos necesarios:
- admin:public_key
- repo (opcional)
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, github_api_request, load_vps_config, require_env, run_ssh, run_ssh_checked


def main() -> None:
    vps_ip, vps_user, identity_file = load_vps_config(find_project_root(Path(__file__).resolve().parent))

    github_token = require_env("GITHUB_TOKEN")
    key_title = require_env("GITHUB_KEY_TITLE")

    print("[INFO] Verificando llave SSH en VPS...")
    check_key = run_ssh(
        "if [ -f ~/.ssh/id_ed25519.pub ]; then echo EXISTS; else echo MISSING; fi",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
    )
    if check_key.returncode != 0:
        print(f"[ERROR] No se pudo conectar al VPS: {check_key.stderr.strip()}")
        raise SystemExit(1)

    if "EXISTS" not in check_key.stdout:
        print("[INFO] Generando llave SSH en VPS...")
        try:
            run_ssh_checked(
                'mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""',
                identity_file=identity_file,
                user=vps_user,
                host=vps_ip,
            )
        except RuntimeError as exc:
            print(f"[ERROR] No se pudo generar la llave en el VPS: {exc}")
            raise SystemExit(1)
    else:
        print("[OK] La llave ya existe.")

    print("[INFO] Leyendo llave pública...")
    try:
        public_key = run_ssh_checked(
            "cat ~/.ssh/id_ed25519.pub", identity_file=identity_file, user=vps_user, host=vps_ip
        )
    except RuntimeError as exc:
        print(f"[ERROR] No se pudo leer la llave pública del VPS: {exc}")
        raise SystemExit(1)

    if not public_key:
        print("[ERROR] La llave pública del VPS está vacía.")
        raise SystemExit(1)

    print("[INFO] Registrando llave en GitHub...")
    status, payload = github_api_request(
        "POST",
        "https://api.github.com/user/keys",
        token=github_token,
        body={"title": key_title, "key": public_key},
    )
    if status == 201:
        print("[OK] Llave registrada correctamente.")
    elif status == 422:
        print("[OK] La llave ya existe en GitHub.")
    else:
        print(f"[ERROR] No se pudo registrar la llave en GitHub (status {status}): {payload}")
        raise SystemExit(1)

    print("[INFO] Probando conexión GitHub...")
    test_result = run_ssh(
        "ssh -o StrictHostKeyChecking=no -T git@github.com || true",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
    )
    print(test_result.stdout)
    print(test_result.stderr)

    print("\n[OK] SETUP SSH GITHUB COMPLETADO")


if __name__ == "__main__":
    main()
