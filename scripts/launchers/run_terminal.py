from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

"""
Flujo:
1) Localiza el ejecutable de Python en el .venv de terminal.
2) Carga variables desde la raíz/.env a os.environ.
3) Lee la variable de entorno SERVER_PORT y construye SERVER_URL.
4) Inicia la aplicación de terminal como un subproceso.
5) Monitorea los archivos en las rutas especificadas en busca de cambios.
6) Si se detectan cambios, termina el proceso actual y lo reinicia.
7) Maneja la interrupción manual para detener el proceso.
"""


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        print(f"[ERROR] No existe el archivo .env: {env_path}")
        raise SystemExit(1)

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        k = key.strip()
        v = value.strip()
        if not k:
            continue
        os.environ[k] = v


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        print(f"[ERROR] Falta variable de entorno: {name}")
        raise SystemExit(1)
    return value.strip()


def _require_int_env(name: str) -> int:
    raw = _require_env(name)
    try:
        value = int(raw)
    except ValueError as exc:
        print(f"[ERROR] {name} no es numérico: {raw}")
        raise SystemExit(1) from exc
    if value < 1 or value > 65535:
        print(f"[ERROR] {name} fuera de rango: {value}")
        raise SystemExit(1)
    return value


def _find_terminal_python(repo_root: Path) -> Path:
    python_exe = repo_root / "terminal" / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        print(f"[ERROR] No existe el Python del venv de terminal: {python_exe}")
        raise SystemExit(1)
    return python_exe


def _iter_watch_files(base: Path) -> list[Path]:
    if not base.exists():
        return []
    if base.is_file():
        return [base]
    return [p for p in base.rglob("*") if p.is_file() and p.suffix in {".py", ".qss"}]


def _snapshot(paths: list[Path]) -> dict[str, int]:
    out: dict[str, int] = {}
    for base in paths:
        for p in _iter_watch_files(base):
            try:
                out[str(p)] = p.stat().st_mtime_ns
            except OSError:
                continue
    return out


def _has_changes(previous: dict[str, int], paths: list[Path]) -> tuple[bool, dict[str, int]]:
    current = _snapshot(paths)
    if current.keys() != previous.keys():
        return True, current
    for path_str, mtime_ns in current.items():
        if previous.get(path_str) != mtime_ns:
            return True, current
    return False, previous


def _terminate_process_tree(pid: int) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False)
        return
    subprocess.run(["kill", "-TERM", str(pid)], capture_output=True, check=False)


def run_watcher() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    terminal_src_dir = repo_root / "terminal" / "src"
    main_file = terminal_src_dir / "main.py"
    if not main_file.exists():
        print(f"[ERROR] No existe el entrypoint: {main_file}")
        return 1

    env_path = repo_root / "scripts" / ".env"
    _load_env_file(env_path)
    server_port = _require_int_env("SERVER_PORT")

    python_exe = _find_terminal_python(repo_root)
    cmd = [str(python_exe), "main.py"]
    watch_paths = [terminal_src_dir]

    child_env = os.environ.copy()
    child_env["SERVER_URL"] = f"http://localhost:{server_port}"

    print("[INFO] Iniciando terminal con recarga automática...")
    print(f"[INFO] Python: {python_exe}")
    print(f"[INFO] Entry: {main_file}")
    print(f"[INFO] Monitoreando: {terminal_src_dir}")
    print(f"[INFO] SERVER_URL: {child_env['SERVER_URL']}")

    snapshot = _snapshot(watch_paths)

    while True:
        print("[INFO] Lanzando proceso...")
        process = subprocess.Popen(cmd, cwd=str(terminal_src_dir), env=child_env)
        try:
            while process.poll() is None:
                time.sleep(0.35)
                changed, snapshot = _has_changes(snapshot, watch_paths)
                if changed:
                    print("[INFO] Cambios detectados. Reiniciando proceso...")
                    _terminate_process_tree(process.pid)
                    break
            else:
                code = process.returncode or 0
                if code == 0:
                    print("[OK] Proceso finalizado correctamente.")
                else:
                    print(f"[ERROR] Proceso finalizado con código: {code}")
                return code
        except KeyboardInterrupt:
            print("[INFO] Interrupción manual. Deteniendo proceso...")
            _terminate_process_tree(process.pid)
            print("[OK] Proceso detenido.")
            return 0


if __name__ == "__main__":
    raise SystemExit(run_watcher())
