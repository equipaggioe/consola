from __future__ import annotations
import json

from PySide6.QtCore import QSettings

from core.projects import Project, MOCK_PROJECTS

"""
Conjunto de repositorios abiertos como pestanas de nivel superior.

Antes solo se guardaba el ORDEN (una lista de rutas) y la lista real de repos
salia siempre de `MOCK_PROJECTS`: anadir un repo con «+», quitar uno o
reordenar uno anadido no sobrevivia al reinicio. Aca se guarda la lista
entera —ruta, nombre, color, icono— para que la UI arranque como quedo.

Se guarda en QSettings, igual que los favoritos (`ui/favorites.py`) y los
parametros por repo (`ui/params_store.py`).
"""

_KEY = 'projects/list'
_LEGACY_ORDER_KEY = 'projects/order'


def _to_dict(p: Project) -> dict:
    return {'name': p.name, 'path': p.path, 'color': p.color, 'icon': p.icon}


def _from_dict(d: dict) -> Project | None:
    try:
        return Project(str(d['name']), str(d['path']), str(d['color']), str(d['icon']))
    except (KeyError, TypeError):
        return None


def _seed() -> list[Project]:
    """Primera vez (nada guardado): siembra con `MOCK_PROJECTS`, respetando el
    orden de la clave vieja `projects/order` si existe, y lo persiste — para
    que a partir de ahi quitar uno de fabrica tambien se recuerde."""
    order = QSettings().value(_LEGACY_ORDER_KEY, []) or []
    order = list(order) if not isinstance(order, str) else ([order] if order else [])
    if order:
        by_path = {p.path: p for p in MOCK_PROJECTS}
        seeded = [by_path.pop(path) for path in order if path in by_path]
        seeded.extend(by_path.values())
    else:
        seeded = list(MOCK_PROJECTS)
    save(seeded)
    return seeded


def load() -> list[Project]:
    """Los repos guardados, en orden. Nunca devuelve una lista vacia."""
    raw = QSettings().value(_KEY, '')
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = None
        if isinstance(data, list):
            projects = [p for p in (_from_dict(d) for d in data if isinstance(d, dict)) if p]
            if projects:
                return projects
    return _seed()


def save(projects: list[Project]) -> None:
    QSettings().setValue(
        _KEY, json.dumps([_to_dict(p) for p in projects], ensure_ascii=False)
    )
