from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
#ya esta recontruido por gpt
"""
Construye el APK de la app.

Flujo:
0) (Opcional) Si BUILD_APK=false: solo sube al VPS el APK ya generado y el pubspec.yaml.
1) Ubica Flutter (FLUTTER_BIN).
2) Incrementa la versión en pubspec.yaml (según VERSION_BUMP_MODE).
3) Corre flutter pub get.
4) Corre flutter build apk --release (pasando API_BASE_URL desde app/config.json).
5) Opcional: copia al VPS el APK generado y el pubspec.yaml, preservando la misma ruta relativa
   dentro del repo remoto.

Si falla cualquier paso, revierte el cambio de pubspec.yaml.
"""

BUILD_APK = True
VERSION_BUMP_MODE = "patch+build"  # patch+build | build_only | patch_only | none
FLUTTER_PROJECT_DIR = "app"

COPY_TO_VPS = True
VPS_REMOTE_DIR = "/srv"


SSH_CONNECT_TIMEOUT_SEC = 20
SSH_BATCH_MODE = True

def _run(cmd: list[str], *, cwd: Path, step: str) -> None:
    print(f"[INFO] {step}", flush=True)
    print(f"[INFO] Comando: {' '.join(cmd)}", flush=True)
    start = time.monotonic()
    subprocess.run(cmd, cwd=str(cwd), check=True)
    elapsed = time.monotonic() - start
    print(f"[OK] {step} ({elapsed:.1f}s)", flush=True)


def _ssh_base_args() -> list[str]:
    args: list[str] = []
    if SSH_BATCH_MODE:
        args.extend(["-o", "BatchMode=yes"])
    if SSH_CONNECT_TIMEOUT_SEC > 0:
        args.extend(["-o", f"ConnectTimeout={int(SSH_CONNECT_TIMEOUT_SEC)}"])
    return args

def find_project_root() -> Path:
    start = Path(__file__).resolve().parent


    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path

    raise RuntimeError("No se encontró .git.")


def _load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        raise FileNotFoundError(f"No existe el archivo .env: {env_path}")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        k = key.strip()
        v = value.strip()
        if k and k not in os.environ:
            os.environ[k] = v


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Falta variable requerida: {name}")
    return value.strip()


def _repo_name_from_git_url(git_repo_url: str) -> str:
    return git_repo_url.split("/")[-1].replace(".git", "")


def _copy_file_to_vps_same_repo_path(
    *,
    local_path: Path,
    repo_root: Path,
    remote_dir_base: str,
    git_repo_url: str,
    vps_ip: str,
    vps_user: str,
    identity_file: Path,
) -> str:
    if not identity_file.is_file():
        raise FileNotFoundError(f"No existe la llave privada local: {identity_file}")

    repo_name = _repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{remote_dir_base}/{repo_name}"
    try:
        rel = local_path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"El archivo no está dentro del repo: {local_path}") from exc

    remote_dest = f"{remote_repo_path}/{rel.as_posix()}"
    remote_parent = str(Path(remote_dest).parent).replace("\\", "/")

    print(f"[INFO] Subiendo al VPS: {rel.as_posix()}", flush=True)
    subprocess.run(
        [
            "ssh",
            *_ssh_base_args(),
            "-i",
            str(identity_file),
            f"{vps_user}@{vps_ip}",
            f'mkdir -p "{remote_parent}"',
        ],
        check=True,
    )

    subprocess.run(
        [
            "scp",
            *_ssh_base_args(),
            "-i",
            str(identity_file),
            str(local_path),
            f"{vps_user}@{vps_ip}:{remote_dest}",
        ],
        check=True,
    )

    return remote_dest


def _resolve_flutter_cmd() -> list[str]:
    configured = os.getenv("FLUTTER_BIN")
    if configured is not None and configured.strip():
        p = Path(configured.strip()).expanduser()
        if p.is_file():
            return [str(p)]
        raise FileNotFoundError(f"FLUTTER_BIN apunta a un archivo que no existe: {p}")

    candidates = ["flutter", "flutter.bat", "flutter.cmd", "flutter.exe"]
    resolved = ""
    for c in candidates:
        found = shutil.which(c)
        if found:
            resolved = found
            break

    if not resolved:
        raise FileNotFoundError("No se encontró flutter en PATH y no está definido FLUTTER_BIN.")

    lower = resolved.lower()
    if os.name == "nt" and (lower.endswith(".bat") or lower.endswith(".cmd")):
        return ["cmd.exe", "/c", resolved]
    return [resolved]


def _read_api_base_url_from_config(config_path: Path) -> str:
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe config.json: {config_path}")

    try:
        decoded = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"config.json inválido: {config_path}") from exc

    if not isinstance(decoded, dict):
        raise ValueError(f"config.json debe ser un objeto JSON: {config_path}")

    raw = decoded.get("API_BASE_URL")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Falta API_BASE_URL en config.json: {config_path}")

    return raw.strip()



