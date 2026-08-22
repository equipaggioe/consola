from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import hashlib
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import detect_os, run_logged


"""
Instala Android SDK (cmdline-tools latest, platform-tools, emulator) y configura entorno.

Flujo:
1) Detecta sistema operativo.
2) Define SDK_ROOT.
3) Resuelve el ZIP real de cmdline-tools (latest) desde la página oficial y valida SHA-1.
4) Descarga el ZIP y lo descomprime en <SDK>/cmdline-tools/latest.
5) Valida que exista sdkmanager.
6) Acepta licencias e instala solo lo que falte (platform-tools, emulator, build-tools, platform).
7) Instala/valida hypervisor según OS.
8) Limpia PATH de rutas anteriores de Android SDK.
9) Configura ANDROID_HOME/ANDROID_SDK_ROOT y agrega la nueva ruta de Android SDK al PATH.
"""

SDK_ROOT = r"D:\Android"
AVD_HOME_DIR = "avd"
BUILD_TOOLS_VERSION = "36.0.0"
PLATFORM_API_LEVEL = "36"

ANDROID_STUDIO_DOWNLOADS_URL = "https://developer.android.com/studio#command-line-tools-only"
ANDROID_REPOSITORY_URL = "https://dl.google.com/android/repository/"


def _default_sdk_root(os_key: str) -> Path:
    return Path(SDK_ROOT)


def _ensure_java() -> None:
    try:
        run_logged(["java", "-version"], check=False, capture_output=True)
    except FileNotFoundError:
        print("[ERROR] No se encontró Java (java). sdkmanager requiere Java.")
        raise SystemExit(1)


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def _resolve_cmdline_tools_release(os_key: str) -> tuple[str, str]:
    html = _fetch_text(ANDROID_STUDIO_DOWNLOADS_URL)

    if os_key == "windows":
        filename_re = r"commandlinetools-win-\d+_latest\.zip"
    elif os_key == "linux":
        filename_re = r"commandlinetools-linux-\d+_latest\.zip"
    else:
        print(f"[ERROR] OS no soportado para cmdline-tools: {os_key}")
        raise SystemExit(1)

    matches = re.findall(filename_re, html)
    uniq = list(dict.fromkeys(matches))
    if len(uniq) != 1:
        print("[ERROR] No se pudo resolver el ZIP de cmdline-tools desde la página de Android Studio.")
        print(f"[ERROR] OS: {os_key} | coincidencias: {len(uniq)}")
        raise SystemExit(1)

    filename = uniq[0]
    sha_match = re.search(re.escape(filename) + r"[\s\S]{0,300}?([0-9a-f]{40})", html, flags=re.IGNORECASE)
    if not sha_match:
        print("[ERROR] No se pudo resolver el SHA-1 del ZIP de cmdline-tools desde la página de Android Studio.")
        print(f"[ERROR] Archivo: {filename}")
        raise SystemExit(1)
    sha1 = sha_match.group(1).lower()
    return filename, sha1


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _download_cmdline_tools_zip(os_key: str) -> Path:
    filename, expected_sha1 = _resolve_cmdline_tools_release(os_key)
    url = ANDROID_REPOSITORY_URL + filename

    tmp_dir = Path(tempfile.mkdtemp(prefix="android_cmdline_tools_"))
    zip_path = tmp_dir / "commandlinetools-latest.zip"
    print(f"[INFO] Descargando cmdline-tools ({os_key})...")
    print(f"[INFO] URL: {url}")
    urllib.request.urlretrieve(url, zip_path)
    actual_sha1 = _sha1_file(zip_path)
    if actual_sha1 != expected_sha1:
        print("[ERROR] SHA-1 no coincide para cmdline-tools.")
        print(f"[ERROR] Esperado: {expected_sha1}")
        print(f"[ERROR] Actual:   {actual_sha1}")
        raise SystemExit(1)
    print(f"[OK] Descargado: {zip_path}")
    return zip_path


