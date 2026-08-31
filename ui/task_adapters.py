from __future__ import annotations
from typing import Callable

"""
El puente entre lo que marca el panel de parametros y lo que espera la
funcion real de `core/tasks/`.

Existe porque las dos puntas cambian por razones distintas: el catalogo
elige como se llama un eje para quien lo lee (`'Gradle/Android'`), y la
funcion elige como se llama su parametro para quien programa
(`families=['gradle']`). Sin este archivo esa traduccion viviria a mano
en `TabPanel._run`, mezclada con el resto del cableado de la consola.

Cada entrada de `ADAPTERS` es la senal de que esa capacidad ya dejo de ser
un stub: `TabPanel._run` corre de verdad la que tiene adaptador aca, y sigue
simulando las que no. Conectar el siguiente boton es agregar su adaptador.
"""

# Etiqueta tal como aparece en `catalog.FAMILY_AXIS_VALUES` / `HEAVY_AXIS_VALUES`
# -> clave que entiende `core.tasks.utils.find_artifacts`. Explicito a mano:
# un reorden de las listas del catalogo no debe desalinear esto.
_FAMILY_LABEL_TO_KEY = {
    'Python': 'python',
    'Gradle/Android': 'gradle',
    'Flutter': 'flutter',
    'Volcados de crash': 'crash',
}
_HEAVY_LABEL_TO_KEY = {
    'node_modules': 'node_modules',
    '.venv': 'venv',
    'build/dist': 'build',
    '.dart_tool': 'dart_tool',
}


def _clean_artifacts_kwargs(payload: dict) -> dict:
    families = [_FAMILY_LABEL_TO_KEY[v] for v in payload['variants'].get('families', [])
               if v in _FAMILY_LABEL_TO_KEY]
    heavy = [_HEAVY_LABEL_TO_KEY[v] for v in payload['variants'].get('heavy', [])
            if v in _HEAVY_LABEL_TO_KEY]
    apply = payload['options'].get('dry_run') == 'borrar'
    return {'apply': apply, 'families': families, 'heavy': heavy}


# capability_id -> payload (de ParamsPanel.payload()) -> kwargs de la funcion real
ADAPTERS: dict[str, Callable[[dict], dict]] = {
    'clean_artifacts': _clean_artifacts_kwargs,
}
