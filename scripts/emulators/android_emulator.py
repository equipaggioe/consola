from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

"""
Código base para arrancar emuladores Android asegurando:
1) Existencia de herramientas del Android SDK.
2) Instalación de la system image.
3) Creación del AVD si no existe.
4) hw.keyboard=yes en config.ini del AVD.
5) Arranque del emulador con flags.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import print_header, resolve_android_tool, run_logged


@dataclass(frozen=True)
class AndroidSdkPaths:
    emulator: str
    adb: str
    sdkmanager: str
    avdmanager: str


def sdk_paths() -> AndroidSdkPaths:
    return AndroidSdkPaths(
        emulator=resolve_android_tool(sdk_subpath=("emulator",), windows_name="emulator.exe", other_name="emulator"),
        adb=resolve_android_tool(sdk_subpath=("platform-tools",), windows_name="adb.exe", other_name="adb"),
        sdkmanager=resolve_android_tool(
            sdk_subpath=("cmdline-tools", "latest", "bin"), windows_name="sdkmanager.bat", other_name="sdkmanager"
        ),
        avdmanager=resolve_android_tool(
            sdk_subpath=("cmdline-tools", "latest", "bin"), windows_name="avdmanager.bat", other_name="avdmanager"
        ),
    )


def _tool_paths(paths: AndroidSdkPaths) -> dict[str, str]:
    return {
        "sdkmanager": paths.sdkmanager,
        "avdmanager": paths.avdmanager,
        "emulator": paths.emulator,
        "adb": paths.adb,
    }


def _check_required_tools(paths: AndroidSdkPaths) -> None:
    for name, path in _tool_paths(paths).items():
        if not path or not os.path.exists(path):
            raise RuntimeError(f"No se encontró '{name}' en la ruta esperada: {path}.")
        print(f"[OK] {name}: {path}")


def system_image(*, api_level: str, target: str, abi: str) -> str:
    return f"system-images;android-{api_level};{target};{abi}"


def _system_image_installed(paths: AndroidSdkPaths, system_image_id: str) -> bool:
    result = run_logged([paths.sdkmanager, "--list_installed"], capture_output=True)
    return system_image_id in (result.stdout or "")


def _avd_exists(paths: AndroidSdkPaths, avd_name: str) -> bool:
    result = run_logged([paths.emulator, "-list-avds"], capture_output=True)
    avds = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return avd_name in avds


def _avd_home() -> str:
    avd_home = os.environ.get("ANDROID_AVD_HOME")
    if not avd_home:
        raise RuntimeError("La variable de entorno 'ANDROID_AVD_HOME' no está definida.")
    return avd_home


def _update_avd_config(*, avd_name: str) -> None:
    config_ini_path = os.path.join(_avd_home(), f"{avd_name}.avd", "config.ini")
    if not os.path.exists(config_ini_path):
        print(f"[ERROR] No se encontró config.ini para el AVD '{avd_name}' en: {config_ini_path}")
        return

    lines: list[str] = []
    found = False
    with open(config_ini_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("hw.keyboard="):
                lines.append("hw.keyboard=yes\n")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append("hw.keyboard=yes\n")
    with open(config_ini_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"[OK] Teclado de hardware habilitado para AVD '{avd_name}'.")


def run(
    *,
    avd_name: str,
    device: str,
    api_level: str,
    abi: str,
    target: str,
    flags: list[str] | None = None,
) -> None:
    paths = sdk_paths()
    system_image_id = system_image(api_level=api_level, target=target, abi=abi)
    emulator_flags = flags or [
        "-no-boot-anim",
        "-netdelay",
        "none",
        "-netspeed",
        "full",
    ]

    print_header("VALIDANDO HERRAMIENTAS ANDROID")
    try:
        _check_required_tools(paths)
    except RuntimeError as exc:
        print(f"\n[ERROR] {exc}")
        raise SystemExit(1) from exc

    print_header("VERIFICANDO SYSTEM IMAGE")
    if _system_image_installed(paths, system_image_id):
        print("[OK] Ya está instalada:")
        print(f"     {system_image_id}")
    else:
        print("[INFO] No está instalada.")
        print(f"[INFO] Instalando:\n       {system_image_id}")
        run_logged([paths.sdkmanager, system_image_id])

    print_header("VALIDANDO AVD")
    if _avd_exists(paths, avd_name):
        print(f"[INFO] El AVD '{avd_name}' ya existe.")
        _update_avd_config(avd_name=avd_name)
    else:
        print(f"[INFO] Creando AVD: {avd_name}")
        run_logged(
            [
                paths.avdmanager,
                "create",
                "avd",
                "--name",
                avd_name,
                "--package",
                system_image_id,
                "--device",
                device,
            ]
        )
        _update_avd_config(avd_name=avd_name)

    print_header("INICIANDO EMULADOR")
    cmd = [paths.emulator, "-avd", avd_name, *emulator_flags]
    print(f"[INFO] Iniciando emulador con AVD: {avd_name}")
    print(f"[INFO] Comando: {' '.join(cmd)}")
    run_logged(cmd)
    print_header("EMULADOR FINALIZADO")