def _extract_cmdline_tools(zip_path: Path, sdk_root: Path, os_key: str) -> Path:
    tools_latest = sdk_root / "cmdline-tools" / "latest"

    sdkmanager_name = "sdkmanager.bat" if os_key == "windows" else "sdkmanager"
    existing = tools_latest / "bin" / sdkmanager_name
    if existing.exists():
        print("[OK] cmdline-tools ya está instalado.")
        return tools_latest

    print(f"[INFO] Descomprimiendo cmdline-tools en: {tools_latest}")
    tools_latest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tools_latest)

    inner = tools_latest / "cmdline-tools"
    if inner.exists():
        for item in inner.iterdir():
            item.rename(tools_latest / item.name)
        inner.rmdir()

    if not existing.exists():
        print(f"[ERROR] No se encontró sdkmanager después de descomprimir: {existing}")
        raise SystemExit(1)

    print("[OK] cmdline-tools instalado.")
    return tools_latest


def _sdkmanager_path(tools_latest: Path, os_key: str) -> str:
    name = "sdkmanager.bat" if os_key == "windows" else "sdkmanager"
    return str(tools_latest / "bin" / name)


def _accept_licenses(sdkmanager: str, sdk_root: Path) -> None:
    print("[INFO] Aceptando licencias...")
    subprocess.run(
        [sdkmanager, f"--sdk_root={sdk_root}", "--licenses"],
        input=("y\n" * 200).encode("utf-8"),
        check=False,
    )


def _sdkmanager_list_installed(sdkmanager: str, sdk_root: Path) -> set[str]:
    result = run_logged([sdkmanager, f"--sdk_root={sdk_root}", "--list_installed"], capture_output=True)
    installed: set[str] = set()
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pkg = line.split("|", 1)[0].strip()
        if pkg:
            installed.add(pkg)
    return installed


def _install_sdk_components(sdkmanager: str, sdk_root: Path) -> None:
    desired = [
        "platform-tools",
        "emulator",
        f"build-tools;{BUILD_TOOLS_VERSION}",
        f"platforms;android-{PLATFORM_API_LEVEL}",
    ]
    installed = _sdkmanager_list_installed(sdkmanager, sdk_root)
    missing = [pkg for pkg in desired if pkg not in installed]

    if not missing:
        print("[OK] Componentes ya instalados.")
        return

    print("[INFO] Instalando componentes faltantes:")
    for pkg in missing:
        print(f"  - {pkg}")
    run_logged([sdkmanager, f"--sdk_root={sdk_root}", *missing])
    print("[OK] Componentes instalados.")


def _install_or_validate_hypervisor(*, sdk_root: Path, sdkmanager: str, os_key: str) -> None:
    cpu = (platform.processor() or "").strip()
    machine = (platform.machine() or "").strip()
    print(f"[INFO] CPU detectado: {cpu or '-'} ({machine or '-'})")

    if os_key == "windows":
        service_check = subprocess.run(["sc", "query", "gvm"], capture_output=True)
        if service_check.returncode == 0:
            print("[OK] Hypervisor Driver ya está instalado (servicio gvm detectado).")
            return
        print("[INFO] Instalando Google Android Emulator Hypervisor Driver (si aplica)...")
        run_logged([sdkmanager, f"--sdk_root={sdk_root}", "extras;google;Android_Emulator_Hypervisor_Driver"])
        installer = (
            sdk_root
            / "extras"
            / "google"
            / "Android_Emulator_Hypervisor_Driver"
            / "silent_install.bat"
        )
        if installer.exists():
            subprocess.run([str(installer)], check=True, shell=True)
            print("[OK] Hypervisor Driver instalado.")
        else:
            print("[WARN] No se encontró silent_install.bat del Hypervisor Driver.")
        return

    if os_key == "linux":
        if os.path.exists("/dev/kvm"):
            print("[OK] /dev/kvm encontrado. KVM disponible.")
            return
        print("[ERROR] No se encontró /dev/kvm. Para emulador acelerado necesitas KVM habilitado.")
        raise SystemExit(1)


