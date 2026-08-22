from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
#ya esta recontruido por gpt
"""
Construye el APK de la app (Flutter o Flet, con detección automática).

Flujo:
0) (Opcional) Si BUILD_APK=false: solo sube al VPS el APK ya generado y el archivo de versión.
1) Detecta el tipo de proyecto (Flutter o Flet) según APP_TYPE, o automáticamente
   buscando pubspec.yaml (Flutter) o pyproject.toml con 'flet' como dependencia (Flet).
2) Ubica el binario del framework correspondiente (FLUTTER_BIN o FLET_BIN).
3) Incrementa la versión en pubspec.yaml o pyproject.toml (según VERSION_BUMP_MODE).
4) Corre el build:
   - Flutter: flutter pub get, luego flutter build apk --release.
   - Flet: flet build apk.
   En ambos casos se pasa API_BASE_URL (desde API_URL de scripts/.env, la misma fuente
   que usa scripts/launchers/run_flutter.py para las corridas de debug) vía --dart-define.
5) Opcional: copia al VPS el APK generado y el archivo de versión, preservando la misma ruta
   relativa dentro del repo remoto.

Si falla cualquier paso, revierte el cambio del archivo de versión.
"""

BUILD_APK = True
COPY_TO_VPS = True

APP_DIR = "app"
APP_TYPE = "auto"  # auto | flutter | flet
VERSION_BUMP_MODE = "patch+build"  # patch+build | build_only | patch_only | none

SSH_CONNECT_TIMEOUT_SEC = 20
SSH_BATCH_MODE = True


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    copy_to_vps,
    detect_app_project_type,
    find_project_root,
    load_env_file,
    load_vps_config,
    require_env,
    resolve_flet_cmd,
    resolve_flutter_cmd,
    reversible_write,
)


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
    try:
        rel = local_path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"El archivo no está dentro del repo: {local_path}") from exc

    print(f"[INFO] Subiendo al VPS: {rel.as_posix()}", flush=True)
    return copy_to_vps(
        local_path,
        remote_rel_path=rel.as_posix(),
        remote_dir_base=remote_dir_base,
        git_repo_url=git_repo_url,
        vps_ip=vps_ip,
        vps_user=vps_user,
        identity_file=identity_file,
        extra_ssh_args=_ssh_base_args(),
    )


def _load_vps_config(repo_root: Path) -> tuple[str, str, str, str, Path]:
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")
    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    return vps_ip, vps_user, git_repo_url, vps_deploy_dir, identity_file


def _read_api_base_url(repo_root: Path) -> str:
    """Resuelve la URL del backend desde scripts/.env (clave API_URL).

    Fuente unica compartida con run_flutter.py: antes el build de release la
    leia de app/config.json y el runner de debug de scripts/.env, asi que los
    dos valores podian divergir sin que nada avisara.
    """
    load_env_file(repo_root / "scripts" / ".env")
    return require_env("API_URL").rstrip("/")


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


def _bump_pyproject_version(pyproject_path: Path, *, bump_mode: str) -> tuple[str, str]:
    """Incrementa version = "X.Y.Z" dentro de la sección [project] de un pyproject.toml.

    Flet no tiene el concepto de build number separado (a diferencia de pubspec.yaml),
    así que build_only no modifica nada y patch+build/patch_only bumpean el patch.
    """
    rx = re.compile(r'^(\s*version\s*=\s*)(["\'])(\d+\.\d+\.\d+)(\2)(\s*)$')
    lines = pyproject_path.read_text(encoding="utf-8").splitlines(keepends=True)

    in_project_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project_section = stripped == "[project]"
            continue
        if not in_project_section:
            continue

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
        major, minor, patch = (int(x) for x in old_semver.split("."))

        bump_mode = bump_mode.strip()
        if bump_mode in ("none", "build_only"):
            return old_semver, old_semver

        if bump_mode in ("patch+build", "patch_only"):
            new_semver = f"{major}.{minor}.{patch + 1}"
        else:
            raise ValueError(
                f"VERSION_BUMP_MODE inválido: {bump_mode!r}. Usa: patch+build | build_only | patch_only | none"
            )

        lines[i] = f"{m.group(1)}{m.group(2)}{new_semver}{m.group(4)}{m.group(5)}{newline}"
        pyproject_path.write_text("".join(lines), encoding="utf-8")
        return old_semver, new_semver

    raise ValueError(f"No se encontró una línea version válida en la sección [project] de: {pyproject_path}")


