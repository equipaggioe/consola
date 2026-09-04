from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Project:
    name: str
    path: str
    color: str  # hex
    icon: str   # emoji


# No hay lista de repos de fabrica. La primera vez que se abre Consola la barra
# de pestanas esta vacia y se anade el primero con «+» (`ui/project_store.py`
# guarda lo que se vaya anadiendo). Antes vivia aca un `MOCK_PROJECTS` con las
# rutas del desarrollador, que en cualquier otra maquina eran ocho pestanas
# rotas.