def _is_windows_android_sdk_path(path_entry: str) -> bool:
    p = (path_entry or "").strip().strip('"').rstrip("\\/").lower()
    return (
        p.endswith(r"\platform-tools")
        or p.endswith(r"\emulator")
        or p.endswith(r"\cmdline-tools\latest\bin")
        or r"\cmdline-tools\latest\bin" in p
    )


def _configure_windows_env(sdk_root: Path, tools_latest: Path) -> None:
    avd_home = sdk_root / AVD_HOME_DIR
    subprocess.run(["setx", "/M", "ANDROID_HOME", str(sdk_root)], check=True, capture_output=True)
    subprocess.run(["setx", "/M", "ANDROID_SDK_ROOT", str(sdk_root)], check=True, capture_output=True)
    subprocess.run(["setx", "/M", "ANDROID_AVD_HOME", str(avd_home)], check=True, capture_output=True)
    os.environ["ANDROID_HOME"] = str(sdk_root)
    os.environ["ANDROID_SDK_ROOT"] = str(sdk_root)
    os.environ["ANDROID_AVD_HOME"] = str(avd_home)

    import winreg

    def _read_system_env(name: str) -> str | None:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            0,
            winreg.KEY_READ,
        )
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)

    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    )
    current, _ = winreg.QueryValueEx(key, "Path")
    entries = [e for e in (current or "").split(";") if e.strip()]
    filtered = [e for e in entries if not _is_windows_android_sdk_path(e)]
    removed = len(entries) - len(filtered)
    if removed:
        print(f"[OK] Se removieron {removed} entrada(s) previas de Android SDK del PATH.")
    entries = filtered

    paths_to_add = [
        str(sdk_root / "platform-tools"),
        str(tools_latest / "bin"),
        str(sdk_root / "emulator"),
    ]

    added = False
    for p in paths_to_add:
        if p not in entries:
            entries.append(p)
            added = True
            print(f"[OK] Agregado al PATH: {p}")
        else:
            print(f"[OK] Ya en PATH: {p}")

    if added or removed:
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, ";".join(entries))
        print("[OK] PATH del sistema actualizado.")
    else:
        print("[OK] PATH del sistema ya estaba configurado.")
    winreg.CloseKey(key)

    android_home_sys = (_read_system_env("ANDROID_HOME") or "").strip()
    android_sdk_root_sys = (_read_system_env("ANDROID_SDK_ROOT") or "").strip()
    android_avd_home_sys = (_read_system_env("ANDROID_AVD_HOME") or "").strip()
    expected = str(sdk_root)
    expected_avd_home = str(avd_home)
    if android_home_sys != expected or android_sdk_root_sys != expected or android_avd_home_sys != expected_avd_home:
        print(
            "[ERROR] No se confirmaron ANDROID_HOME/ANDROID_SDK_ROOT/ANDROID_AVD_HOME a nivel sistema "
            "(posible falta de permisos)."
        )
        print(f"[ERROR] ANDROID_HOME:     '{android_home_sys}'")
        print(f"[ERROR] ANDROID_SDK_ROOT: '{android_sdk_root_sys}'")
        print(f"[ERROR] ANDROID_AVD_HOME: '{android_avd_home_sys}'")
        raise SystemExit(1)
    print("[OK] Variables ANDROID_HOME, ANDROID_SDK_ROOT y ANDROID_AVD_HOME confirmadas a nivel sistema.")

    key_verify = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0,
        winreg.KEY_READ,
    )
    try:
        path_value, _ = winreg.QueryValueEx(key_verify, "Path")
    finally:
        winreg.CloseKey(key_verify)

    missing_paths = [p for p in paths_to_add if p not in (path_value or "")]
    if missing_paths:
        print("[ERROR] No se confirmaron entradas de PATH a nivel sistema (posible falta de permisos).")
        for p in missing_paths:
            print(f"[ERROR] Falta en PATH: {p}")
        raise SystemExit(1)
    print("[OK] PATH confirmado a nivel sistema.")


