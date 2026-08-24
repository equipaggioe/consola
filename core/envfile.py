from __future__ import annotations
import os

from .errors import MissingConfig, TaskError
from .settings import SETTINGS, GROUP_ORDER, get_setting, settings_by_group

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


# ---------------------------------------------------------------------------
# Lectura tipada de un .env
# ---------------------------------------------------------------------------

def read_value(path: str, key: str) -> str:
    """Lee una sola clave de un .env sin cargar nada al entorno del proceso.

    Sustituye a `peek_env_value`: aca nunca se toca `os.environ`, porque una
    tarea no puede pisarle el entorno a las otras pestanas que corren a la vez.
    """
    return load_env(path).get(key, '')


def upsert_value(path: str, key: str, value: str) -> str:
    """Reemplaza o agrega `KEY=value` conservando el resto del archivo intacto."""
    lines = []
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as fh:
            lines = fh.read().splitlines()

    prefix = f'{key}='
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f'{key}={value}'
            replaced = True
    if not replaced:
        lines.append(f'{key}={value}')

    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    return 'updated' if replaced else 'added'


_TRUE = {'1', 'true', 'yes', 'y', 'on', 'si'}
_FALSE = {'0', 'false', 'no', 'n', 'off'}


class Config:
    """Los valores de `.consola/config.env` de un proyecto, ya leidos.

    Es lo que en los scripts eran ocho funciones sueltas sobre `os.environ`
    (`require_env`, `require_port_env`, `require_bool_env`, `optional_env`...).
    Aca son metodos de un solo objeto que la tarea recibe por el contexto, y
    que no dependen del entorno del proceso.
    """

    def __init__(self, values: dict[str, str] | None = None, *, repo_name: str = '') -> None:
        self.values = dict(values or {})
        self.repo_name = repo_name

    @classmethod
    def for_project(cls, repo_path: str) -> 'Config':
        return cls(load_config(repo_path), repo_name=os.path.basename(os.path.normpath(repo_path)))

    def __contains__(self, key: str) -> bool:
        return bool(self.values.get(key, '').strip())

    def get(self, key: str, default: str = '') -> str:
        """Valor, con el default del esquema como red antes que el default suelto."""
        raw = self.values.get(key, '').strip()
        if raw:
            return raw
        setting = get_setting(key)
        if setting and setting.default:
            return setting.default
        return default

    def require(self, key: str) -> str:
        value = self.get(key)
        if not value:
            raise MissingConfig([key])
        return value

    def port(self, key: str, default: int = 0) -> int:
        raw = self.get(key)
        if not raw:
            if default:
                return default
            raise MissingConfig([key])
        if not raw.isdigit() or not 1 <= int(raw) <= 65535:
            raise TaskError(f'{key} no es un puerto valido: {raw}')
        return int(raw)

    def flag(self, key: str, default: bool = False) -> bool:
        raw = self.get(key).lower()
        if not raw:
            return default
        if raw in _TRUE:
            return True
        if raw in _FALSE:
            return False
        raise TaskError(f'{key} no es un booleano: {raw}')

    def rel_path(self, key: str, root: str) -> str:
        """Una clave que guarda una ruta relativa al repo, resuelta contra `root`."""
        return os.path.normpath(os.path.join(root, self.require(key)))

    def missing(self, *keys: str) -> list[str]:
        return [k for k in keys if not self.get(k)]

    def secrets(self) -> list[str]:
        """Valores a enmascarar en la consola (PLAN.md 9)."""
        return [self.values[s.key] for s in SETTINGS
                if s.secret and self.values.get(s.key, '').strip()]
