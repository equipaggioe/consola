import os
import shutil
from pathlib import Path
from typing import Dict, Optional


def _load_dotenv_if_present(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}

    out: Dict[str, str] = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                out[k] = v
    except Exception:
        return {}
    return out


def _env(name: str, fallback: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    if v is None:
        return fallback
    v = v.strip()
    return v if v else fallback


def _resolve_dir(cfg: str, repo_root: Path) -> Path:
    p = Path(cfg).expanduser()
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


def _recreate_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    scripts_dir = Path(__file__).resolve().parent
    repo_root = scripts_dir.parent

    dotenv = _load_dotenv_if_present(repo_root / "backend" / ".env")
    if os.getenv("APP_WEB_ULTIMA_DIR") is None and "APP_WEB_ULTIMA_DIR" in dotenv:
        os.environ["APP_WEB_ULTIMA_DIR"] = dotenv["APP_WEB_ULTIMA_DIR"]
    if os.getenv("APP_WEB_ESTABLE_DIR") is None and "APP_WEB_ESTABLE_DIR" in dotenv:
        os.environ["APP_WEB_ESTABLE_DIR"] = dotenv["APP_WEB_ESTABLE_DIR"]

    ultima_dir_raw = _env("APP_WEB_ULTIMA_DIR")
    app_web_ultima_dir = (
        _resolve_dir(ultima_dir_raw, repo_root)
        if ultima_dir_raw
        else (repo_root / "backend" / "pze" / "static" / "app_web_ultima")
    )

    estable_dir_raw = _env("APP_WEB_ESTABLE_DIR")
    app_web_estable_dir = (
        _resolve_dir(estable_dir_raw, repo_root)
        if estable_dir_raw
        else (repo_root / "backend" / "pze" / "static" / "app_web_estable")
    )

    if not app_web_ultima_dir.is_dir():
        raise FileNotFoundError(f"No existe app_web_ultima_dir: {app_web_ultima_dir}")
    if not (app_web_ultima_dir / "index.html").is_file():
        raise FileNotFoundError(f"No se encontró index.html en app_web_ultima_dir: {app_web_ultima_dir}")

    _recreate_dir(app_web_estable_dir)
    shutil.copytree(app_web_ultima_dir, app_web_estable_dir, dirs_exist_ok=True)

    print(f"app_web_ultima_dir={app_web_ultima_dir}")
    print(f"app_web_estable_dir={app_web_estable_dir}")


if __name__ == "__main__":
    main()
