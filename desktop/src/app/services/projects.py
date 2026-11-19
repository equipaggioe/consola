"""The `Project` dataclass.

There is no factory list of repos. The first time Consola opens, the tab
bar is empty and the first repo is added with «+»;
`services/project_store.py` saves what gets added.

`theme` is a key (`blue`, `coral`), not a color: the repo picks a theme
and the whole ladder of backgrounds of its workspace comes from it
(`services/palettes.py`). Saving the key and not the hex lets the recipe
change without repainting each saved repo. The UI resolves it, since
`services` does not import `ui`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Project:
    """A repository open in Consola."""

    name: str
    path: str
    theme: str  # key of a palette in `services/palettes.py`
