from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

"""
Construye la SPA (Svelte) y opcionalmente copia el build al VPS.

Flujo:
1) Calcula la raíz del repo (buscando .git).
2) Incrementa la versión (SemVer) en package.json (según VERSION_BUMP_MODE).
3) Corre npm ci en el proyecto.
4) Corre npm run build.
5) Si COPY_TO_VPS es True, copia el directorio de salida al VPS en la misma ruta relativa del repo.
6) Si falla cualquier paso, revierte el cambio de package.json.
"""


DEFAULT_PROJECT_DIR = "panel"
BUILD_OUTPUT_DIR_NAME = ""

VERSION_BUMP_MODE = "patch"  # major | minor | patch | none
COPY_TO_VPS = True
VPS_REMOTE_DIR = "/srv"


def _run(cmd: list[str], *, cwd: Path) -> None:
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    subprocess.run(cmd, cwd=str(cwd), check=True)


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


def _bump_package_version(package_json_path: Path, *, bump_mode: str) -> tuple[str, str]:
    text = package_json_path.read_text(encoding="utf-8")

    m = re.search(r'("version"\s*:\s*")([^"]+)(")', text)
    if not m:
        raise ValueError(f"No se encontró 'version' en: {package_json_path}")

    old_version = m.group(2).strip()
    vm = re.match(r"^(\d+)\.(\d+)\.(\d+)$", old_version)
    if not vm:
        raise ValueError(
            "Formato de version no soportado en package.json. Usa SemVer: X.Y.Z (ej: 1.2.3)"
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
        new_version = f"{major}.{minor}.{patch}"
    elif bump_mode == "minor":
        minor += 1
        patch = 0
        new_version = f"{major}.{minor}.{patch}"
    elif bump_mode == "patch":
        patch += 1
        new_version = f"{major}.{minor}.{patch}"
    else:
        raise ValueError(
            f"VERSION_BUMP_MODE inválido: {bump_mode!r}. Usa: major | minor | patch | none"
        )

    updated = text[: m.start(2)] + new_version + text[m.end(2) :]
    package_json_path.write_text(updated, encoding="utf-8")
    return old_version, new_version


def _resolve_build_output_dir(project_dir: Path) -> Path:
    configured = BUILD_OUTPUT_DIR_NAME.strip()
    if configured:
        output_dir = project_dir / configured
        if not output_dir.is_dir():
            raise FileNotFoundError(
                f"No se encontró el directorio de salida esperado: {output_dir}. Ajusta BUILD_OUTPUT_DIR_NAME."
            )
        return output_dir

    candidates = [project_dir / "build", project_dir / "dist"]
    existing = [p for p in candidates if p.is_dir()]
    if len(existing) == 1:
        return existing[0]

    found = ", ".join(str(p) for p in existing) if existing else "ninguno"
    raise FileNotFoundError(
        "No se pudo determinar el directorio de salida del build. "
        f"Encontrados: {found}. Configura BUILD_OUTPUT_DIR_NAME."
    )


def _copy_dir_to_vps(
    *,
    local_dir: Path,
    rel_dir_from_repo_root: Path,
    remote_dir_base: str,
    git_repo_url: str,
    vps_ip: str,
    vps_user: str,
    identity_file: Path,
) -> str:
    if not local_dir.is_dir():
        raise FileNotFoundError(f"No existe el directorio local: {local_dir}")

    if not identity_file.is_file():
        raise FileNotFoundError(f"No existe la llave privada local: {identity_file}")

    repo_name = _repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{remote_dir_base}/{repo_name}"

    rel_posix = rel_dir_from_repo_root.as_posix()
    remote_parent = f"{remote_repo_path}/{Path(rel_posix).parent.as_posix()}"

    subprocess.run(
        ["ssh", "-i", str(identity_file), f"{vps_user}@{vps_ip}", f'mkdir -p "{remote_parent}"'],
        check=True,
    )

    remote_dest = f"{remote_parent}"
    subprocess.run(
        ["scp", "-r", "-i", str(identity_file), str(local_dir), f"{vps_user}@{vps_ip}:{remote_dest}"],
        check=True,
    )

    remote_dir = f"{remote_repo_path}/{rel_posix}"
    return remote_dir


def main() -> None:
    repo_root = find_project_root()
    spa_project_dir = DEFAULT_PROJECT_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        spa_project_dir = sys.argv[1].strip()

    project_dir = repo_root / spa_project_dir

    if not project_dir.is_dir():
        raise FileNotFoundError(f"No existe el proyecto SPA: {project_dir}")

    package_json_path = project_dir / "package.json"
    package_original = package_json_path.read_text(encoding="utf-8")
    old_version, new_version = _bump_package_version(package_json_path, bump_mode=VERSION_BUMP_MODE)
    try:
        _run(["npm", "ci"], cwd=project_dir)
        _run(["npm", "run", "build"], cwd=project_dir)

        output_dir = _resolve_build_output_dir(project_dir)

        remote_dir = ""
        if COPY_TO_VPS:
            env_path = repo_root / "scripts" / ".env"
            _load_env_file(env_path)

            vps_ip = _require_env("VPS_IP")
            vps_user = _require_env("VPS_USER")
            vps_key_name = _require_env("VPS_KEY_NAME")
            git_repo_url = _require_env("GIT_REPO_URL")

            identity_file = Path.home() / ".ssh" / vps_key_name
            rel_dir_from_repo_root = output_dir.relative_to(repo_root)
            remote_dir = _copy_dir_to_vps(
                local_dir=output_dir,
                rel_dir_from_repo_root=rel_dir_from_repo_root,
                remote_dir_base=VPS_REMOTE_DIR,
                git_repo_url=git_repo_url,
                vps_ip=vps_ip,
                vps_user=vps_user,
                identity_file=identity_file,
            )

        print(f"package_version={old_version}->{new_version}")
        print(f"spa_build_dir={output_dir}")
        if remote_dir:
            print(f"spa_build_dir_vps={remote_dir}")
    except Exception:
        package_json_path.write_text(package_original, encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
