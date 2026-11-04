"""Level 0 of Consola: the plumbing the capabilities use inside.

None of this is a button. Each module solves one class of problem. It
does not import Qt, print to stdout, read stdin or exit the process: it
reports through the `TaskContext` it receives and raises `TaskError`
when it cannot go on (ADR-0005).

    errors      TaskError, Cancelled, MissingConfig
    context     TaskContext: log, run, confirm, ask, note, cancel
    process     run external binaries: stream, capture, kill
    envfile     .consola/config.env: read, write, typed access
    settings    schema of the configuration keys
    files       compare, copy, delete and revert files
    ports       choose a free port
    ssh         Remote, remote commands, scp, tunnels, keys
    vps         deployment paths, systemd, journal, packages
    database    resolve the local base or the tunneled one
    runner      where project code runs: local or VPS venv
    versioning  read and bump a manifest's version
    toolchain   flutter, flet, pnpm, venv, framework detection
    android     SDK, AVDs, system images and emulators
    targets     discover subprojects inside the open repo
    registry    catalog of capabilities
    projects    the Project dataclass; the UI handles the list
"""

from __future__ import annotations

from app.core.context import Level, TaskContext
from app.core.envfile import Config
from app.core.errors import Cancelled, MissingConfig, TaskError
from app.core.projects import Project
from app.core.registry import AxisDef, Capability, Registry, Step, registry
from app.core.ssh import Remote

__all__ = [
    "Cancelled",
    "MissingConfig",
    "TaskError",
    "Level",
    "TaskContext",
    "Config",
    "Project",
    "Registry",
    "registry",
    "Capability",
    "AxisDef",
    "Step",
    "Remote",
]