def _append_shell_exports(profile_path: Path, sdk_root: Path) -> None:
    content = profile_path.read_text(encoding="utf-8", errors="replace") if profile_path.exists() else ""
    sdk_root_posix = sdk_root.as_posix()
    if (
        sdk_root_posix in content
        and "cmdline-tools/latest/bin" in content
        and "ANDROID_SDK_ROOT" in content
        and "ANDROID_AVD_HOME" in content
    ):
        print(f"[OK] Perfil ya contiene Android SDK: {profile_path}")
        return

    block = (
        "\n"
        + f'export ANDROID_SDK_ROOT="{sdk_root_posix}"\n'
        + 'export ANDROID_HOME="$ANDROID_SDK_ROOT"\n'
        + f'export ANDROID_AVD_HOME="{sdk_root_posix}/{AVD_HOME_DIR}"\n'
        + 'export PATH="$PATH:$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin"\n'
    )
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(content + block, encoding="utf-8")
    print(f"[OK] Perfil actualizado: {profile_path}")


def _remove_android_from_shell_profile(profile_path: Path) -> None:
    if not profile_path.exists():
        return

    lines = profile_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    kept: list[str] = []
    removed = 0
    for line in lines:
        if (
            "export ANDROID_SDK_ROOT=" in line
            or "export ANDROID_HOME=" in line
            or "export ANDROID_AVD_HOME=" in line
            or ("cmdline-tools/latest/bin" in line and "PATH" in line)
            or ("platform-tools" in line and "PATH" in line)
            or ("/emulator" in line and "PATH" in line)
        ):
            removed += 1
            continue
        kept.append(line)

    if removed == 0:
        return

    profile_path.write_text("".join(kept), encoding="utf-8")
    print(f"[OK] Se removieron {removed} línea(s) de Android SDK del perfil: {profile_path}")


def _configure_unix_env(sdk_root: Path) -> None:
    avd_home = sdk_root / AVD_HOME_DIR
    os.environ["ANDROID_HOME"] = str(sdk_root)
    os.environ["ANDROID_SDK_ROOT"] = str(sdk_root)
    os.environ["ANDROID_AVD_HOME"] = str(avd_home)

    shell = (os.environ.get("SHELL") or "").strip()
    profile = Path.home() / (".zshrc" if shell.endswith("zsh") else ".bashrc")
    print("[WARN] Se modificará tu perfil de shell para exportar ANDROID_SDK_ROOT/ANDROID_HOME/ANDROID_AVD_HOME y PATH.")
    _remove_android_from_shell_profile(profile)
    _append_shell_exports(profile, sdk_root)
    content = profile.read_text(encoding="utf-8", errors="replace") if profile.exists() else ""
    if (
        sdk_root.as_posix() not in content
        or "cmdline-tools/latest/bin" not in content
        or "ANDROID_AVD_HOME" not in content
    ):
        print("[ERROR] No se confirmó la modificación del perfil de shell (no se encontró la ruta en el perfil).")
        raise SystemExit(1)
    print(f"[OK] Perfil confirmado: {profile}")
    print("[INFO] Reinicia tu terminal para que el PATH se actualice.")


def main() -> None:
    os_key = detect_os()
    sdk_root = _default_sdk_root(os_key)
    sdk_root.mkdir(parents=True, exist_ok=True)

    _ensure_java()

    zip_path = _download_cmdline_tools_zip(os_key)
    tools_latest = _extract_cmdline_tools(zip_path, sdk_root, os_key)

    sdkmanager = _sdkmanager_path(tools_latest, os_key)
    _accept_licenses(sdkmanager, sdk_root)
    _install_sdk_components(sdkmanager, sdk_root)
    _install_or_validate_hypervisor(sdk_root=sdk_root, sdkmanager=sdkmanager, os_key=os_key)


    print("[INFO] Configurando variables de entorno y PATH...")
    if os_key == "windows":
        _configure_windows_env(sdk_root, tools_latest)
    else:
        _configure_unix_env(sdk_root)

    print("\n[OK] Instalación completa.")
    print(f"[OK] ANDROID_SDK_ROOT: {sdk_root}")


if __name__ == "__main__":
    main()
