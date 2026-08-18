from __future__ import annotations

import os
import subprocess
import sys
import shutil

"""
Elimina todos los AVDs locales.

Flujo:
1) Obtiene emulator y avdmanager desde ANDROID_SDK_ROOT/ANDROID_HOME o desde el PATH.
2) Lista AVDs con emulator -list-avds.
3) Elimina cada AVD con avdmanager delete avd.
4) Imprime el resultado final.
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


def _resolve_tools() -> tuple[str, str]:
    os_key = _detect_os()
    sdk_root = _sdk_root_from_env()

    emulator_exe = "emulator.exe" if os_key == "windows" else "emulator"
    avdmanager_exe = "avdmanager.bat" if os_key == "windows" else "avdmanager"

    if sdk_root:
        emulator_path = os.path.join(sdk_root, "emulator", emulator_exe)
        avdmanager_path = os.path.join(sdk_root, "cmdline-tools", "latest", "bin", avdmanager_exe)

        missing: list[str] = []
        if not os.path.exists(emulator_path):
            missing.append(emulator_path)
        if not os.path.exists(avdmanager_path):
            missing.append(avdmanager_path)
        if missing:
            print("[ERROR] ANDROID_SDK_ROOT/ANDROID_HOME está definido pero faltan herramientas en la ruta esperada.")
            print(f"[ERROR] SDK root: {sdk_root}")
            for p in missing:
                print(f"[ERROR] Falta: {p}")
            raise SystemExit(1)

        return emulator_path, avdmanager_path

    emulator_found = shutil.which(emulator_exe)
    avdmanager_found = shutil.which(avdmanager_exe)
    if emulator_found and avdmanager_found:
        return emulator_found, avdmanager_found

    print("[ERROR] No se pudieron localizar emulator/avdmanager.")
    print("[ERROR] Define ANDROID_SDK_ROOT o ANDROID_HOME, o agrega emulator y avdmanager al PATH.")
    raise SystemExit(1)


def _get_avds(emulator_path: str) -> list[str]:
    result = _run([emulator_path, "-list-avds"], capture_output=True)
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
            _run([avdmanager_path, "delete", "avd", "--name", avd])

    print_header("LIMPIEZA DE AVDs COMPLETADA")


if __name__ == "__main__":
    main()
