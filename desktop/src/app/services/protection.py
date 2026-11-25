"""A guard per repository and per TARGET TYPE.

The problem is not pressing a button by accident but pressing it in the
wrong repo. And not all destructive actions are equally serious:
emptying a toy repo's artifact folder is redone with a build; deleting
the production VPS's database is not.

Three decisions hold the design up:

1. **The guard is per target type, not per button.** What matters is the
   blast radius: the VPS, the database, other repos. One button can
   touch two targets (`reinit_migrations` empties the database and
   deletes repo files), and one button can touch different targets by
   its parameters (`rebuild_db` against `local` stays on this machine;
   against `remote` it reaches the VPS).

2. **The switch lives in its own section, not the parameters panel.**
   Deliberately: a guard removed with the same gesture that presses Run
   becomes part of the gesture, and in two weeks it comes off unread.
   Here it is decided ONCE, when adding the repo. A switch touched every
   few months does not become a reflex.

It saves in `.consola/params.json` (`services/params_store.py`), not
`config.env`: the .env file is the DATA tasks need, such as the IP, the
user and the token, and no step ever reads a `PROTECT_*`. It is a
decision of the console about this repo, like the steps left checked in
a panel, and it goes where those go.

3. **What repeats is the written confirmation, and it verifies
   identity.** Typing `BORRAR` is right in any repo: the habit always
   hits and the check checks nothing. Typing the REPO'S NAME is right
   only in the repo one thinks is open: on a mistake, one's fingers type
   the other's name and the action does not run. The habit does not
   erode this check: it is what makes it work.

A dry run fires nothing. `clean_artifacts` and `sync_common_files` in
`dry_run` mode destroy nothing: asking for confirmation would be the
noise that wears out the real notice's signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.language import QT_TRANSLATE_NOOP


@dataclass(frozen=True)
class Target:
    """A type of thing a destructive action can break."""

    id: str  # how it saves in `.consola/params.json`
    # how it reads in the dialog: «el VPS», «la base de datos»
    label: str
    chip: str  # short label for the status bar: «VPS», «BD»
    setting_label: str  # how the switch reads in the Security section
    protected_by_default: bool
    why: str  # why that default, for the switch's tooltip


TARGETS: tuple[Target, ...] = (
    Target(
        "vps",
        QT_TRANSLATE_NOOP("protection", "el VPS"),
        QT_TRANSLATE_NOOP("protection", "VPS"),
        QT_TRANSLATE_NOOP("protection", "Proteger el VPS"),
        True,
        QT_TRANSLATE_NOOP("protection", "alcanza a una maquina remota y no hay deshacer"),
    ),
    Target(
        "db",
        QT_TRANSLATE_NOOP("protection", "la base de datos"),
        QT_TRANSLATE_NOOP("protection", "BD"),
        QT_TRANSLATE_NOOP("protection", "Proteger la base de datos"),
        True,
        QT_TRANSLATE_NOOP("protection", "los datos borrados no vuelven sin un backup"),
    ),
    Target(
        "other_repos",
        QT_TRANSLATE_NOOP("protection", "otros repositorios"),
        QT_TRANSLATE_NOOP("protection", "otros repos"),
        QT_TRANSLATE_NOOP("protection", "Proteger otros repos"),
        True,
        QT_TRANSLATE_NOOP(
            "protection", "escribe fuera de este repo, en carpetas que no estas mirando"
        ),
    ),
    Target(
        "local",
        QT_TRANSLATE_NOOP("protection", "archivos de este repo"),
        QT_TRANSLATE_NOOP("protection", "local"),
        QT_TRANSLATE_NOOP("protection", "Proteger archivos locales"),
        False,
        QT_TRANSLATE_NOOP(
            "protection", "apagado por defecto: un artefacto borrado se rehace con un build"
        ),
    ),
    Target(
        "origin",
        QT_TRANSLATE_NOOP("protection", "origin en GitHub"),
        QT_TRANSLATE_NOOP("protection", "origin"),
        QT_TRANSLATE_NOOP("protection", "Proteger origin (GitHub)"),
        False,
        QT_TRANSLATE_NOOP(
            "protection",
            "apagado por defecto: reescribe el historial que ven quienes clonaron o "
            "hicieron fork de este repo, pero no toca esta maquina ni el VPS",
        ),
    ),
)

_BY_ID = {t.id: t for t in TARGETS}


def get(target_id: str) -> Target | None:
    """Return the target with that id."""
    return _BY_ID.get(target_id)


# --- what each action breaks ---
#
# Only `kind='destructive'`. `purge_emulators` is not here: it is
# `scope='machine'` (it deletes AVDs and SDK images, which belong to no
# repo), so a per-repo switch would have no repo to belong to. It keeps
# its own written confirmation.


@dataclass(frozen=True)
class Rule:
    """An action's fixed targets, and those its parameters add."""

    always: tuple[str, ...] = ()
    # axis name -> {value: targets that value adds}
    when: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    # axis name -> values with which the action destroys nothing
    dry_run: dict[str, tuple[str, ...]] = field(default_factory=dict)


