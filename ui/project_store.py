from __future__ import annotations
import json
import os

from PySide6.QtCore import QSettings

from core.projects import Project, MOCK_PROJECTS

"""
Conjunto de repositorios abiertos como pestanas de nivel superior.

Antes solo se guardaba el ORDEN (una lista de rutas) y la lista real de repos
salia siempre de `MOCK_PROJECTS`: anadir un repo con «+», quitar uno o
reordenar uno anadido no sobrevivia al reinicio. Aca se guarda la lista
entera —ruta, nombre, color, icono— para que la UI arranque como quedo.

**Esto SI va en QSettings**, a diferencia de los parametros de cada accion, que
desde ahora viven en el repo (`ui/params_store.py`). La regla es de quien es la
decision: que repos tengo abiertos en pestanas es una decision de ESTA maquina
—un repo no puede saber que esta en tu barra— mientras que como quedaron
marcados los pasos de «Actualizar remoto» es una decision sobre ESE repo.
"""

_KEY = 'projects/list'
_LEGACY_ORDER_KEY = 'projects/order'


def identity(path: str) -> str:
    """Clave estable de un repo: su ruta normalizada.

    Es la identidad que se usa para todo lo indexado por repo —el espacio de
    trabajo abierto (`ui/main_window.py`), el cache de parametros
    (`ui/params_store.py`)— porque la misma carpeta escrita con barras al reves,
    con otra caja o con separador final tiene que contar como un solo repo.
    """
    return os.path.normcase(os.path.normpath(path or ''))


def display_path(path: str) -> str:
    """La forma en que se guarda y se muestra: barras hacia adelante, sin
    separador final. Normaliza sin destruir las mayusculas que el usuario ve."""
    return os.path.normpath(path or '').replace(os.sep, '/')


def _to_dict(p: Project) -> dict:
    return {'name': p.name, 'path': p.path, 'color': p.color, 'icon': p.icon}


def _from_dict(d: dict) -> Project | None:
    try:
        path = display_path(str(d['path']))
    except (KeyError, TypeError):
        return None
    if not path or path == '.':
        return None
    return Project(str(d.get('name') or os.path.basename(path)),
                   path,
                   str(d.get('color') or '#58a6ff'),
                   str(d.get('icon') or '\U0001F4C1'))


def dedupe(projects: list[Project]) -> list[Project]:
    """Un repo por carpeta, el primero gana.

    Dos pestanas de la misma carpeta serian dos espacios de trabajo escribiendo
    el mismo `.consola/params.json`, y el ultimo en guardar le pisaria lo
    elegido al otro sin que se note.
    """
    visto: set[str] = set()
    unicos = []
    for p in projects:
        key = identity(p.path)
        if key in visto:
            continue
        visto.add(key)
        unicos.append(p)
    return unicos


def _seed() -> list[Project]:
    """Primera vez (nada guardado): siembra con `MOCK_PROJECTS`, respetando el
    orden de la clave vieja `projects/order` si existe, y lo persiste — para
    que a partir de ahi quitar uno de fabrica tambien se recuerde."""
    order = QSettings().value(_LEGACY_ORDER_KEY, []) or []
    order = [order] if isinstance(order, str) else list(order)
    if order:
        by_key = {identity(p.path): p for p in MOCK_PROJECTS}
        seeded = [by_key.pop(identity(path)) for path in order if identity(path) in by_key]
        seeded.extend(by_key.values())
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
            projects = dedupe([p for p in (_from_dict(d) for d in data
                                           if isinstance(d, dict)) if p])
            if projects:
                return projects
    return _seed()


def save(projects: list[Project]) -> None:
    QSettings().setValue(
        _KEY, json.dumps([_to_dict(p) for p in dedupe(projects)], ensure_ascii=False)
    )


def reset() -> list[Project]:
    """Vuelve a la lista de fabrica. Es la unica salida si la guardada quedo
    apuntando a carpetas que ya no existen (`MOCK_PROJECTS` trae rutas de una
    maquina concreta, y una vez sembradas persisten para siempre)."""
    QSettings().remove(_KEY)
    QSettings().remove(_LEGACY_ORDER_KEY)
    save(MOCK_PROJECTS)
    return list(MOCK_PROJECTS)
