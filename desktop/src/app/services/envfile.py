"""`.consola/config.env`: read, write and typed access."""

from __future__ import annotations

import os
from collections.abc import Iterable

from PySide6.QtCore import QCoreApplication

from app.services.errors import MissingConfig, TaskError
from app.services.settings import (
    GROUP_ORDER,
    Setting,
    get_setting,
    repo_settings,
    settings_by_group,
)

CONSOLA_DIR = ".consola"
CONFIG_NAME = "config.env"

HEADER = "# .consola/config.env - generado/editado por Consola, no a mano\n"


def config_path(repo_path: str) -> str:
    """Return the path of the repo's `config.env`."""
    return os.path.join(repo_path, CONSOLA_DIR, CONFIG_NAME)


def split_list(value: str) -> list[str]:
    """Split a value that lists several things on one line.

    It takes commas and line breaks as separators, discards empties and
    keeps the written order: a list of files to copy reads from left to
    right.
    """
    parts = (p.strip() for chunk in value.splitlines() for p in chunk.split(","))
    return [p for p in parts if p]


def repo_name_of(repo_path: str) -> str:
    """Return the repo's folder, the default `DB_USER` and `DB_NAME`."""
    return os.path.basename(os.path.normpath(repo_path))


def parse_env(text: str) -> dict[str, str]:
    """Return the keys and values of an env file's text."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # A pair of quotes that wraps the value, not any quote at the
        # edge: `strip("'")` ate the last one of `... frame-ancestors
        # 'none'` and left an invalid CSP in the Caddyfile.
        if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(path: str) -> dict[str, str]:
    """Return the keys and values of an env file."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return parse_env(fh.read())
    except (OSError, UnicodeDecodeError):
        return {}


def load_config(repo_path: str) -> dict[str, str]:
    """Return the repo's `config.env` as keys and values."""
    return load_env(config_path(repo_path))


def has_config(repo_path: str) -> bool:
    """Return whether the repo has a `config.env`."""
    return os.path.isfile(config_path(repo_path))


