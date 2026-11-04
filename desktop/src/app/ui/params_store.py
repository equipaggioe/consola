"""Parameters chosen in an action's panel, per repository and button.

**They live in the repo**, in `.consola/params.json`, next to
`config.env`. Not in QSettings: a global machine table indexed by path
breaks when the folder moves or is renamed, leaves garbage when the repo
is deleted and cannot be looked at or edited by hand.

`.consola/` ignores itself in git (`core/envfile.py`), so the file is
not committed: it stays this machine's preference, only saved where it
belongs.

The exception is capabilities with `scope='machine'`, such as installing
an SDK: those happen to the machine, not the repo. A repo has no say
about where the Android SDK goes, so **they stay in QSettings**. The
rule is: repo decision, repo file; machine decision, QSettings.

Two accesses dominate performance, and both are hot:

- `ui/readiness.py::missing_keys` calls `stored_steps` once per
  capability on each repo change (dozens of reads in a row).
- `ui/params_panel.py::_refresh_summary` calls `save` on each keystroke
  of a text field.

So the file reads whole ONCE per repo into an in-memory cache, and
writes gather on a short timer instead of hitting disk per keystroke.
`flush()` forces the write; the window's closing calls it.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, cast

from PySide6.QtCore import QSettings, QTimer

from app.core.envfile import CONSOLA_DIR, ensure_ignored

_FILE_NAME = "params.json"
# The repo's guards (`core/protection.py`) share the file with each
# button's parameters, under a key no `capability_id` can have: an id is
# a Python identifier and has no '@'. They share a file because they
# share a nature, console decisions about THIS repo and not data tasks
# consume, and so they also share the cache, the atomic write and the
# timer.
_PROTECTION_KEY = "@protection"
# A repo's open action tabs are another console decision about THIS
# repo, which buttons were left at hand, so they go to the same file
# under another key with '@' outside the ids' space.
_TABS_KEY = "@tabs"
# The repo's color is the third console decision about THIS repo: it is
# chosen per repo and travels with it, not with the machine that opened
# it. It saves the theme's key (`ui/palettes.py`), not a hex.
_THEME_KEY = "@theme"
# namespace of what DOES stay in QSettings: `scope='machine'`
# capabilities (`_machine_key`)
_QSETTINGS_PREFIX = "params"
_FLUSH_MS = 500

# normalized repo -> {capability_id: state}. The normalized path is both
# key and write target: `normcase` only lowers capitals on Windows, and
# that path opens the same file.
_cache: dict[str, dict[str, Any]] = {}
_dirty: set[str] = set()
_timer: QTimer | None = None


def _norm(repo_path: str) -> str:
    return os.path.normcase(os.path.normpath(repo_path or ""))


def _file(repo_norm: str) -> str:
    return os.path.join(repo_norm, CONSOLA_DIR, _FILE_NAME)


def _is_machine(capability_id: str) -> bool:
    from app.core.registry import registry

    cap = registry.get_capability(capability_id)
    return cap is not None and cap.is_machine_wide


def _machine_key(capability_id: str) -> str:
    return f"{_QSETTINGS_PREFIX}/machine/{capability_id}"


# --- configuration keys that belong to the machine ---
#
# `Setting.scope='machine'` (`core/settings.py`): where an executable
# got installed does not belong to the open repo, so it does not go in
# its `config.env`. Same rule as `scope='machine'` capabilities, same
# place: QSettings.


def machine_env() -> dict[str, Any]:
    """Return the machine values, to mix them with the repo's."""
    from app.core.settings import machine_settings

    settings = QSettings()
    return {s.key: str(settings.value(f"machine/{s.key}", "") or "") for s in machine_settings()}


def save_machine_env(values: dict[str, Any]) -> None:
    """Write the machine keys in `values`; ignore the rest."""
    from app.core.settings import machine_settings

    settings = QSettings()
    for s in machine_settings():
        if s.key in values:
            settings.setValue(f"machine/{s.key}", values[s.key])


# --- reading ---


