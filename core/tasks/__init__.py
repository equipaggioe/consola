from __future__ import annotations

"""Niveles 1 y 2: las capacidades con cuerpo real.

Cada modulo agrupa las atomicas de un grupo del rail y las compuestas que las
encadenan. La regla para saber si un paso interno de un script viejo se volvio
atomica con boton propio esta en PLAN.md 7, caso 7: se separa si tiene sentido
re-ejecutarlo solo, sin repetir el resto.

Nada de aca reimplementa plomeria: todo se apoya en `core/` (nivel 0). Por eso
la mayoria de las atomicas son de tres a diez lineas.
"""

from . import builders, database, emulators, launchers, utils, vps_ops, vps_server, vps_setup

MODULES = (launchers, builders, emulators, vps_ops, vps_server, vps_setup, database, utils)

__all__ = ['MODULES', 'bind_all', 'builders', 'database', 'emulators', 'launchers',
           'utils', 'vps_ops', 'vps_server', 'vps_setup']


def bind_all() -> None:
    """Le da cuerpo a todas las capacidades del catalogo que ya estan implementadas.

    Se llama despues de `load_catalog()`: el catalogo declara la forma, esto
    reemplaza el stub por la funcion. Lo que no aparezca aca sigue siendo stub y
    la UI lo dibuja como tal.
    """
    for module in MODULES:
        module.bind_all()
