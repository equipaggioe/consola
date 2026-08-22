from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    find_project_root,
    load_env_file,
    pick_android_emulator_id,
    require_env,
    resolve_flutter_cmd,
    run_flutter_devices_machine,
)

"""
Flujo:

1) Define el directorio del proyecto Flutter por variable en este archivo.
2) Carga variables desde scripts/.env a os.environ.
3) Lee API_URL desde os.environ y lo usa como API_BASE_URL (Dart define).
4) Valida pubspec.yaml en el directorio del proyecto Flutter.
5) Detecta el emulador Android activo usando `flutter devices --machine`.
6) Ejecuta `flutter run` en modo debug sobre el emulador, pasando API_BASE_URL por `--dart-define`.
5) Deja la sesión interactiva (hot reload/hot restart) en la terminal actual.
6) Propaga el código de salida del proceso de Flutter.
"""

FLUTTER_PROJECT_DIR = "app"


def _flutter_project_dir(repo_root: Path) -> Path:
    raw = (FLUTTER_PROJECT_DIR or "").strip()
    if not raw:
        print("[ERROR] FLUTTER_PROJECT_DIR está vacío.")
        raise SystemExit(1)

    candidate = Path(raw)
    app_dir = candidate if candidate.is_absolute() else (repo_root / candidate)
    pubspec = app_dir / "pubspec.yaml"
    if not pubspec.exists():
        print(f"[ERROR] No se encontró pubspec.yaml en: {pubspec}")
        raise SystemExit(1)
    return app_dir


def main() -> int:
    root = find_project_root(Path(__file__).resolve().parent)
    env_path = root / "scripts" / ".env"
    load_env_file(env_path)

    api = require_env("API_URL").rstrip("/")
    app_dir = _flutter_project_dir(root)
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

    cmd = [
        *flutter_cmd,
        "run",
        "-d",
        device_id,
        f"--dart-define=API_BASE_URL={api}",
    ]

    print("[INFO] Iniciando Flutter en modo debug...")
    print(f"[INFO] Proyecto: {app_dir}")
    print(f"[INFO] Dispositivo: {device_id}")
    print(f"[INFO] API_BASE_URL: {api}")
    print(f"[INFO] Comando: {' '.join(cmd)}")

    return subprocess.call(cmd, cwd=str(app_dir))


if __name__ == "__main__":
    raise SystemExit(main())
