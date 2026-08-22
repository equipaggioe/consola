from __future__ import annotations

import sys
from pathlib import Path

"""
Elimina todos los AVDs locales.

Flujo:
1) Obtiene emulator y avdmanager desde ANDROID_SDK_ROOT/ANDROID_HOME o desde el PATH.
2) Lista AVDs con emulator -list-avds.
3) Elimina cada AVD con avdmanager delete avd.
4) Imprime el resultado final.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import print_header, resolve_android_tool, run_logged


def _resolve_tools() -> tuple[str, str]:
    emulator_path = resolve_android_tool(
        sdk_subpath=("emulator",), windows_name="emulator.exe", other_name="emulator"
    )
    avdmanager_path = resolve_android_tool(
        sdk_subpath=("cmdline-tools", "latest", "bin"), windows_name="avdmanager.bat", other_name="avdmanager"
    )
    return emulator_path, avdmanager_path


def _get_avds(emulator_path: str) -> list[str]:
    result = run_logged([emulator_path, "-list-avds"], capture_output=True)
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def main() -> None:
    print_header("BORRANDO AVDs")
    emulator_path, avdmanager_path = _resolve_tools()
    avds = _get_avds(emulator_path)
    if not avds:
        print("No hay AVDs.")
    else:
        for avd in avds:
            print(f"\nEliminando AVD: {avd}")
            run_logged([avdmanager_path, "delete", "avd", "--name", avd])

    print_header("LIMPIEZA DE AVDs COMPLETADA")


if __name__ == "__main__":
    main()
