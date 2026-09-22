from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Project:
    name: str
    path: str
    theme: str  # clave de una paleta de `ui/palettes.py`
    icon: str   # emoji


# No hay lista de repos de fabrica. La primera vez que se abre Consola la barra
# de pestanas esta vacia y se anade el primero con «+» (`ui/project_store.py`
# guarda lo que se vaya anadiendo). Antes vivia aca un `MOCK_PROJECTS` con las
# rutas del desarrollador, que en cualquier otra maquina eran ocho pestanas
# rotas.
#
# `theme` es una clave («azul», «coral»), no un color: el repo elige un tema y
# de ahi sale la escalera entera de fondos de su espacio de trabajo
# (`ui/palettes.py`). Guardar la clave y no el hex deja afinar la receta sin
# tener que repintar a mano cada repo ya guardado. Se resuelve en la UI, que es
# quien sabe de colores; `core` no importa `ui`.
