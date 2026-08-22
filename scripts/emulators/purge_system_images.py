from __future__ import annotations

import sys
from pathlib import Path

"""
Desinstala todas las system images instaladas.

Flujo:
1) Obtiene sdkmanager desde ANDROID_SDK_ROOT/ANDROID_HOME o desde el PATH.
2) Lista paquetes instalados con sdkmanager --list_installed.
3) Filtra los que empiezan con system-images;.
4) Desinstala cada uno con sdkmanager --uninstall.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import print_header, resolve_android_tool, run_logged


def _resolve_sdkmanager_path() -> str:
    return resolve_android_tool(
        sdk_subpath=("cmdline-tools", "latest", "bin"), windows_name="sdkmanager.bat", other_name="sdkmanager"
    )


def _get_system_images(sdkmanager_path: str) -> list[str]:
    result = run_logged([sdkmanager_path, "--list_installed"], capture_output=True)
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
            run_logged([sdkmanager_path, "--uninstall", image])

    print_header("LIMPIEZA DE SYSTEM IMAGES COMPLETADA")


if __name__ == "__main__":
    main()
