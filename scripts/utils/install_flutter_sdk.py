from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

"""
Instala Flutter SDK (stable) y configura entorno.

Flujo:
1) Detecta sistema operativo.
2) Resuelve el ZIP real de Flutter stable desde el JSON oficial y valida SHA-256.
3) Descarga el ZIP y lo descomprime en <FLUTTER_HOME>.
4) Valida que exista flutter (flutter.bat/flutter).
5) Limpia PATH de rutas anteriores de Flutter.
6) Agrega la nueva ruta de Flutter al PATH.
7) Ejecuta flutter --version y flutter doctor (sin fallar por warnings).
"""


FLUTTER_HOME = r"D:\flutter"
FLUTTER_RELEASES_BASE_URL = "https://storage.googleapis.com/flutter_infra_release/releases/"


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture_output,
        input=input_text,
    )


def _detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    print(f"[ERROR] Sistema operativo no soportado: {sys.platform}")
    raise SystemExit(1)


def _default_flutter_home(os_key: str) -> Path:
    return Path(FLUTTER_HOME)


def _ensure_git() -> None:
    try:
        _run(["git", "--version"], check=False, capture_output=True)
    except FileNotFoundError:
        print("[ERROR] No se encontró Git (git). Flutter lo requiere (actualizaciones y herramientas).")
        raise SystemExit(1)


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8", errors="replace"))


def _resolve_flutter_stable(os_key: str) -> tuple[str, str]:
    if os_key == "windows":
        releases_url = FLUTTER_RELEASES_BASE_URL + "releases_windows.json"
    elif os_key == "linux":
        releases_url = FLUTTER_RELEASES_BASE_URL + "releases_linux.json"
    else:
        print(f"[ERROR] OS no soportado para Flutter: {os_key}")
        raise SystemExit(1)

    data = _fetch_json(releases_url)
    stable_hash = (((data.get("current_release") or {}).get("stable")) or "").strip()
    if not stable_hash:
        print("[ERROR] No se pudo resolver el hash stable de Flutter desde el JSON oficial.")
        raise SystemExit(1)

    releases = data.get("releases") or []
    stable = next((r for r in releases if (r.get("hash") or "").strip() == stable_hash), None)
    if not stable:
        print("[ERROR] No se encontró el release stable en la lista de releases.")
        raise SystemExit(1)

    archive_rel = (stable.get("archive") or "").strip()
    sha256 = (stable.get("sha256") or "").strip().lower()
    if not archive_rel or not sha256:
        print("[ERROR] El release stable no trae 'archive' o 'sha256' en el JSON oficial.")
        raise SystemExit(1)

    url = FLUTTER_RELEASES_BASE_URL + archive_rel
    return url, sha256


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _download_flutter_zip(os_key: str) -> Path:
    url, expected_sha256 = _resolve_flutter_stable(os_key)
    tmp_dir = Path(tempfile.mkdtemp(prefix="flutter_sdk_"))
    zip_path = tmp_dir / "flutter-sdk.zip"
    print(f"[INFO] Descargando Flutter SDK ({os_key})...")
    print(f"[INFO] URL: {url}")
    urllib.request.urlretrieve(url, zip_path)
    actual_sha256 = _sha256_file(zip_path)
    if actual_sha256 != expected_sha256:
        print("[ERROR] SHA-256 no coincide para Flutter SDK.")
        print(f"[ERROR] Esperado: {expected_sha256}")
        print(f"[ERROR] Actual:   {actual_sha256}")
        raise SystemExit(1)
    print(f"[OK] Descargado: {zip_path}")
    return zip_path


def _extract_flutter(zip_path: Path, flutter_home: Path, os_key: str) -> Path:
    flutter_tool = flutter_home / "bin" / ("flutter.bat" if os_key == "windows" else "flutter")
    if flutter_tool.exists():
        print("[OK] Flutter ya está instalado.")
        return flutter_home

    flutter_home.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Descomprimiendo Flutter en: {flutter_home.parent}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(flutter_home.parent)

    extracted = flutter_home.parent / "flutter"
    if extracted != flutter_home:
        if flutter_home.exists():
            print(f"[ERROR] Ya existe el directorio destino: {flutter_home}")
            print("[ERROR] No se puede mover el folder extraído sin sobrescribir.")
            raise SystemExit(1)
        if extracted.exists():
            extracted.rename(flutter_home)

    if not flutter_tool.exists():
        print(f"[ERROR] No se encontró flutter después de descomprimir: {flutter_tool}")
        raise SystemExit(1)

    print("[OK] Flutter instalado.")
    return flutter_home


