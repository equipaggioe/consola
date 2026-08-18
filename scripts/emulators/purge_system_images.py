from __future__ import annotations

import os
import subprocess
import sys
import shutil

"""
Desinstala todas las system images instaladas.

Flujo:
1) Obtiene sdkmanager desde ANDROID_SDK_ROOT/ANDROID_HOME o desde el PATH.
2) Lista paquetes instalados con sdkmanager --list_installed.
3) Filtra los que empiezan con system-images;.
4) Desinstala cada uno con sdkmanager --uninstall.
"""


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _run(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(cmd, check=True, text=True, capture_output=capture_output)


def _detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    print(f"[ERROR] Sistema operativo no soportado: {sys.platform}")
    raise SystemExit(1)


def _sdk_root_from_env() -> str | None:
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return None


def _resolve_sdkmanager_path() -> str:
    os_key = _detect_os()
    sdk_root = _sdk_root_from_env()

    if sdk_root:
        filename = "sdkmanager.bat" if os_key == "windows" else "sdkmanager"
        candidate = os.path.join(sdk_root, "cmdline-tools", "latest", "bin", filename)
        if os.path.exists(candidate):
            return candidate
        print("[ERROR] ANDROID_SDK_ROOT/ANDROID_HOME está definido pero no se encontró sdkmanager en la ruta esperada.")
        print(f"[ERROR] SDK root: {sdk_root}")
        print(f"[ERROR] Esperado: {candidate}")
        raise SystemExit(1)

    exe = "sdkmanager.bat" if os_key == "windows" else "sdkmanager"
    found = shutil.which(exe)
    if found:
        return found

    print("[ERROR] No se pudo localizar sdkmanager.")
    print("[ERROR] Define ANDROID_SDK_ROOT o ANDROID_HOME, o agrega sdkmanager al PATH.")
    raise SystemExit(1)


def _get_system_images(sdkmanager_path: str) -> list[str]:
    result = _run([sdkmanager_path, "--list_installed"], capture_output=True)
    images: list[str] = []
    for line in (result.stdout or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("system-images;"):
            images.append(stripped.split("|", 1)[0].strip())
    return images


def main() -> None:
    print_header("BORRANDO SYSTEM IMAGES")
    sdkmanager_path = _resolve_sdkmanager_path()
    images = _get_system_images(sdkmanager_path)
    if not images:
        print("No hay system images.")
    else:
        for image in images:
            print(f"\nDesinstalando: {image}")
            _run([sdkmanager_path, "--uninstall", image])

    print_header("LIMPIEZA DE SYSTEM IMAGES COMPLETADA")


if __name__ == "__main__":
    main()