RULES: dict[str, Rule] = {
    "revoke_ssh": Rule(always=("vps",)),
    # Every level drops the VPS's database.
    "clean_vps": Rule(always=("vps", "db"), dry_run={"apply": ("dry_run",)}),
    "teardown_db": Rule(always=("db",)),
    # `local` stays on this machine; `remote` reaches the server. The
    # same button, two different blast radii.
    "rebuild_db": Rule(always=("db",), when={"scope": {"remote": ("vps",)}}),
    # It overwrites the whole local database with the dump. It has no
    # written confirmation of its own: the per-repo guard covers it
    # (ADR-0047).
    "restore_db": Rule(always=("db",)),
    # It touches two targets: it empties the local database's schema and
    # deletes the files in the open repo's `alembic/versions/`.
    "reinit_migrations": Rule(always=("db", "local")),
    "clean_artifacts": Rule(always=("local",), dry_run={"apply": ("dry_run",)}),
    "update_copies": Rule(always=("local",), dry_run={"apply": ("dry_run",)}),
    "sync_common_files": Rule(always=("other_repos",), dry_run={"apply": ("dry_run",)}),
    # `push` rewrites origin and leaves this machine as is; `reset`
    # discards this machine's commits and files.
    "git_force_push": Rule(always=("origin",)),
    "git_force_reset": Rule(always=("local",)),
}


def _chosen(payload: dict[str, Any], axis: str) -> set[str]:
    """Return what is checked on an axis, as a loose value or a list."""
    raw = (payload.get("options") or {}).get(axis)
    if isinstance(raw, list):
        return set(raw)
    return {raw} if raw else set()


def targets_of(capability_id: str, payload: dict[str, Any] | None = None) -> list[Target]:
    """Return what this run will break with these parameters.

    Empty = nothing.
    """
    rule = RULES.get(capability_id)
    if rule is None:
        return []
    payload = payload or {}

    for axis, harmless in rule.dry_run.items():
        if _chosen(payload, axis) & set(harmless):
            return []  # a dry run destroys nothing: nothing is asked

    ids = list(rule.always)
    for axis, mapping in rule.when.items():
        for value in _chosen(payload, axis):
            ids.extend(mapping.get(value, ()))

    seen: set[str] = set()
    output: list[Target] = []
    for tid in ids:
        target = _BY_ID.get(tid)
        if target is not None and tid not in seen:
            seen.add(tid)
            output.append(target)
    return output


def defaults() -> dict[str, Any]:
    """Return how a repo starts before it has said anything."""
    return {t.id: t.protected_by_default for t in TARGETS}


def state_from(stored: dict[str, Any] | None) -> dict[str, Any]:
    """Return the full state from what was saved, which may be partial.

    A target missing from the json falls to its default, protected
    except `local`: adding a new target cannot leave existing repos
    unprotected.
    """
    state = defaults()
    for tid, value in (stored or {}).items():
        if tid in _BY_ID:
            state[tid] = bool(value)
    return state


class Decision:
    """What the console does with a run before letting it start."""

    # it breaks nothing (or is a dry run): it runs without asking
    ALLOW = "allow"
    # it breaks something, but nothing protected: a repo reminder
    REMIND = "remind"
    # it touches a target protected in this repo: it does not run
    BLOCK = "block"


def decide(
    state: dict[str, Any], capability_id: str, payload: dict[str, Any] | None = None
) -> tuple[str, list[Target]]:
    """Return a run's decision and the targets that explain it.

    - `BLOCK`: a target in the blast radius is protected in this repo.
      The action does not run and the notice offers no way past it: the
      guard comes off in the Security section, once, with a cool head.
    - `REMIND`: the action destroys something but this repo protects
      none of those targets. A reminder of which repo this is, with
      Cancel and Continue and nothing else: no typed word or repo name.
    - `ALLOW`: nothing to destroy with these parameters, or it is a dry
      run.

    `state` is what `state_from` returns: `{target_id: bool}`.
    """
    targets = targets_of(capability_id, payload)
    if not targets:
        return Decision.ALLOW, []
    blocked = [t for t in targets if is_protected(state, t)]
    if blocked:
        return Decision.BLOCK, blocked
    return Decision.REMIND, targets


def is_protected(state: dict[str, Any], target: Target) -> bool:
    """Return whether this repo protects that target."""
    return bool(state.get(target.id, target.protected_by_default))


def repo_protections(state: dict[str, Any]) -> list[Target]:
    """Return all the targets this repo protects, regardless of action.

    The status bar's indicator summarizes it
    (`widgets/workspace_status_bar.py::WorkspaceStatusBar`).
    """
    return [t for t in TARGETS if is_protected(state, t)]
