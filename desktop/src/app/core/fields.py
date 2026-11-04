from __future__ import annotations

import ast
from pathlib import Path

from app.core.errors import TaskError
from app.core.settings import Setting, get_setting

"""
Los campos de `Settings` del repo administrado (ADR-0063).

Son lo que el servidor lee de sus credenciales, y sus valores de produccion van
en `config.env` con el nombre del campo en mayusculas. canone fija donde vive la
clase (`<SERVER_DIR>/src/app/config.py`) y que todo campo es obligatorio. Se lee
con `ast` y no importando el modulo: importarlo pediria el venv del repo, y el
modulo lee `CREDENTIALS_DIRECTORY` al cargarse.
"""

CONFIG = Path("src") / "app" / "config.py"
GROUP = "Credenciales"

# Los escribe `install.py`, no `credentials.py` (ADR-0105 de canone).
WRITTEN_BY_INSTALL = ("database_url", "turn_secret")


def settings_fields(server: Path) -> list[str]:
    """Los campos de la clase `Settings`, en el orden en que se declaran.

    Sin `config.py` no hay ninguno: el repo no sigue la plantilla de canone.
    Con el archivo y sin la clase, corta: es un repo de canone roto.
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
    """Una clave de `config.env` por campo, salvo los que escribe `install.py`.

    Una clave que fuera a la vez campo y clave de Consola tendria dos fuentes,
    y no se sabria a quien mandarla: corta.
    """
    claves = []
    for field in settings_fields(server):
        if field in WRITTEN_BY_INSTALL:
            continue
        key = field.upper()
        if get_setting(key) is not None:
            raise TaskError(f"El campo {field} de Settings choca con la clave {key} de Consola.")
        claves.append(Setting(key, GROUP, field, secret=True))
    return tuple(claves)
