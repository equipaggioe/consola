from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

"""
Construye un ejecutable descargable a partir de una app Python (PyInstaller).

Flujo:
1) Calcula la raíz del repo (buscando .git).
2) Resuelve ENTRYPOINT (puede pasarse por CLI o usar el default del script).
3) Busca o crea pyproject.toml en la raíz de la app (carpeta del ENTRYPOINT).
4) Incrementa la versión (SemVer) en pyproject.toml según VERSION_BUMP_MODE.
5) Ejecuta PyInstaller con --name (ONEFILE controla --onefile).
6) Si COPY_TO_VPS es True, copia el artefacto al VPS en la misma ruta relativa del repo remoto.
7) Si falla cualquier paso, revierte pyproject.toml.

Notas:
- PyInstaller no compila cross-platform: para Windows y Linux, corre este script en cada SO.
- Si BUILD_BINARY=false, se salta el bump de versión y PyInstaller, y solo se sube al VPS
  el ejecutable y el pyproject.toml ya existentes (requiere COPY_TO_VPS=true).
"""

BUILD_BINARY = True
COPY_TO_VPS = False

ENTRYPOINT = ""  # Archivo Python que PyInstaller ejecutará como punto de entrada (ej: server/main.py, tools/cli.py)
APP_NAME = ""
ONEFILE = True
VERSION_BUMP_MODE = "patch"  # major | minor | patch | none


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import bump_semver, copy_to_vps, find_project_root, load_vps_config, require_env, reversible_write


def _platform_tag() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    raise RuntimeError(f"Plataforma no soportada: os.name={os.name!r}, sys.platform={sys.platform!r}")


def _find_pyinstaller() -> str:
    configured = os.getenv("PYINSTALLER_BIN")
    if configured and configured.strip():
        p = Path(configured.strip()).expanduser()
        if p.is_file():
            return str(p)
        raise FileNotFoundError(f"PYINSTALLER_BIN apunta a un archivo que no existe: {p}")

    exe = shutil.which("pyinstaller")
    if exe:
        return exe
    if os.name == "nt":
        exe = shutil.which("pyinstaller.exe")
        if exe:
            return exe
        exe = shutil.which("pyinstaller.cmd")
        if exe:
            return exe

    raise FileNotFoundError(
        "No se encontró PyInstaller. Instálalo en tu entorno actual o define PYINSTALLER_BIN."
    )


def _bump_pyproject_version(pyproject_path: Path, *, bump_mode: str) -> tuple[str, str]:
    lines = pyproject_path.read_text(encoding="utf-8").splitlines(keepends=True)

    in_project = False
    rx_header = re.compile(r"^\s*\[(.+?)\]\s*$")
    rx_version = re.compile(r'^(\s*version\s*=\s*")([^"]+)(".*)$')

    for i, line in enumerate(lines):
        line_noeol = line.rstrip("\r\n")
        eol = line[len(line_noeol) :]

        header = rx_header.match(line_noeol)
        if header:
            in_project = header.group(1).strip() == "project"
            continue

        if not in_project:
            continue

        m = rx_version.match(line_noeol)
        if not m:
            continue

        old_version = m.group(2).strip()
        vm = re.match(r"^(\d+)\.(\d+)\.(\d+)$", old_version)
        if not vm:
            raise ValueError(
                f"Versión inválida en pyproject.toml (usa X.Y.Z): {old_version!r}"
            )

        if bump_mode.strip() == "none":
            return old_version, old_version

        major, minor, patch = bump_semver(
            int(vm.group(1)), int(vm.group(2)), int(vm.group(3)), mode=bump_mode
        )
        new_version = f"{major}.{minor}.{patch}"
        lines[i] = f"{m.group(1)}{new_version}{m.group(3)}{eol}"
        pyproject_path.write_text("".join(lines), encoding="utf-8")
        return old_version, new_version

    raise ValueError(f"No se encontró [project].version en: {pyproject_path}")


