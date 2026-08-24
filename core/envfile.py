from __future__ import annotations
import os

from .settings import SETTINGS, GROUP_ORDER, settings_by_group

CONSOLA_DIR = '.consola'
CONFIG_NAME = 'config.env'

HEADER = "# .consola/config.env - generado/editado por Consola, no a mano\n"


def config_path(repo_path: str) -> str:
    return os.path.join(repo_path, CONSOLA_DIR, CONFIG_NAME)


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_env(path: str) -> dict[str, str]:
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return parse_env(fh.read())
    except (OSError, UnicodeDecodeError):
        return {}


def load_config(repo_path: str) -> dict[str, str]:
    return load_env(config_path(repo_path))


def has_config(repo_path: str) -> bool:
    return os.path.isfile(config_path(repo_path))


def render_config(values: dict[str, str]) -> str:
    """Regenera el archivo agrupado por categoria; las claves ajenas se conservan al final."""
    known = {s.key for s in SETTINGS}
    out = [HEADER]
    for group in GROUP_ORDER:
        items = settings_by_group().get(group, [])
        if not items:
            continue
        out.append(f"\n# {group}\n")
        for setting in items:
            out.append(f"{setting.key}={values.get(setting.key, '')}\n")
    extra = {k: v for k, v in values.items() if k not in known}
    if extra:
        out.append("\n# Otras claves\n")
        for key in sorted(extra):
            out.append(f"{key}={extra[key]}\n")
    return ''.join(out)


def save_config(repo_path: str, values: dict[str, str]) -> str:
    """Escribe `.consola/config.env` y devuelve la ruta. Crea la carpeta si falta."""
    path = config_path(repo_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(render_config(values))
    _ensure_gitignored(repo_path)
    return path


def _ensure_gitignored(repo_path: str) -> None:
    """`.consola/` nunca se commitea (PLAN.md §9)."""
    gitignore = os.path.join(repo_path, '.gitignore')
    entry = f"{CONSOLA_DIR}/"
    try:
        existing = ''
        if os.path.isfile(gitignore):
            with open(gitignore, 'r', encoding='utf-8') as fh:
                existing = fh.read()
            if any(line.strip().rstrip('/') == CONSOLA_DIR for line in existing.splitlines()):
                return
        prefix = '' if (not existing or existing.endswith('\n')) else '\n'
        with open(gitignore, 'a', encoding='utf-8', newline='\n') as fh:
            fh.write(f"{prefix}{entry}\n")
    except OSError:
        pass  # no poder tocar .gitignore nunca debe romper el guardado


def import_from(path: str) -> dict[str, str]:
    """Lee un archivo .env arbitrario (elegido por el usuario) y devuelve
    solo las claves que sobreviven al esquema."""
    legacy = load_env(path)
    known = {s.key for s in SETTINGS}
    return {k: v for k, v in legacy.items() if k in known and v}


def missing_keys(values: dict[str, str], keys) -> list[str]:
    return [k for k in keys if not values.get(k, '').strip()]
