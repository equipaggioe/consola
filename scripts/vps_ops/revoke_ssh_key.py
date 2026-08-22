from __future__ import annotations

import sys
from pathlib import Path

"""
Revoca una llave SSH del VPS (authorized_keys) y elimina los archivos locales de esa llave.

Flujo:
1) Calcula la raíz del repo (carpeta padre de scripts/).
2) Carga scripts/.env a variables de entorno.
3) Lee y valida VPS_IP, VPS_USER y VPS_KEY_NAME.
4) Localiza la llave privada y pública en ~/.ssh/.
5) Conecta al VPS y elimina la llave del authorized_keys.
6) Elimina los archivos locales de la llave.
7) Imprime el resultado y una advertencia.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import find_project_root, load_vps_config, require_env, run_ssh


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    ip, usuario, private_key = load_vps_config(repo_root)
    key_name = require_env("VPS_KEY_NAME")

    ssh_dir = Path.home() / ".ssh"
    public_key = ssh_dir / f"{key_name}.pub"

    print("[INFO] Eliminando llave pública del VPS...")

    if not public_key.is_file():
        print(f"[ERROR] No existe la llave pública local: {public_key}")
        raise SystemExit(1)

    public_key_text = public_key.read_text(encoding="utf-8").strip()
    if not public_key_text:
        print(f"[ERROR] La llave pública local está vacía: {public_key}")
        raise SystemExit(1)

    shell_key = public_key_text.replace("'", "'\"'\"'")
    remote_cmd = (
        f"key='{shell_key}'; "
        'f="$HOME/.ssh/authorized_keys"; '
        'tmp="$f.tmp.$$"; '
        'if [ -f "$f" ]; then '
        '  grep -vF -- "$key" "$f" > "$tmp"; s=$?; '
        '  if [ $s -eq 0 ] || [ $s -eq 1 ]; then '
        '    mv "$tmp" "$f" && chmod 600 "$f" && echo OK; '
        "  else "
        '    rm -f "$tmp"; exit $s; '
        "  fi; "
        "else "
        "  echo NOFILE; "
        "fi"
    )

    result = run_ssh(remote_cmd, identity_file=private_key, user=usuario, host=ip)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print("[ERROR] No se pudo eliminar la llave del VPS.")
        raise SystemExit(1)

    print("[OK] Llave pública eliminada del VPS.")
    print("[INFO] Eliminando llaves SSH locales...")

    for p in [private_key, public_key]:
        if p.exists():
            p.unlink()
            print(f"[OK] Eliminada: {p}")
        else:
            print(f"[WARN] No existe: {p}")

    print("[WARN] Si esta era la única llave de acceso, podrías perder acceso al VPS.")
    print("[OK] Proceso terminado.")


if __name__ == "__main__":
    main()
