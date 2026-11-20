"""The set of repositories open as top-level tabs.

The first time Consola opens there are none: the bar starts empty and
the first is added with «+». From then on the whole list is saved, path
and name, so the UI starts as it was left: adding, removing and
reordering survive a restart.

**This DOES go in QSettings**, unlike each action's parameters, which
live in the repo (`services/params_store.py`). The rule is whose
decision it is: which repos are open in tabs is a decision of THIS
machine, since a repo cannot know it is on your bar, while how the steps
of an action stayed checked is a decision about THAT repo.

**Color does not go here**: it is a decision about THAT repo, so it
lives in its `.consola/params.json` and travels with it. It is read on
load and attached to each `Project` (`_resolve_themes`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QSettings

from app.services import palettes, params_store
from app.services.projects import Project

_KEY = "projects/list"


def identity(path: str) -> str:
    """Return a repo's stable key: its normalized path.

    It is the identity of everything indexed by repo, such as the open
    workspace (`windows/main_window.py`) and the parameter cache
    (`services/params_store.py`), because the same folder written with
    reversed slashes, another case or a final separator has to count as
    one repo.
    """
    return os.path.normcase(os.path.normpath(path or ""))


def display_path(path: str) -> str:
    """Return how a path is saved and shown.

    Forward slashes, no final separator.

    It normalizes without destroying the capitals the user sees.
    """
    return os.path.normpath(path or "").replace(os.sep, "/")


def _to_dict(p: Project) -> dict[str, Any]:
    return {"name": p.name, "path": p.path}


def _from_dict(d: dict[str, Any]) -> Project | None:
    """Return an entry of the saved list.

    The theme comes later, from the repo.
    """
    try:
        path = display_path(str(d["path"]))
    except (KeyError, TypeError):
        return None
    if not path or path == ".":
        return None
    return Project(str(d.get("name") or Path(path).name), path, "")


def _resolve_themes(projects: list[Project]) -> list[Project]:
    """Give each repo its saved theme, or the first free one.

    Without a saved theme there are two cases and both are the same: a
    repo opened before themes existed, and a freshly cloned one with no
    `.consola` yet. Both choose as when adding with «+», the first theme
    no other open repo uses, and it is saved at once so the next start
    finds it.
    """
    used: list[str] = []
    for p in projects:
        saved = params_store.load_theme(p.path)
        if saved not in palettes.THEMES:
            saved = palettes.first_free(used)
            params_store.save_theme(p.path, saved)
        p.theme = saved
        used.append(saved)
    return projects


def dedupe(projects: list[Project]) -> list[Project]:
    """Keep one repo per folder; the first wins.

    Two tabs of the same folder would be two workspaces writing the same
    `.consola/params.json`, and the last to save would silently
    overwrite the other's choices.
    """
    seen: set[str] = set()
    unique = []
    for p in projects:
        key = identity(p.path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def load() -> list[Project]:
    """Return the saved repos in order. Empty the first time."""
    raw = QSettings().value(_KEY, "")
    if not raw:
        return []
    try:
        data = json.loads(cast(str, raw))
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return _resolve_themes(
        dedupe([p for p in (_from_dict(d) for d in data if isinstance(d, dict)) if p])
    )


def save(projects: list[Project]) -> None:
    """Save the list of open repos."""
    QSettings().setValue(
        _KEY, json.dumps([_to_dict(p) for p in dedupe(projects)], ensure_ascii=False)
    )


def clear() -> None:
    """Leave the bar empty, like the first time."""
    QSettings().remove(_KEY)
