"""Persistent environment variables, per user and without admin rights.

Consola is meant for Linux and has to work the same on Windows, so the
environment is written in the same conceptual way on both: a delimited
block inside the shell profile on POSIX, and `HKCU/Environment` on
Windows. Never at system level, which demands an elevated console and
dirties the whole machine for what is in practice a single-user install.

The delimited block is rewritten whole each time, so reinstalling leaves
no duplicated exports or dangling old paths.
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.services.context import TaskContext
from app.services.host import HOST

BEGIN = "# >>> consola >>>"
END = "# <<< consola <<<"
_HEADER = "# Bloque gestionado por Consola: se reescribe completo, no lo edites a mano."
_EXPORT = re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

PathFilter = Callable[[str], bool]


def profile_path() -> Path:
    """Return the startup file of the user's shell."""
    shell = (os.environ.get("SHELL") or "").strip()
    return Path.home() / (".zshrc" if shell.endswith("zsh") else ".bashrc")


def configure(
    ctx: TaskContext,
    *,
    variables: Mapping[str, str] | None = None,
    path_add: Iterable[Path | str] = (),
    path_drop: PathFilter | None = None,
) -> None:
    """Persist variables and paths in the user's environment.

    `path_drop` decides which old PATH entries are discarded: that
    allows reinstalling elsewhere without pointing to the old folder.
    Besides writing them, it applies them to the current process, so
    Consola finds what was just installed without restarting.
    """
    values = dict(variables or {})
    added = [str(Path(p)) for p in path_add]

    _STORES[HOST.env_store](ctx, values, added, path_drop)

    _apply_to_process(values, added)


def _apply_to_process(variables: Mapping[str, str], path_add: list[str]) -> None:
    """Apply to the live process.

    Otherwise Consola would need a restart.

    It is what turns the status bar indicators green when the install
    ends instead of on the next start.
    """
    for name, value in variables.items():
        os.environ[name] = value
    separator = os.pathsep
    current = [p for p in os.environ.get("PATH", "").split(separator) if p]
    for entry in path_add:
        if entry not in current:
            current.append(entry)
    os.environ["PATH"] = separator.join(current)


# --- POSIX ---


def _configure_posix(
    ctx: TaskContext, variables: dict[str, str], path_add: list[str], path_drop: PathFilter | None
) -> None:
    profile = profile_path()
    stored, dirs = read_block(profile)

    kept = [d for d in dirs if not (path_drop and path_drop(d))]
    removed = len(dirs) - len(kept)
    for entry in path_add:
        if entry not in kept:
            kept.append(entry)

    stored.update(variables)
    _write_block(profile, stored, kept)

    for name, value in variables.items():
        ctx.ok(f"{name} = {value}")
    if removed:
        ctx.info(
            QCoreApplication.translate(
                "userenv", "Se quitaron {0} ruta(s) anteriores del PATH."
            ).format(removed)
        )
    ctx.ok(QCoreApplication.translate("userenv", "Perfil actualizado: {0}").format(profile))
    ctx.info(
        QCoreApplication.translate(
            "userenv", "Abre una terminal nueva para que el PATH se actualice ahi."
        )
    )


def read_block(profile: Path) -> tuple[dict[str, str], list[str]]:
    """Return the variables and PATH entries in Consola's block.

    It reads before writing because the block is shared: rewriting it
    blindly for one SDK would erase what another left.
    """
    variables: dict[str, str] = {}
    dirs: list[str] = []
    if not profile.is_file():
        return variables, dirs

    text = profile.read_text(encoding="utf-8", errors="replace")
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < start:
        return variables, dirs

    for line in text[start:end].splitlines():
        match = _EXPORT.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2).strip().strip('"')
        if name == "PATH":
            dirs.extend(p for p in raw.split(":") if p and p != "$PATH")
        else:
            variables[name] = raw
    return variables, dirs


