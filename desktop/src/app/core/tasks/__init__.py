"""Levels 1 and 2: the capabilities with a real body.

Each module groups the atomic capabilities of one rail group and the
composites that chain them. The rule for when an inner step becomes an
atomic capability with its own button is in ADR-0004: it splits off if
rerunning it alone makes sense.

Nothing here reimplements plumbing: it all rests on `core/` (level 0).
That is why most atomic capabilities are three to ten lines.
"""

from __future__ import annotations

from app.core.tasks import (
    builders,
    database,
    emulators,
    git,
    images,
    launchers,
    utils,
    vps_ops,
    vps_release,
    vps_server,
    vps_setup,
)

MODULES = (
    launchers,
    builders,
    images,
    emulators,
    git,
    vps_ops,
    vps_server,
    vps_setup,
    vps_release,
    database,
    utils,
)

__all__ = [
    "MODULES",
    "bind_all",
    "builders",
    "database",
    "emulators",
    "git",
    "images",
    "launchers",
    "utils",
    "vps_ops",
    "vps_release",
    "vps_server",
    "vps_setup",
]


def bind_all() -> None:
    """Give a body to every implemented capability of the catalog.

    Call it after `load_catalog()`: the catalog declares the shape, and
    this replaces the stub with the function. What does not appear here
    stays a stub, and the UI draws it as one.
    """
    for module in MODULES:
        module.bind_all()
