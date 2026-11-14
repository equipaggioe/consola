"""The database buttons against a canone VPS.

SSH is replaced: these cover which `database.py` commands Consola sends
and when it stops before sending them.
"""

import types
from pathlib import Path
from typing import cast

import pytest

from app.core import canone, catalog
from app.core.context import TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.registry import Capability
from app.core.tasks import database, vps_setup


def _ignore(*args: object, **kwargs: object) -> None:
    pass


def _vps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state: str) -> list[str]:
    """Return the commands the VPS receives, from a repo in `state`."""
    (tmp_path / "README.md").write_text(f"# demo\n\nEstado: {state}\n", encoding="utf-8")
    sent: list[str] = []

    def run(ctx: TaskContext, command: str) -> None:
        sent.append(command)

    def origin(root: Path) -> tuple[str, str]:
        return "equipaggio", "demo"

    def admin(ctx: TaskContext) -> types.SimpleNamespace:
        return entry

    entry = types.SimpleNamespace(run=run, remote=types.SimpleNamespace(host="vps"))
    monkeypatch.setattr(canone, "origin", origin)
    monkeypatch.setattr(vps_setup, "admin", admin)
    return sent


def _context(tmp_path: Path) -> TaskContext:
    return cast(
        TaskContext,
        types.SimpleNamespace(
            config=Config({}), root=tmp_path, step=_ignore, ok=_ignore, warn=_ignore, note=_ignore
        ),
    )


def test_rebuilding_the_vps_runs_database_py_step_by_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rebuilding the VPS empties, migrates and seeds, with mocks."""
    sent = _vps(monkeypatch, tmp_path, "en desarrollo")
    database.rebuild_db(_context(tmp_path), "remote", drop=False, partitions=False)
    program = "/usr/local/sbin/demo-database"
    assert sent == [
        f"{program} empty",
        f"{program} migrate",
        f"{program} seed",
        f"{program} seed --mock",
    ]


def test_a_repo_in_production_does_not_reach_the_vps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A repo in production stops before emptying or loading mocks."""
    sent = _vps(monkeypatch, tmp_path, "en producción")
    with pytest.raises(TaskError, match="producción"):
        database.rebuild_db(_context(tmp_path), "remote", drop=False, partitions=False)
    with pytest.raises(TaskError, match="producción"):
        database.run_mock_seeders(_context(tmp_path), "remote")
    assert sent == []


def test_a_repo_in_production_still_seeds_the_vps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The base seeders run in production too: they are idempotent."""
    sent = _vps(monkeypatch, tmp_path, "en producción")
    database.run_seeders(_context(tmp_path), "remote")
    assert sent == ["/usr/local/sbin/demo-database seed"]


@pytest.mark.parametrize(
    ("scope", "runs", "skips"),
    [
        ("local", {"drop", "partitions"}, {"empty"}),
        ("remote", {"empty"}, {"drop", "partitions"}),
    ],
)
def test_each_scope_runs_only_its_own_steps(scope: str, runs: set[str], skips: set[str]) -> None:
    """A step of the other scope does not run, even checked."""
    rebuild = Capability(
        id="rebuild_db",
        name="Reconstruir base",
        group="Base de datos",
        kind="destructive",
        axes=[catalog._scope_axis()],
        steps=catalog.REBUILD_DB_STEPS,
    )
    every = [step.id for step in catalog.REBUILD_DB_STEPS]
    kwargs = rebuild.kwargs_from({"options": {"scope": scope}, "steps": every})
    assert kwargs["scope"] == scope
    assert all(kwargs[step] for step in runs | {"migrate", "seeders", "mock_seeders"})
    assert not any(kwargs[step] for step in skips)