def _ensure_pyproject(pyproject_path: Path, *, project_name: str) -> None:
    if pyproject_path.is_file():
        return

    safe_name = re.sub(r"[^0-9A-Za-z._-]+", "-", project_name).strip("-").lower()
    if not safe_name:
        safe_name = "python-app"

    pyproject_path.write_text(
        "\n".join(
            [
                "[project]",
                f'name = "{safe_name}"',
                'version = "0.0.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _copy_to_vps(*, local_path: Path, repo_root: Path, app_root: Path) -> str:
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")
    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")

    remote_rel = local_path.relative_to(app_root).as_posix()
    return copy_to_vps(
        local_path,
        remote_rel_path=remote_rel,
        remote_dir_base=vps_deploy_dir,
        git_repo_url=git_repo_url,
        vps_ip=vps_ip,
        vps_user=vps_user,
        identity_file=identity_file,
    )


def _resolve_entrypoint(repo_root: Path) -> Path:
    entrypoint_raw = ENTRYPOINT.strip()
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        entrypoint_raw = sys.argv[1].strip()

    if not entrypoint_raw:
        raise RuntimeError("ENTRYPOINT está vacío. Pásalo por línea de comando o configúralo en el script.")

    entrypoint_candidate = Path(entrypoint_raw)
    entrypoint_path = (
        entrypoint_candidate
        if entrypoint_candidate.is_absolute()
        else (repo_root / entrypoint_candidate)
    )
    if not entrypoint_path.is_file():
        raise FileNotFoundError(f"No existe ENTRYPOINT: {entrypoint_path}")
    return entrypoint_path


def _resolve_artifact(app_root: Path, *, app_name: str, tag: str) -> Path:
    suffix = ".exe" if tag == "windows" and ONEFILE else ""
    artifact = app_root / "dist" / f"{app_name}{suffix}"
    if ONEFILE:
        if not artifact.is_file():
            raise FileNotFoundError(f"No se encontró el ejecutable esperado: {artifact}")
    else:
        artifact = app_root / "dist" / app_name
        if not artifact.exists():
            raise FileNotFoundError(f"No se encontró el output esperado: {artifact}")
    return artifact


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    tag = _platform_tag()

    entrypoint_path = _resolve_entrypoint(repo_root)
    app_root = entrypoint_path.parent
    pyproject_path = app_root / "pyproject.toml"
    _ensure_pyproject(pyproject_path, project_name=(APP_NAME.strip() or app_root.name))
    app_name = APP_NAME.strip() or entrypoint_path.stem

    if not BUILD_BINARY:
        if not COPY_TO_VPS:
            raise RuntimeError("BUILD_BINARY=false requiere COPY_TO_VPS=true.")

        artifact = _resolve_artifact(app_root, app_name=app_name, tag=tag)
        remote_artifact = _copy_to_vps(local_path=artifact, repo_root=repo_root, app_root=app_root)
        remote_pyproject = _copy_to_vps(local_path=pyproject_path, repo_root=repo_root, app_root=app_root)

        print("build_binary=false")
        print(f"platform={tag}")
        print(f"artifact={artifact}")
        print(f"artifact_vps={remote_artifact}")
        print(f"pyproject_vps={remote_pyproject}")
        return

    pyinstaller = _find_pyinstaller()

    with reversible_write(pyproject_path):
        old_version, new_version = _bump_pyproject_version(pyproject_path, bump_mode=VERSION_BUMP_MODE)
        cmd: list[str] = [
            pyinstaller,
            "--noconfirm",
            "--clean",
            "--name",
            app_name,
        ]
        if ONEFILE:
            cmd.append("--onefile")
        cmd.append(str(entrypoint_path))

        subprocess.run(cmd, cwd=str(app_root), check=True)

    artifact = _resolve_artifact(app_root, app_name=app_name, tag=tag)

    remote_artifact = ""
    if COPY_TO_VPS:
        remote_artifact = _copy_to_vps(local_path=artifact, repo_root=repo_root, app_root=app_root)

    print(f"pyproject_version={old_version}->{new_version}")
    print(f"platform={tag}")
    print(f"entrypoint={entrypoint_path}")
    print(f"artifact={artifact}")
    if remote_artifact:
        print(f"artifact_vps={remote_artifact}")


if __name__ == "__main__":
    main()
