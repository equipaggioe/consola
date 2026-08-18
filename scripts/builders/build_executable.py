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
"""


ENTRYPOINT = ""
APP_NAME = ""
ONEFILE = True

VERSION_BUMP_MODE = "patch"  # major | minor | patch | none

COPY_TO_VPS = False
VPS_REMOTE_DIR = "/srv"


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


def _copy_to_vps_file(
    *,
    local_path: Path,
    remote_rel_path: str,
    remote_dir_base: str,
    git_repo_url: str,
    vps_ip: str,
    vps_user: str,
    identity_file: Path,
) -> str:
    if not local_path.is_file():
        raise FileNotFoundError(f"No existe el archivo local: {local_path}")

    if not identity_file.is_file():
        raise FileNotFoundError(f"No existe la llave privada local: {identity_file}")

    repo_name = _repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{remote_dir_base}/{repo_name}"
    remote_rel_posix = Path(remote_rel_path).as_posix()
    remote_full_path = f"{remote_repo_path}/{remote_rel_posix}"
    remote_parent = Path(remote_full_path).parent.as_posix()

    subprocess.run(
        ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", f'mkdir -p "{remote_parent}"'],
        check=True,
    )

    subprocess.run(
        ["scp", "-i", str(identity_file), str(local_path), f"{vps_user}@{vps_ip}:{remote_full_path}"],
        check=True,
    )

    return remote_full_path


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

        major = int(vm.group(1))
        minor = int(vm.group(2))
        patch = int(vm.group(3))

        bump_mode = bump_mode.strip()
        if bump_mode == "none":
            return old_version, old_version

        if bump_mode == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_mode == "minor":
            minor += 1
            patch = 0
        elif bump_mode == "patch":
            patch += 1
        else:
            raise ValueError(
                f"VERSION_BUMP_MODE inválido: {bump_mode!r}. Usa: major | minor | patch | none"
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


def main() -> None:
    repo_root = find_project_root()
    tag = _platform_tag()

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

    app_root = entrypoint_path.parent
    pyproject_path = app_root / "pyproject.toml"
    _ensure_pyproject(pyproject_path, project_name=(APP_NAME.strip() or app_root.name))

    app_name = APP_NAME.strip() or entrypoint_path.stem

    pyinstaller = _find_pyinstaller()

    pyproject_original = pyproject_path.read_text(encoding="utf-8")
    old_version, new_version = _bump_pyproject_version(pyproject_path, bump_mode=VERSION_BUMP_MODE)
    try:
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
    except Exception:
        pyproject_path.write_text(pyproject_original, encoding="utf-8")
        raise

    suffix = ".exe" if tag == "windows" and ONEFILE else ""
    artifact = app_root / "dist" / f"{app_name}{suffix}"
    if ONEFILE:
        if not artifact.is_file():
            raise FileNotFoundError(f"No se encontró el ejecutable esperado: {artifact}")
    else:
        artifact = app_root / "dist" / app_name
        if not artifact.exists():
            raise FileNotFoundError(f"No se encontró el output esperado: {artifact}")

    remote_artifact = ""
    if COPY_TO_VPS:
        env_path = repo_root / "scripts" / ".env"
        _load_env_file(env_path)

        vps_ip = _require_env("VPS_IP")
        vps_user = _require_env("VPS_USER")
        vps_key_name = _require_env("VPS_KEY_NAME")
        git_repo_url = _require_env("GIT_REPO_URL")

        identity_file = Path.home() / ".ssh" / vps_key_name
        remote_rel = artifact.relative_to(app_root).as_posix()
        remote_artifact = _copy_to_vps_file(
            local_path=artifact,
            remote_rel_path=remote_rel,
            remote_dir_base=VPS_REMOTE_DIR,
            git_repo_url=git_repo_url,
            vps_ip=vps_ip,
            vps_user=vps_user,
            identity_file=identity_file,
        )

    print(f"pyproject_version={old_version}->{new_version}")
    print(f"platform={tag}")
    print(f"entrypoint={entrypoint_path}")
    print(f"artifact={artifact}")
    if remote_artifact:
        print(f"artifact_vps={remote_artifact}")


if __name__ == "__main__":
    main()