def _find_flet_apk(flet_build_dir: Path) -> Path:
    if not flet_build_dir.is_dir():
        raise FileNotFoundError(f"No se encontró el directorio de build de Flet: {flet_build_dir}")
    apks = sorted(flet_build_dir.glob("*.apk"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not apks:
        raise FileNotFoundError(f"No se encontró ningún .apk en: {flet_build_dir}")
    return apks[0]


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    app_project_dir_raw = APP_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        app_project_dir_raw = sys.argv[1].strip()

    project_dir_candidate = Path(app_project_dir_raw)
    project_dir = (
        project_dir_candidate if project_dir_candidate.is_absolute() else (repo_root / project_dir_candidate)
    )

    app_type = APP_TYPE.strip().lower()
    if app_type == "auto":
        app_type = detect_app_project_type(project_dir)
    elif app_type not in ("flutter", "flet"):
        raise ValueError(f"APP_TYPE inválido: {APP_TYPE!r}. Usa: auto | flutter | flet")
    print(f"[INFO] Tipo de proyecto detectado: {app_type}", flush=True)

    if app_type == "flutter":
        version_path = project_dir / "pubspec.yaml"
        apk_path = project_dir / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"
    else:
        version_path = project_dir / "pyproject.toml"
        flet_build_dir = project_dir / "build" / "apk"

    if not BUILD_APK:
        if not COPY_TO_VPS:
            raise RuntimeError("BUILD_APK=false requiere COPY_TO_VPS=true.")
        if app_type == "flet":
            apk_path = _find_flet_apk(flet_build_dir)
        elif not apk_path.is_file():
            raise FileNotFoundError(f"No se encontró el APK: {apk_path}")
        if not version_path.is_file():
            raise FileNotFoundError(f"No se encontró el archivo de versión: {version_path}")

        vps_ip, vps_user, git_repo_url, vps_deploy_dir, identity_file = _load_vps_config(repo_root)
        remote_apk = _copy_file_to_vps_same_repo_path(
            local_path=apk_path,
            repo_root=repo_root,
            remote_dir_base=vps_deploy_dir,
            git_repo_url=git_repo_url,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
        )
        remote_version = _copy_file_to_vps_same_repo_path(
            local_path=version_path,
            repo_root=repo_root,
            remote_dir_base=vps_deploy_dir,
            git_repo_url=git_repo_url,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
        )

        print("build_apk=false")
        print(f"android_apk_build={apk_path}")
        print(f"android_ultima_apk_vps={remote_apk}")
        print(f"android_version_vps={remote_version}")
        return

    api_base_url = _read_api_base_url(repo_root)

    with reversible_write(version_path):
        if app_type == "flutter":
            old_version, new_version = _bump_pubspec_version(version_path, bump_mode=VERSION_BUMP_MODE)
            flutter_cmd = resolve_flutter_cmd()
            _run([*flutter_cmd, "pub", "get"], cwd=project_dir, step="flutter pub get")
            _run(
                [*flutter_cmd, "build", "apk", "--release", f"--dart-define=API_BASE_URL={api_base_url}"],
                cwd=project_dir,
                step="flutter build apk --release",
            )
            if not apk_path.is_file():
                raise FileNotFoundError(f"No se encontró el APK: {apk_path}")
        else:
            old_version, new_version = _bump_pyproject_version(version_path, bump_mode=VERSION_BUMP_MODE)
            flet_cmd = resolve_flet_cmd()
            _run(
                [*flet_cmd, "build", "apk", f"--dart-define=API_BASE_URL={api_base_url}"],
                cwd=project_dir,
                step="flet build apk",
            )
            apk_path = _find_flet_apk(flet_build_dir)

        remote_apk = ""
        remote_version = ""
        if COPY_TO_VPS:
            vps_ip, vps_user, git_repo_url, vps_deploy_dir, identity_file = _load_vps_config(repo_root)
            remote_apk = _copy_file_to_vps_same_repo_path(
                local_path=apk_path,
                repo_root=repo_root,
                remote_dir_base=vps_deploy_dir,
                git_repo_url=git_repo_url,
                vps_ip=vps_ip,
                vps_user=vps_user,
                identity_file=identity_file,
            )
            remote_version = _copy_file_to_vps_same_repo_path(
                local_path=version_path,
                repo_root=repo_root,
                remote_dir_base=vps_deploy_dir,
                git_repo_url=git_repo_url,
                vps_ip=vps_ip,
                vps_user=vps_user,
                identity_file=identity_file,
            )

        print(f"version={old_version}->{new_version}")
        print(f"android_apk_build={apk_path}")
        if remote_apk:
            print(f"android_ultima_apk_vps={remote_apk}")
        if remote_version:
            print(f"android_version_vps={remote_version}")


if __name__ == "__main__":
    main()
