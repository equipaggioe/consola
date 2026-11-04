"""Available RAM on the machine, for the status bar indicator.

It needs no psutil: Windows has `GlobalMemoryStatusEx` and Linux has
`/proc/meminfo` (`HOST.memory`).
"""

from __future__ import annotations

from app.core.host import HOST


def available_ram() -> tuple[float, float] | None:
    """Return available and total RAM in GB, or `None` if unknown."""
    par = HOST.memory()
    if not par or not par[0] or not par[1]:
        return None
    available, total = par
    return available / (1024**3), total / (1024**3)
