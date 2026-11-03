from __future__ import annotations

from app.core.host import HOST

"""
RAM disponible en la maquina, para el indicador de la barra de estado.

Se pide sola, sin depender de psutil (`requirements.txt` no lo trae): en
Windows alcanza con `GlobalMemoryStatusEx`, en Linux/Mac con `/proc/meminfo`
(`HOST.memory`).
"""


def available_ram() -> tuple[float, float] | None:
    """RAM disponible y total, en GB. `None` si no se pudo consultar (Mac sin
    `/proc/meminfo`, por ejemplo: no vale la pena otra rama por tan poco)."""
    par = HOST.memory()
    if not par or not par[0] or not par[1]:
        return None
    disponible, total = par
    return disponible / (1024 ** 3), total / (1024 ** 3)