def config_text(repo_path: str) -> str | None:
    """Return the text of the repo's `config.env`, or None if absent.

    A file that exists and cannot be read stops: read as empty, the next
    save would write it back blank.
    """
    path = config_path(repo_path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise TaskError(
            QCoreApplication.translate("envfile", "No se puede leer {0}: {1}").format(path, error)
        ) from error


# Generic description of the dynamic default, for the template file,
# which belongs to no repo and cannot resolve it to a value.
_DYNAMIC_DEFAULT_HINTS = {
    "DB_USER": "nombre del repo",
    "DB_NAME": "<nombre del repo>_db",
    "DOMAIN": "<CF_DOMAIN_NAME>",
}


def describe(setting: Setting) -> str:
    """Return a key's comment line: what it is for and what is expected.

    It makes a freshly created file with all the schema's keys and no
    values readable: without it, it would be a bare list of names. It
    goes in the base language, whatever the interface's: the file
    belongs to the repo and does not change with the machine.
    """
    bits = []
    if setting.label and setting.label != setting.key:
        bits.append(setting.label)
    if setting.secret:
        bits.append("secreto")
    if setting.default:
        bits.append(f"por defecto: {setting.default}")
    elif setting.default_hint:
        bits.append(f"por defecto: {setting.default_hint}")
    elif setting.key in _DYNAMIC_DEFAULT_HINTS:
        bits.append(f"por defecto: {_DYNAMIC_DEFAULT_HINTS[setting.key]}")
    return " · ".join(bits)


def render_config(values: dict[str, str], fields: tuple[Setting, ...] = ()) -> str:
    """Regenerate the file grouped by category.

    Only the schema's `scope='repo'` keys and the repo's `Settings`
    fields (`services/fields.py`), which go in their group. Any other
    key in `values` is not written: machine keys belong in QSettings
    (`services/settings.py`), and a key the schema no longer declares is
    gone (`removed_keys` names them before saving).
    """
    groups = settings_by_group(fields)
    out = [HEADER]
    for group in GROUP_ORDER:
        items = [s for s in groups.get(group, []) if s.scope == "repo"]
        if not items:
            continue
        out.append(f"\n# --- {group} ---\n")
        for setting in items:
            note = describe(setting)
            if note:
                out.append(f"# {note}\n")
            out.append(f"{setting.key}={values.get(setting.key, '')}\n")
    return "".join(out)


def removed_keys(values: dict[str, str], fields: tuple[Setting, ...] = ()) -> list[str]:
    """Return the keys of `values` `render_config` does not write."""
    written = {s.key for s in (*repo_settings(), *fields)}
    return sorted(k for k in values if k not in written)


def is_current(text: str, fields: tuple[Setting, ...] = ()) -> bool:
    """Return whether the file's text already has the schema's form."""
    return text == render_config(parse_env(text), fields)


def save_config(repo_path: str, values: dict[str, str], fields: tuple[Setting, ...] = ()) -> str:
    """Write `.consola/config.env` and return its path.

    It creates the folder if needed.
    """
    path = config_path(repo_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_config(values, fields))
    ensure_ignored(repo_path)
    return path


# What `.consola/.gitignore` keeps out of commits (ADR-0087): the data
# and decisions of whoever runs Consola, and what the camera generates.
# The camera itself, in `.consola/camera/`, is versioned.
IGNORED = ("config.env", "params.json", "screenshots/", "publishable/")


def ensure_ignored(repo_path: str) -> None:
    """Keep the data of `.consola/` out of commits, with its .gitignore.

    ADR-0064 and ADR-0087.

    It goes inside the folder and not in the repo's `.gitignore`, which
    belongs to canone's template and not Consola. It adds the lines of
    `IGNORED` that are missing and keeps the others; a `*` from before
    ADR-0087 goes, because it also ignores the camera. If it cannot be
    written the exception rises: saving without that file leaves
    `config.env`, with its secrets, ready to be committed.

    Public because `services/params_store.py` also writes `params.json`
    there and needs the same guarantee.
    """
    path = os.path.join(repo_path, CONSOLA_DIR, ".gitignore")
    current = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            current = fh.read()
    lines = [line for line in current.splitlines() if line.strip() != "*"]
    lines += [entry for entry in IGNORED if entry not in lines]
    wanted = "".join(f"{line}\n" for line in lines)
    if current == wanted:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(wanted)


def import_from(path: str) -> dict[str, str]:
    """Return only the schema's keys of a .env file the user chose."""
    legacy = load_env(path)
    known = {s.key for s in repo_settings()}
    return {k: v for k, v in legacy.items() if k in known and v}


def missing_keys(values: dict[str, str], keys: Iterable[str]) -> list[str]:
    """Return which keys have no value."""
    return [k for k in keys if not values.get(k, "").strip()]


# --- typed reading of a .env ---


def read_value(path: str, key: str) -> str:
    """Read one key of a .env, loading nothing into the environment.

    It never touches `os.environ`, because a task must not overwrite the
    environment of the other tabs running at the same time.
    """
    return load_env(path).get(key, "")


_TRUE = {"1", "true", "yes", "y", "on", "si"}
_FALSE = {"0", "false", "no", "n", "off"}


class Config:
    """The values of a project's `.consola/config.env`, already read.

    They are methods of one object the task receives through its
    context, and they do not depend on the process environment.
    """

    def __init__(self, values: dict[str, str] | None = None, *, repo_name: str = "") -> None:
        """Keep the values and the repo's name."""
        self.values = dict(values or {})
        self.repo_name = repo_name

    @classmethod
    def for_project(cls, repo_path: str) -> "Config":
        """Return the config of that repo."""
        return cls(load_config(repo_path), repo_name=repo_name_of(repo_path))

    def __contains__(self, key: str) -> bool:
        """Return whether the key has a value."""
        return bool(self.values.get(key, "").strip())

    def get(self, key: str, default: str = "") -> str:
        """Return a value, or the schema's default, or the loose one.

        There are two kinds of default, in order: the fixed one of
        `Setting.default`, the same for any repo (`ROOT_USER='root'`),
        and the dynamic one below, which depends on THIS repo (`DB_USER`
        from its folder's name). Both are what the action will use if
        the field stays empty, so a key with either never counts as
        missing (`missing()`, and with it
        `widgets/params_panel.py::_missing_keys`).
        """
        raw = self.values.get(key, "").strip()
        if raw:
            return raw
        setting = get_setting(key)
        if setting and setting.default:
            return setting.default
        dynamic = self._dynamic_default(key)
        if dynamic:
            return dynamic
        return default

    def _dynamic_default(self, key: str) -> str:
        """Return the values derived from the repo or another key.

        The role and the local database come from the repo's name.
        `VPS_USER` has no default: it is the account that administers
        the VPS, and canone does not let it be named like the app
        (ADR-0087 of canone). `DOMAIN` comes from Cloudflare's domain.
        """
        if key == "DB_USER":
            return self.repo_name
        if key == "DB_NAME":
            return f"{self.repo_name}_db" if self.repo_name else ""
        if key == "DOMAIN":
            return self.get("CF_DOMAIN_NAME")
        return ""

    def require(self, key: str) -> str:
        """Return the key's value, or stop if it has none."""
        value = self.get(key)
        if not value:
            raise MissingConfig([key])
        return value

    def port(self, key: str, default: int = 0) -> int:
        """Return the key's value as a port."""
        raw = self.get(key)
        if not raw:
            if default:
                return default
            raise MissingConfig([key])
        if not raw.isdigit() or not 1 <= int(raw) <= 65535:
            raise TaskError(
                QCoreApplication.translate("Config", "{0} no es un puerto valido: {1}").format(
                    key, raw
                )
            )
        return int(raw)

    def flag(self, key: str, default: bool = False) -> bool:
        """Return the key's value as a boolean."""
        raw = self.get(key).lower()
        if not raw:
            return default
        if raw in _TRUE:
            return True
        if raw in _FALSE:
            return False
        raise TaskError(
            QCoreApplication.translate("Config", "{0} no es un booleano: {1}").format(key, raw)
        )

    def rel_path(self, key: str, root: str) -> str:
        """Return a key's path, resolved on `root`."""
        return os.path.normpath(os.path.join(root, self.require(key)))

    def missing(self, *keys: str) -> list[str]:
        """Return which of those keys have no value."""
        return [k for k in keys if not self.get(k)]