def _bump_pubspec_version(pubspec_path: Path, *, bump_mode: str) -> tuple[str, str]:
    rx = re.compile(r'^(\s*version:\s*)(["\']?)(\d+\.\d+\.\d+)\+(\d+)(\2)(\s*)$')
    lines = pubspec_path.read_text(encoding="utf-8").splitlines(keepends=True)

    for i, line in enumerate(lines):
        newline = ""
        core = line
        if core.endswith("\r\n"):
            newline = "\r\n"
            core = core[:-2]
        elif core.endswith("\n"):
            newline = "\n"
            core = core[:-1]

        m = rx.match(core)
        if not m:
            continue

        old_semver = m.group(3)
        old_build = int(m.group(4))
        major, minor, patch = (int(x) for x in old_semver.split("."))

        bump_mode = bump_mode.strip()
        if bump_mode == "none":
            return f"{old_semver}+{old_build}", f"{old_semver}+{old_build}"

        if bump_mode == "patch+build":
            new_semver = f"{major}.{minor}.{patch + 1}"
            new_build = old_build + 1
        elif bump_mode == "build_only":
            new_semver = old_semver
            new_build = old_build + 1
        elif bump_mode == "patch_only":
            new_semver = f"{major}.{minor}.{patch + 1}"
            new_build = old_build
        else:
            raise ValueError(
                f"VERSION_BUMP_MODE inválido: {bump_mode!r}. Usa: patch+build | build_only | patch_only | none"
            )

        lines[i] = f"{m.group(1)}{m.group(2)}{new_semver}+{new_build}{m.group(5)}{m.group(6)}{newline}"
        pubspec_path.write_text("".join(lines), encoding="utf-8")
        return f"{old_semver}+{old_build}", f"{new_semver}+{new_build}"

    raise ValueError(f"No se encontró una línea version válida en: {pubspec_path}")


def main() -> None:
    repo_root = find_project_root()
    flutter_project_dir_raw = FLUTTER_PROJECT_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        flutter_project_dir_raw = sys.argv[1].strip()

    flutter_project_dir_candidate = Path(flutter_project_dir_raw)
    flutter_project_dir = (
        flutter_project_dir_candidate
        if flutter_project_dir_candidate.is_absolute()
        else (repo_root / flutter_project_dir_candidate)
    )
    pubspec_path = flutter_project_dir / "pubspec.yaml"
    config_path = flutter_project_dir / "config.json"
    apk_path = (
        flutter_project_dir
        / "build"
        / "app"
        / "outputs"
        / "flutter-apk"
        / "app-release.apk"
    )

    if not BUILD_APK:
        if not COPY_TO_VPS:
            raise RuntimeError("BUILD_APK=false requiere COPY_TO_VPS=true.")
        if not apk_path.is_file():
            raise FileNotFoundError(f"No se encontró el APK: {apk_path}")
        if not pubspec_path.is_file():
            raise FileNotFoundError(f"No se encontró pubspec.yaml: {pubspec_path}")

        env_path = repo_root / "scripts" / ".env"
        _load_env_file(env_path)

        vps_ip = _require_env("VPS_IP")
        vps_user = _require_env("VPS_USER")
        vps_key_name = _require_env("VPS_KEY_NAME")
        git_repo_url = _require_env("GIT_REPO_URL")

        identity_file = Path.home() / ".ssh" / vps_key_name
        remote_apk = _copy_file_to_vps_same_repo_path(
            local_path=apk_path,
            repo_root=repo_root,
            remote_dir_base=VPS_REMOTE_DIR,
            git_repo_url=git_repo_url,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
        )
        remote_pubspec = _copy_file_to_vps_same_repo_path(
            local_path=pubspec_path,
            repo_root=repo_root,
            remote_dir_base=VPS_REMOTE_DIR,
            git_repo_url=git_repo_url,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
        )

        print("build_apk=false")
        print(f"android_apk_build={apk_path}")
        print(f"android_ultima_apk_vps={remote_apk}")
        print(f"android_pubspec_vps={remote_pubspec}")
        return

    flutter_cmd = _resolve_flutter_cmd()
    api_base_url = _read_api_base_url_from_config(config_path).rstrip("/")

    pubspec_original = pubspec_path.read_text(encoding="utf-8")
    old_version, new_version = _bump_pubspec_version(pubspec_path, bump_mode=VERSION_BUMP_MODE)
    try:
        _run([*flutter_cmd, "pub", "get"], cwd=flutter_project_dir, step="flutter pub get")
        _run(
            [*flutter_cmd, "build", "apk", "--release", f"--dart-define=API_BASE_URL={api_base_url}"],
            cwd=flutter_project_dir,
            step="flutter build apk --release",
        )

        if not apk_path.is_file():
            raise FileNotFoundError(f"No se encontró el APK: {apk_path}")

        remote_apk = ""
        remote_pubspec = ""
        if COPY_TO_VPS:
            env_path = repo_root / "scripts" / ".env"
            _load_env_file(env_path)

            vps_ip = _require_env("VPS_IP")
            vps_user = _require_env("VPS_USER")
            vps_key_name = _require_env("VPS_KEY_NAME")
            git_repo_url = _require_env("GIT_REPO_URL")

            identity_file = Path.home() / ".ssh" / vps_key_name
            remote_apk = _copy_file_to_vps_same_repo_path(
                local_path=apk_path,
                repo_root=repo_root,
                remote_dir_base=VPS_REMOTE_DIR,
                git_repo_url=git_repo_url,
                vps_ip=vps_ip,
                vps_user=vps_user,
                identity_file=identity_file,
            )
            remote_pubspec = _copy_file_to_vps_same_repo_path(
                local_path=pubspec_path,
                repo_root=repo_root,
                remote_dir_base=VPS_REMOTE_DIR,
                git_repo_url=git_repo_url,
                vps_ip=vps_ip,
                vps_user=vps_user,
                identity_file=identity_file,
            )

        print(f"pubspec_version={old_version}->{new_version}")
        print(f"android_apk_build={apk_path}")
        if remote_apk:
            print(f"android_ultima_apk_vps={remote_apk}")
        if remote_pubspec:
            print(f"android_pubspec_vps={remote_pubspec}")
    except Exception:
        pubspec_path.write_text(pubspec_original, encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