def _read(repo_path: str) -> dict[str, Any]:
    """Return all that is saved for a repo, cached. It never raises.

    A file broken by hand counts as nothing there, and the first save
    remakes it.
    """
    key = _norm(repo_path)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    data: dict[str, Any] = {}
    try:
        with open(_file(key), "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            data = {k: v for k, v in loaded.items() if isinstance(v, dict)}
    except (OSError, ValueError, UnicodeDecodeError):
        data = {}

    _cache[key] = data
    return data


def load(repo_path: str, capability_id: str) -> dict[str, Any] | None:
    """Return what is saved for that button in that repo, or None."""
    if _is_machine(capability_id):
        raw = QSettings().value(_machine_key(capability_id), "")
        if not raw:
            return None
        try:
            state = json.loads(cast(str, raw))
        except (TypeError, ValueError):
            return None
        return state if isinstance(state, dict) else None

    state = _read(repo_path).get(capability_id)
    return state if isinstance(state, dict) else None


def load_protection(repo_path: str) -> dict[str, Any]:
    """Return the repo's guards, completed with their defaults.

    A repo that never touched them starts protected in all but `local`
    (`core/protection.py`), so the file need not say anything.
    """
    from app.core import protection

    return protection.state_from(_read(repo_path).get(_PROTECTION_KEY))


def save_protection(repo_path: str, state: dict[str, Any]) -> None:
    """Save the whole guards, not just the one touched.

    Whole because the state is five checkboxes that read together, and
    the file stays with all five written even if one has its default: a
    guard absent from the file reads worse than one that says `false`.
    """
    key = _norm(repo_path)
    data = _read(repo_path)
    clean = {k: bool(v) for k, v in state.items()}
    if data.get(_PROTECTION_KEY) == clean:
        return
    data[_PROTECTION_KEY] = clean
    _dirty.add(key)
    _schedule()


def load_tabs(repo_path: str) -> list[str]:
    """Return the `capability_id` of the open action tabs, in order.

    Empty if the repo never opened any or the file does not say.
    """
    raw = _read(repo_path).get(_TABS_KEY)
    if not isinstance(raw, dict):
        return []
    opened = raw.get("open")
    return [str(x) for x in opened] if isinstance(opened, list) else []


def save_tabs(repo_path: str, capability_ids: list[str]) -> None:
    """Save which action tabs stay open, in order, to reopen them.

    They reopen as they were on the next start (`ui/tab_panel.py`).
    """
    key = _norm(repo_path)
    data = _read(repo_path)
    clean = {"open": [str(x) for x in capability_ids]}
    if data.get(_TABS_KEY) == clean:
        return
    data[_TABS_KEY] = clean
    _dirty.add(key)
    _schedule()


def load_theme(repo_path: str) -> str:
    """Return the repo's color theme key, or empty if it chose none.

    `ui/palettes.py` translates it to colors; here it is a string and
    nothing else. Empty is no error: a fresh clone brings no `.consola`,
    and whoever opens it gives it the first free theme
    (`ui/project_store.py`).
    """
    raw = _read(repo_path).get(_THEME_KEY)
    if not isinstance(raw, dict):
        return ""
    key = raw.get("key")
    return key if isinstance(key, str) else ""


def save_theme(repo_path: str, theme: str) -> None:
    """Save the repo's color theme key."""
    key = _norm(repo_path)
    data = _read(repo_path)
    # Wrapped in an object like the other '@' keys: `_read` discards
    # what is not an object, so a loose string was lost on rereading.
    clean = {"key": str(theme)}
    if data.get(_THEME_KEY) == clean:
        return
    data[_THEME_KEY] = clean
    _dirty.add(key)
    _schedule()


def stored_steps(repo_path: str, capability_id: str) -> list[str] | None:
    """Return the saved active steps.

    They compute outside the panel what an action lacks to run without
    opening the tab (`ui/readiness.py`).
    """
    state = load(repo_path, capability_id)
    if not state:
        return None
    steps = state.get("steps")
    return list(steps) if isinstance(steps, list) else None


# --- writing ---


def save(repo_path: str, capability_id: str, state: dict[str, Any]) -> None:
    """Save what was chosen for that button in that repo."""
    if _is_machine(capability_id):
        QSettings().setValue(_machine_key(capability_id), json.dumps(state, ensure_ascii=False))
        return

    key = _norm(repo_path)
    data = _read(repo_path)
    if data.get(capability_id) == state:
        # a keystroke that changed nothing does not dirty the file
        return
    data[capability_id] = state
    _dirty.add(key)
    _schedule()


def clear(repo_path: str, capability_id: str) -> None:
    """Forget what was saved for that button in that repo."""
    if _is_machine(capability_id):
        QSettings().remove(_machine_key(capability_id))
        return
    key = _norm(repo_path)
    if _read(repo_path).pop(capability_id, None) is not None:
        _dirty.add(key)
        _schedule()


def _schedule() -> None:
    """Gather a burst of keystrokes' writes into a single one."""
    global _timer
    if _timer is None:
        _timer = QTimer()
        _timer.setSingleShot(True)
        _timer.setInterval(_FLUSH_MS)
        _timer.timeout.connect(flush)
    _timer.start()


def flush() -> None:
    """Write what is pending to disk.

    The timer and the window's closing call it
    (`ui/main_window.py::closeEvent`), so the last changes are not lost
    if it closes within the timer's window.
    """
    for key in list(_dirty):
        _dirty.discard(key)
        _write(key, _cache.get(key) or {})


def _write(repo_norm: str, data: dict[str, Any]) -> None:
    """Write atomically: build it alongside and rename over.

    It is ONE file per repo, not a key per button: a cut mid-write would
    take all the repo's parameters, not one. `os.replace` is atomic on
    one volume, on Windows too.
    """
    path = _file(repo_norm)
    folder = os.path.dirname(path)
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".params-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        # A repo on a disconnected or read-only disk should not bring
        # the interface down: what was chosen stays in the cache and
        # holds for this session.
        return
    ensure_ignored(repo_norm)


def forget(repo_path: str) -> None:
    """Release the cache of a repo removed from the tabs."""
    key = _norm(repo_path)
    if key in _dirty:
        _dirty.discard(key)
        _write(key, _cache.get(key) or {})
    _cache.pop(key, None)
