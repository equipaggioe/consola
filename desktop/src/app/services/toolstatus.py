"""Which development tools this machine has, by looking at the disk.

It feeds the status bar indicators. It is the cheap version of the
question on purpose: it only checks that the binary exists and where,
without running `java -version` or `flutter doctor`. Asking each tool
takes seconds and would block the interface on each refresh, and the
file is enough for what the indicator says: present or not.

That is why there is no «environment status» button either: this checks
itself when the workspace opens and after each install, not when someone
remembers to press it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.services import android
from app.services.errors import TaskError
from app.services.host import HOST
from app.services.process import which_any


@dataclass(frozen=True)
class Tool:
    """A tool that was searched for, with the result of the search."""

    key: str
    label: str
    path: str = ""  # empty = not found
    hint: str = ""  # what to do about it, for the tooltip

    @property
    def found(self) -> bool:
        """Return whether the tool was found."""
        return bool(self.path)

    @property
    def detail(self) -> str:
        """Return the path or the hint, for the tooltip."""
        return (
            self.path
            if self.found
            else (self.hint or QCoreApplication.translate("Tool", "No encontrado."))
        )


def _binary(name: str) -> list[str]:
    """Return the names an executable can have on this system."""
    return HOST.executable_names(name)


def _under(home: str, *parts: str) -> str:
    """Find the executable inside a folder declared by a variable.

    It looks here before PATH because a fresh install writes the
    variable at the same time as the path, so the indicator turns green
    without restarting Consola.
    """
    root = (os.environ.get(home) or "").strip()
    if not root:
        return ""
    for name in _binary(parts[-1]):
        candidate = Path(root).joinpath(*parts[:-1], name)
        if candidate.is_file():
            return str(candidate)
    return ""


def _java() -> Tool:
    path = _under("JAVA_HOME", "bin", "java") or (which_any(_binary("java")) or "")
    return Tool(
        "java",
        QCoreApplication.translate("toolstatus", "Java"),
        path,
        hint=QCoreApplication.translate(
            "toolstatus", "Instala un JDK 17 o superior: sdkmanager no corre sin el."
        ),
    )


def _git() -> Tool:
    return Tool(
        "git",
        QCoreApplication.translate("toolstatus", "Git"),
        which_any(_binary("git")) or "",
        hint=QCoreApplication.translate("toolstatus", "Flutter necesita Git para actualizarse."),
    )


def _android() -> Tool:
    try:
        path = android.resolve_sdk().tool("sdkmanager")
    except TaskError:
        path = ""
    return Tool(
        "android",
        QCoreApplication.translate("toolstatus", "SDK Android"),
        path,
        hint=QCoreApplication.translate(
            "toolstatus", 'Corre "Herramientas Android" para instalarlo.'
        ),
    )


def _flutter() -> Tool:
    path = _under("FLUTTER_HOME", "bin", "flutter") or (which_any(_binary("flutter")) or "")
    return Tool(
        "flutter",
        QCoreApplication.translate("toolstatus", "Flutter"),
        path,
        hint=QCoreApplication.translate("toolstatus", 'Corre "SDK Flutter" para instalarlo.'),
    )


def detect() -> list[Tool]:
    """Return the state of the four tools, in dependency order."""
    return [_java(), _git(), _android(), _flutter()]
