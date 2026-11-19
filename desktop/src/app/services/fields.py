"""The `Settings` fields of the managed repo (ADR-0063).

They are what the server reads from its credentials, and their
production values go in `config.env` under the field name in upper case.
canone fixes where the class lives (`<SERVER_DIR>/src/app/config.py`)
and that every field is required. It is read with `ast` and not by
importing the module: importing asks for the repo's venv, and the module
reads `CREDENTIALS_DIRECTORY` on load.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services.errors import TaskError
from app.services.settings import Setting, get_setting

CONFIG = Path("src") / "app" / "config.py"
GROUP = "Credenciales"

# The secret of coturn: only an app with calls declares it (ADR-0085).
TURN = "turn_secret"
# `install.py` writes these, not `credentials.py` (ADR-0105 of canone),
# which refuses them.
WRITTEN_BY_INSTALL = ("database_url", TURN, "valkey_url")


def settings_fields(server: Path) -> list[str]:
    """Return the fields of the `Settings` class in declaration order.

    Without `config.py` there are none: the repo does not follow the
    canone template. With the file and without the class it stops,
    because that is a broken canone repo.
    """
    path = server / CONFIG
    if not path.is_file():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return [
                line.target.id
                for line in node.body
                if isinstance(line, ast.AnnAssign) and isinstance(line.target, ast.Name)
            ]
    raise TaskError(f"{path} no declara la clase Settings.")


def field_settings(server: Path) -> tuple[Setting, ...]:
    """Return one `config.env` key per field, except `install.py`'s.

    A key that is both a field and a Consola key would have two sources,
    and nobody would know which one wins: it stops.
    """
    keys = []
    for field in settings_fields(server):
        if field in WRITTEN_BY_INSTALL:
            continue
        key = field.upper()
        if get_setting(key) is not None:
            raise TaskError(f"El campo {field} de Settings choca con la clave {key} de Consola.")
        keys.append(Setting(key, GROUP, field, secret=True))
    return tuple(keys)
