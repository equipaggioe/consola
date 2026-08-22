from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    find_project_root,
    load_env_file,
    pick_android_emulator_id,
    require_env,
    resolve_flet_cmd,
    resolve_flutter_cmd,
    run_flutter_devices_machine,
)


"""
Flujo:

1) Define el directorio del proyecto Flet por variable en este archivo.
2) Carga variables desde scripts/.env a os.environ.
3) Lee API_URL desde os.environ y lo expone como API_BASE_URL en el entorno del proceso hijo
   (Flet no tiene un mecanismo equivalente a --dart-define de Flutter para 'flet debug';
   la app debe leerlo con os.getenv("API_BASE_URL")).
4) Valida pyproject.toml en el directorio del proyecto Flet.
5) Según RUN_TARGET:
   - "emulator": detecta el emulador Android activo usando `flutter devices --machine`,
     igual que run_flutter.py (el comando `flet devices` no expone un modo JSON/
     machine-readable propio: internamente llama a `flutter devices` sin --machine y
     parsea texto para mostrar una tabla, así que se usa directamente el Flutter
     subyacente para detectar), y ejecuta `flet debug android --device-id <id> -v`, que
     empaqueta e instala la app en el dispositivo/emulador (no es hot-reload streaming;
     es un build+install, distinto al `flutter run` de Flutter).
   - "python": ejecuta `flet run` directo, que corre la app como ventana nativa de
     escritorio en esta misma máquina (sin Android ni emulador), con hot reload.
6) Propaga el código de salida del proceso de Flet.
"""

FLET_PROJECT_DIR = "app"
RUN_TARGET = "emulator"  # emulator | python


def _flet_app_dir(repo_root: Path) -> Path:
    raw = (FLET_PROJECT_DIR or "").strip()
    if not raw:
        print("[ERROR] FLET_PROJECT_DIR está vacío.")
        raise SystemExit(1)

    candidate = Path(raw)
    app_dir = candidate if candidate.is_absolute() else (repo_root / candidate)
    pyproject = app_dir / "pyproject.toml"
    if not pyproject.exists():
        print(f"[ERROR] No se encontró pyproject.toml en: {pyproject}")
        raise SystemExit(1)
    return app_dir


def main() -> int:
    root = find_project_root(Path(__file__).resolve().parent)
    env_path = root / "scripts" / ".env"
    load_env_file(env_path)

    api = require_env("API_URL").rstrip("/")
    app_dir = _flet_app_dir(root)

    run_target = RUN_TARGET.strip().lower()
    if run_target not in ("emulator", "python"):
        raise ValueError(f"RUN_TARGET inválido: {RUN_TARGET!r}. Usa: emulator | python")

    try:
        flet_cmd = resolve_flet_cmd()
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    if run_target == "emulator":
        try:
            flutter_cmd = resolve_flutter_cmd()
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}")
            return 1

        devices = run_flutter_devices_machine(cwd=app_dir, flutter_cmd=flutter_cmd)
        device_id = pick_android_emulator_id(devices)
        if not device_id:
            print("[ERROR] No se detectó un emulador Android activo.")
            print("[INFO] Asegúrate de iniciar el emulador y vuelve a correr este script.")
            return 1

        cmd = [*flet_cmd, "debug", "android", "--device-id", device_id, "-v"]
        print("[INFO] Iniciando Flet en modo debug (emulador Android)...")
        print(f"[INFO] Dispositivo: {device_id}")
    else:
        cmd = [*flet_cmd, "run"]
        print("[INFO] Iniciando Flet como aplicación de escritorio (Python nativo)...")

    child_env = os.environ.copy()
    child_env["API_BASE_URL"] = api

    print(f"[INFO] Proyecto: {app_dir}")
    print(f"[INFO] API_BASE_URL: {api}")
    print(f"[INFO] Comando: {' '.join(cmd)}")

    return subprocess.call(cmd, cwd=str(app_dir), env=child_env)


if __name__ == "__main__":
    raise SystemExit(main())