def _write_block(profile: Path, variables: Mapping[str, str], dirs: list[str]) -> None:
    lines = [BEGIN, _HEADER]
    lines += [f'export {name}="{value}"' for name, value in variables.items()]
    if dirs:
        lines.append('export PATH="$PATH:' + ":".join(dirs) + '"')
    lines.append(END)
    block = "\n".join(lines) + "\n"

    text = profile.read_text(encoding="utf-8", errors="replace") if profile.is_file() else ""
    start, end = text.find(BEGIN), text.find(END)
    if start >= 0 and end > start:
        text = text[:start] + block + text[end + len(END) :].lstrip("\n")
    else:
        prefix = text.rstrip("\n") + "\n\n" if text.strip() else ""
        text = prefix + block

    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(text, encoding="utf-8", newline="\n")


# --- Windows ---

_SYSTEM_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _configure_windows(
    ctx: TaskContext, variables: dict[str, str], path_add: list[str], path_drop: PathFilter | None
) -> None:
    winreg = _winreg()

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_WRITE
    ) as key:
        for name, value in variables.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            ctx.ok(f"{name} = {value}")

        current, kind = _query(key, "Path")
        entries = [e for e in current.split(";") if e.strip()]
        kept = [e for e in entries if not (path_drop and path_drop(e))]
        removed = len(entries) - len(kept)
        for entry in path_add:
            if entry not in kept:
                kept.append(entry)

        if kept != entries:
            # Always through the registry and never `setx`: setx
            # truncates any value over 1024 characters, and a real PATH
            # exceeds that.
            winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, ";".join(kept))
            if removed:
                ctx.info(
                    QCoreApplication.translate(
                        "userenv", "Se quitaron {0} ruta(s) anteriores del PATH de usuario."
                    ).format(removed)
                )
            ctx.ok(QCoreApplication.translate("userenv", "PATH de usuario actualizado."))
        else:
            ctx.ok(
                QCoreApplication.translate("userenv", "El PATH de usuario ya estaba configurado.")
            )

    _broadcast_change()
    _warn_system_path(ctx, path_drop)


def _winreg() -> Any:
    """Return `winreg`: it and its stubs exist only on Windows."""
    return importlib.import_module("winreg")


def _query(key: Any, name: str) -> tuple[str, int | None]:
    winreg = _winreg()

    try:
        value, kind = winreg.QueryValueEx(key, name)
        return str(value or ""), kind
    except FileNotFoundError:
        return "", None


def _warn_system_path(ctx: TaskContext, path_drop: PathFilter | None) -> None:
    """Warn if the system PATH has old entries that beat the new ones.

    Windows builds the process's PATH with the system's first, so an
    entry left by an earlier `setx /M` install beats what was just
    written in the user's. Reading it needs no rights; cleaning it does,
    so it only reports.
    """
    if path_drop is None:
        return
    winreg = _winreg()

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYSTEM_ENV_KEY, 0, winreg.KEY_READ) as key:
            current, _ = _query(key, "Path")
    except OSError:
        return

    stale = [e for e in current.split(";") if e.strip() and path_drop(e)]
    if not stale:
        return
    ctx.warn(
        QCoreApplication.translate(
            "userenv", "El PATH del sistema todavia tiene rutas anteriores, y tienen prioridad:"
        )
    )
    for entry in stale:
        ctx.warn(f"  {entry}")
    ctx.warn(
        QCoreApplication.translate(
            "userenv", "Quitalas desde Variables de entorno del sistema (requiere administrador)."
        )
    )


def _broadcast_change() -> None:
    """Tell Windows the environment changed, for new windows to see it.

    Without this, terminals opened after the change keep the old PATH
    until signing out.
    """
    try:
        import ctypes

        getattr(ctypes, "windll").user32.SendMessageTimeoutW(
            0xFFFF,  # HWND_BROADCAST
            0x001A,  # WM_SETTINGCHANGE
            0,
            "Environment",
            0x0002,
            5000,
            None,
        )
    except (AttributeError, OSError):
        pass


# One per value of `HOST.env_store`.
_STORES = {"profile": _configure_posix, "registry": _configure_windows}
