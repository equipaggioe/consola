"""Canone's `verificar.py` and `copiar.py` against a fake canone.

Each is replaced by a script that prints its arguments and ends with a
code: these cover what runs and how the task ends.
"""

import sys
from pathlib import Path

import pytest

from app.services import envfile, toolchain
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.projects import Project
from app.services.tasks import utils


def _context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: list[str]) -> TaskContext:
    """Return the context of a repo, with its canone folder set."""

    def python() -> list[str]:
        return [sys.executable]

    def keep(msg: str, level: str) -> None:
        del level
        lines.append(msg)

    monkeypatch.setattr(toolchain, "python_cmd", python)
    repo = tmp_path / "demo"
    repo.mkdir()
    config = envfile.Config({"CANONE_DIR": str(tmp_path / "canone")})
    return TaskContext(
        "verify_canone", project=Project("demo", str(repo), ""), config=config, log_sink=keep
    )


def _verifier(tmp_path: Path, code: int, name: str = "verificar.py") -> None:
    program = tmp_path / "canone" / "scripts" / name
    program.parent.mkdir(parents=True)
    program.write_text(f"import sys\nprint(*sys.argv[1:])\nsys.exit({code})\n", encoding="utf-8")


def test_it_runs_on_the_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The local copy of canone checks the open repo."""
    _verifier(tmp_path, 0)
    lines: list[str] = []
    utils.verify_canone(_context(tmp_path, monkeypatch, lines))
    assert f"--repo {tmp_path / 'demo'}" in lines


def test_what_it_finds_fails_the_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Its code fails the task, after its lines reach the log."""
    _verifier(tmp_path, 1)
    lines: list[str] = []
    with pytest.raises(TaskError, match="codigo 1"):
        utils.verify_canone(_context(tmp_path, monkeypatch, lines))
    assert f"--repo {tmp_path / 'demo'}" in lines


def test_a_folder_that_is_not_canone_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without `verificar.py` it stops before running anything."""
    lines: list[str] = []
    with pytest.raises(TaskError, match="Carpeta de canone"):
        utils.verify_canone(_context(tmp_path, monkeypatch, lines))
    assert lines == []


@pytest.mark.parametrize(
    ("kwargs", "flags"),
    [
        ({}, ""),
        ({"accounts": True}, " --cuentas"),
        ({"accounts": True, "apply": True}, " --cuentas --aplicar"),
    ],
)
def test_the_copies_run_with_what_was_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kwargs: dict[str, bool], flags: str
) -> None:
    """A dry run passes no `--aplicar`."""
    _verifier(tmp_path, 0, "copiar.py")
    lines: list[str] = []
    utils.update_copies(_context(tmp_path, monkeypatch, lines), **kwargs)
    assert f"{tmp_path / 'demo'}{flags}" in lines


def test_copies_that_stop_fail_the_task(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The code of `copiar.py` fails the task."""
    _verifier(tmp_path, 1, "copiar.py")
    with pytest.raises(TaskError, match="codigo 1"):
        utils.update_copies(_context(tmp_path, monkeypatch, []), apply=True)
