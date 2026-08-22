from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import bump_semver, copy_to_vps, find_project_root, load_vps_config, require_env, reversible_write

"""
Construye la SPA (Svelte) y opcionalmente copia el build al VPS.

Flujo:
1) Calcula la raíz del repo (buscando .git).
2) Corre npm install en el proyecto.
3) Incrementa la versión (SemVer) en package.json (según VERSION_BUMP_MODE).
4) Corre npm run build.
5) Si COPY_TO_VPS es True, copia el directorio de salida al VPS en la misma ruta relativa del repo.
6) Si falla cualquier paso, revierte el cambio de package.json.

Notas:
- Si BUILD_SPA=false, se salta el bump de versión y npm install/build, y solo se sube al VPS
  el directorio de salida y el package.json ya existentes (requiere COPY_TO_VPS=true).
- Se usa 'npm install' en lugar de 'npm ci': 'npm ci' borra node_modules completo antes
  de reinstalar, y en Windows eso falla con EPERM si algún proceso (VSCode, el
  language server de Svelte, un dev server vivo) tiene abierto un binario nativo
  (.node) dentro de node_modules. 'npm install' respeta el lockfile y solo toca lo
  que cambió, sin depender de poder borrar el árbol entero.
"""

BUILD_SPA = True
COPY_TO_VPS = True

DEFAULT_PROJECT_DIR = "panel"  # Carpeta del proyecto SPA (relativa a la raíz del repo)
BUILD_OUTPUT_DIR_NAME = ""
VERSION_BUMP_MODE = "patch"  # major | minor | patch | none


def _run(cmd: list[str], *, cwd: Path) -> None:
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    subprocess.run(cmd, cwd=str(cwd), check=True)


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

    bump_mode = bump_mode.strip()
    if bump_mode == "none":
        return old_version, old_version

    major, minor, patch = bump_semver(
        int(vm.group(1)), int(vm.group(2)), int(vm.group(3)), mode=bump_mode
    )
    new_version = f"{major}.{minor}.{patch}"

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


def _copy_to_vps(*, local_path: Path, repo_root: Path, is_dir: bool) -> str:
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    git_repo_url = require_env("GIT_REPO_URL")
    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")

    remote_rel = local_path.relative_to(repo_root).as_posix()
    return copy_to_vps(
        local_path,
        remote_rel_path=remote_rel,
        remote_dir_base=vps_deploy_dir,
        git_repo_url=git_repo_url,
        vps_ip=vps_ip,
        vps_user=vps_user,
        identity_file=identity_file,
        is_dir=is_dir,
    )


def main() -> None:
    repo_root = find_project_root(Path(__file__).resolve().parent)
    spa_project_dir = DEFAULT_PROJECT_DIR
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        spa_project_dir = sys.argv[1].strip()

    project_dir = repo_root / spa_project_dir

    if not project_dir.is_dir():
        raise FileNotFoundError(f"No existe el proyecto SPA: {project_dir}")

    package_json_path = project_dir / "package.json"

    if not BUILD_SPA:
        if not COPY_TO_VPS:
            raise RuntimeError("BUILD_SPA=false requiere COPY_TO_VPS=true.")

        output_dir = _resolve_build_output_dir(project_dir)
        remote_dir = _copy_to_vps(local_path=output_dir, repo_root=repo_root, is_dir=True)
        remote_package_json = _copy_to_vps(local_path=package_json_path, repo_root=repo_root, is_dir=False)

        print("build_spa=false")
        print(f"spa_build_dir={output_dir}")
        print(f"spa_build_dir_vps={remote_dir}")
        print(f"package_json_vps={remote_package_json}")
        return

    _run(["npm", "install"], cwd=project_dir)

    with reversible_write(package_json_path):
        old_version, new_version = _bump_package_version(package_json_path, bump_mode=VERSION_BUMP_MODE)
        _run(["npm", "run", "build"], cwd=project_dir)

        output_dir = _resolve_build_output_dir(project_dir)

        remote_dir = ""
        if COPY_TO_VPS:
            remote_dir = _copy_to_vps(local_path=output_dir, repo_root=repo_root, is_dir=True)

        print(f"package_version={old_version}->{new_version}")
        print(f"spa_build_dir={output_dir}")
        if remote_dir:
            print(f"spa_build_dir_vps={remote_dir}")


if __name__ == "__main__":
    main()
