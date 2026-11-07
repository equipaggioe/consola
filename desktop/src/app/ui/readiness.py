"""Which actions can run without opening their tab."""

from __future__ import annotations

from typing import Any

from app.core import envfile, targets
from app.core.catalog import applicable_ids, for_project
from app.core.projects import Project
from app.core.registry import AxisDef, Capability, registry
from app.core.settings import required_keys_for
from app.ui import params_store


def missing_keys(capability: Capability, env: dict[str, str], repo_path: str) -> list[str]:
    """Return what an action lacks to run without opening the tab.

    Running at once, the search's ▶ button, uses the parameters saved
    for that button in that repo, so it looks at exactly what those
    parameters will run: steps turned off cannot claim keys. With
    nothing saved all steps count, which is what would run by default.

    The final question goes to a `Config`, like
    `ui/params_panel.py::_missing_keys`: a key with a fixed default
    (`SERVER_DIR='server'`) or a dynamic one (`DB_USER` from the repo's
    name) resolves by itself when running. Looking at the field's raw
    text, ▶ marked it as missing while the panel accepted it.
    """
    active = params_store.stored_steps(repo_path, capability.id)
    # Steps this repo lacks, such as the migrations of a repo without
    # Alembic, claim no keys either: they neither draw nor run.
    capability = for_project(capability, repo_path)
    needed = set(required_keys_for(capability.id))
    state = params_store.load(repo_path, capability.id) or {}
    scope = ""
    for axis in capability.axes:
        if axis.requires_env:
            needed |= axis.keys_for(_chosen(axis, state))
        if axis.name == "scope":
            scope = _chosen(axis, state)[0]
    for step in registry.resolve_steps(capability):
        if active is not None and step.optional and step.id not in active:
            continue
        if not step.applies(scope):
            continue
        needed |= step.requires_env
        needed |= set(required_keys_for(step.id))
    config = envfile.Config(env, repo_name=envfile.repo_name_of(repo_path))
    return [k for k in needed if not config.get(k)]


def _chosen(axis: AxisDef, state: dict[str, Any]) -> list[str]:
    """Return the axis values that would run: saved, or defaults."""
    saved = (state.get("variants" if axis.is_multi else "options") or {}).get(axis.name)
    if saved is not None:
        return list(saved) if isinstance(saved, list) else [saved]
    if axis.is_multi:
        return [v for v in axis.values if axis.starts_checked(v)]
    return [axis.initial]


def ready_ids(project: Project | None) -> set[str]:
    """Return the ids of the actions that can run now on `project`.

    They use its saved `.consola/config.env` and saved parameters. The ▶
    of each row of the menu bar search shows it.

    With no repo open nothing is ready, not even actions that ask for no
    key: there is nothing to run them on. Counting them left the menu
    with 22 actions marked ready while their menus were disabled.
    """
    if project is None:
        return set()
    env = envfile.load_config(project.path)
    path = project.path
    # All capabilities resolve against the SAME repo, and each one
    # walked it whole again: `one_scan` shares a single walk among them
    # (`core/targets.py`).
    with targets.one_scan():
        applicable = applicable_ids(path)
        return {
            cap.id
            for cap in registry.get_all()
            if cap.id in applicable and not missing_keys(cap, env, path)
        }