def _configure_windows_env(flutter_home: Path) -> None:
    import winreg

    def _delete_user_env(name: str) -> None:
        try:
            key_user = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
        except FileNotFoundError:
            return

        try:
            try:
                winreg.DeleteValue(key_user, name)
                print(f"[OK] Variable de usuario eliminada: {name}")
            except FileNotFoundError:
                pass
        finally:
            winreg.CloseKey(key_user)

    def _remove_flutter_from_user_path() -> None:
        try:
            key_user = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
        except FileNotFoundError:
            return

        try:
            try:
                current_user_path, path_type = winreg.QueryValueEx(key_user, "Path")
            except FileNotFoundError:
                return

            entries = [e for e in (current_user_path or "").split(";") if e.strip()]
            filtered = [e for e in entries if r"\flutter\bin" not in e.lower()]
            removed = len(entries) - len(filtered)
            if removed == 0:
                return

            winreg.SetValueEx(key_user, "Path", 0, path_type, ";".join(filtered))
            print(f"[OK] Se removieron {removed} entrada(s) de Flutter del PATH de usuario.")
        finally:
            winreg.CloseKey(key_user)

    key = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    )
    winreg.SetValueEx(key, "FLUTTER_HOME", 0, winreg.REG_SZ, str(flutter_home))
    current, _ = winreg.QueryValueEx(key, "Path")
    entries = [e for e in (current or "").split(";") if e.strip()]
    filtered = [e for e in entries if r"\flutter\bin" not in e.lower()]
    removed = len(entries) - len(filtered)
    if removed:
        print(rf"[OK] Se removieron {removed} entrada(s) de Flutter del PATH.")
    entries = filtered

    paths_to_add = [
        str(flutter_home / "bin"),
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

    _delete_user_env("FLUTTER_HOME")
    _remove_flutter_from_user_path()

    key_verify = winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        0,
        winreg.KEY_READ,
    )
    try:
        flutter_home_value, _ = winreg.QueryValueEx(key_verify, "FLUTTER_HOME")
        path_value, _ = winreg.QueryValueEx(key_verify, "Path")
    finally:
        winreg.CloseKey(key_verify)

    expected_flutter_home = str(flutter_home)
    if (flutter_home_value or "").strip() != expected_flutter_home:
        print("[ERROR] No se confirmó FLUTTER_HOME a nivel sistema (posible falta de permisos).")
        print(f"[ERROR] FLUTTER_HOME: '{flutter_home_value}'")
        raise SystemExit(1)
    print("[OK] FLUTTER_HOME confirmado a nivel sistema.")

    missing_paths = [p for p in paths_to_add if p not in (path_value or "")]
    if missing_paths:
        print("[ERROR] No se confirmaron entradas de PATH a nivel sistema (posible falta de permisos).")
        for p in missing_paths:
            print(f"[ERROR] Falta en PATH: {p}")
        raise SystemExit(1)
    print("[OK] PATH confirmado a nivel sistema.")


def _remove_flutter_from_shell_profile(profile_path: Path) -> None:
    if not profile_path.exists():
        return

    lines = profile_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    kept: list[str] = []
    removed = 0
    for line in lines:
        if "flutter/bin" in line:
            removed += 1
            continue
        kept.append(line)

    if removed == 0:
        return

    profile_path.write_text("".join(kept), encoding="utf-8")
    print(f"[OK] Se removieron {removed} línea(s) de Flutter del perfil: {profile_path}")


def _append_shell_exports(profile_path: Path, flutter_home: Path) -> None:
    content = profile_path.read_text(encoding="utf-8", errors="replace") if profile_path.exists() else ""
    flutter_bin = (flutter_home / "bin").as_posix()
    if flutter_bin in content:
        print(f"[OK] Perfil ya contiene Flutter en PATH: {profile_path}")
        return

    block = "\n" + f'export PATH="$PATH:{flutter_bin}"\n'
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(content + block, encoding="utf-8")
    print(f"[OK] Perfil actualizado: {profile_path}")


def _configure_unix_env(flutter_home: Path) -> None:
    os.environ["PATH"] = os.environ.get("PATH", "") + f":{flutter_home}/bin"

    shell = (os.environ.get("SHELL") or "").strip()
    profile = Path.home() / (".zshrc" if shell.endswith("zsh") else ".bashrc")
    print("[WARN] Se modificará tu perfil de shell para exportar PATH.")
    _remove_flutter_from_shell_profile(profile)
    _append_shell_exports(profile, flutter_home)
    content = profile.read_text(encoding="utf-8", errors="replace") if profile.exists() else ""
    if (flutter_home / "bin").as_posix() not in content:
        print("[ERROR] No se confirmó la modificación del perfil de shell (no se encontró la ruta en el perfil).")
        raise SystemExit(1)
    print(f"[OK] Perfil confirmado: {profile}")
    print("[INFO] Reinicia tu terminal para que el PATH se actualice.")


def main() -> None:
    os_key = _detect_os()
    flutter_home = _default_flutter_home(os_key)

    _ensure_git()

    zip_path = _download_flutter_zip(os_key)
    flutter_home = _extract_flutter(zip_path, flutter_home, os_key)

    print("[INFO] Configurando variables de entorno y PATH...")
    if os_key == "windows":
        _configure_windows_env(flutter_home)
    else:
        _configure_unix_env(flutter_home)

    flutter_bin = flutter_home / "bin" / ("flutter.bat" if os_key == "windows" else "flutter")
    print("\n[INFO] Verificando Flutter...")
    _run([str(flutter_bin), "--version"], check=True)

    print("\n[INFO] Ejecutando flutter doctor (puede reportar warnings)...")
    _run([str(flutter_bin), "doctor"], check=False)

    print("\n[OK] Instalación completa.")
    print(f"[OK] Flutter instalado en: {flutter_home}")
    print("[INFO] Abre una nueva terminal para usar 'flutter' desde PATH.")


if __name__ == "__main__":
    main()
