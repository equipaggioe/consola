from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

"""
Código base para arrancar emuladores Android asegurando:
1) Existencia de herramientas del Android SDK.
2) Instalación de la system image.
3) Creación del AVD si no existe.
4) hw.keyboard=yes en config.ini del AVD.
5) Arranque del emulador con flags.
"""


@dataclass(frozen=True)
class AndroidSdkPaths:
    android_home: str
    emulator: str
    adb: str
    sdkmanager: str
    avdmanager: str


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Falta variable de entorno: {name}")
    return value


def sdk_paths(*, android_home: str | None = None) -> AndroidSdkPaths:
    if android_home is None:
        android_home = (os.environ.get("ANDROID_SDK_ROOT") or "").strip() or (os.environ.get("ANDROID_HOME") or "").strip()
        if not android_home:
            raise RuntimeError("Falta ANDROID_SDK_ROOT o ANDROID_HOME en el entorno.")

    emulator = os.path.join(android_home, "emulator", "emulator.exe")
    platform_tools = os.path.join(android_home, "platform-tools")
    adb = os.path.join(platform_tools, "adb.exe")
    cmdline_tools = os.path.join(android_home, "cmdline-tools", "latest", "bin")
    sdkmanager = os.path.join(cmdline_tools, "sdkmanager.bat")
    avdmanager = os.path.join(cmdline_tools, "avdmanager.bat")
    return AndroidSdkPaths(
        android_home=android_home,
        emulator=emulator,
        adb=adb,
        sdkmanager=sdkmanager,
        avdmanager=avdmanager,
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


def _run(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(cmd, check=True, text=True, capture_output=capture_output)


def system_image(*, api_level: str, target: str, abi: str) -> str:
    return f"system-images;android-{api_level};{target};{abi}"


def _system_image_installed(paths: AndroidSdkPaths, system_image_id: str) -> bool:
    result = _run([paths.sdkmanager, "--list_installed"], capture_output=True)
    return system_image_id in (result.stdout or "")


def _avd_exists(paths: AndroidSdkPaths, avd_name: str) -> bool:
    result = _run([paths.emulator, "-list-avds"], capture_output=True)
    avds = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return avd_name in avds


def _update_avd_config(*, avd_name: str) -> None:
    userprofile = os.environ.get("USERPROFILE") or ""
    config_ini_path = os.path.join(userprofile, ".android", "avd", f"{avd_name}.avd", "config.ini")
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
    android_home: str | None = None,
) -> None:
    paths = sdk_paths(android_home=android_home)
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
        _run([paths.sdkmanager, system_image_id])

    print_header("VALIDANDO AVD")
    if _avd_exists(paths, avd_name):
        print(f"[INFO] El AVD '{avd_name}' ya existe.")
        _update_avd_config(avd_name=avd_name)
    else:
        print(f"[INFO] Creando AVD: {avd_name}")
        _run(
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
    _run(cmd)
    print_header("EMULADOR FINALIZADO")
