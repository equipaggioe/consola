from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _resolve_flutter_cmd() -> list[str]:
    candidates = ["flutter", "flutter.bat", "flutter.cmd", "flutter.exe"]
    resolved = ""
    for c in candidates:
        found = shutil.which(c)
        if found:
            resolved = found
            break

    if not resolved:
        print("[ERROR] No se encontró `flutter` en PATH.")
        raise SystemExit(1)

    lower = resolved.lower()
    if os.name == "nt" and (lower.endswith(".bat") or lower.endswith(".cmd")):
        return ["cmd.exe", "/c", resolved]
    return [resolved]


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


def _run_flutter_devices_machine(*, cwd: Path) -> list[dict]:
    flutter_cmd = _resolve_flutter_cmd()
    try:
        out = subprocess.check_output(
            [*flutter_cmd, "devices", "--machine"],
            cwd=str(cwd),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print("[ERROR] Falló `flutter devices --machine`.")
        print(exc.output)
        raise SystemExit(exc.returncode or 1) from exc

    try:
        decoded = json.loads(out)
    except json.JSONDecodeError:
        print("[ERROR] Respuesta inválida de `flutter devices --machine`.")
        print(out)
        raise SystemExit(1)

    if not isinstance(decoded, list):
        print("[ERROR] Respuesta inesperada de `flutter devices --machine` (se esperaba lista).")
        raise SystemExit(1)

    return [d for d in decoded if isinstance(d, dict)]


def _pick_android_emulator_id(devices: list[dict]) -> str:
    for d in devices:
        device_id = str(d.get("id") or "").strip()
        if not device_id:
            continue
        target_platform = str(d.get("targetPlatform") or "").strip().lower()
        is_emulator = bool(d.get("emulator"))
        if target_platform.startswith("android") and (is_emulator or device_id.startswith("emulator-")):
            return device_id
    return ""


def main() -> int:
    root = _repo_root()
    env_path = root / "scripts" / ".env"
    _load_env_file(env_path)

    api = _require_env("API_URL").rstrip("/")
    app_dir = _flutter_project_dir(root)
    flutter_cmd = _resolve_flutter_cmd()

    devices = _run_flutter_devices_machine(cwd=app_dir)
    device_id = _pick_android_emulator_id(devices)
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
