"""The form of `.consola/config.env` and when it is up to date."""

from pathlib import Path

import pytest

from app.services import envfile
from app.services.errors import TaskError
from app.services.settings import Setting

FIELD = (Setting("HEALTH_TOKEN", "Credenciales", "health_token", secret=True),)


def test_a_rendered_file_is_current() -> None:
    """What `render_config` writes is already the schema's form."""
    text = envfile.render_config({"VPS_IP": "203.0.113.5", "HEALTH_TOKEN": "h"}, FIELD)
    assert envfile.is_current(text, FIELD)


def test_a_key_out_of_order_is_not_current() -> None:
    """A file with the right keys in another order needs rewriting."""
    text = envfile.render_config({"VPS_IP": "203.0.113.5"})
    assert not envfile.is_current("VPS_IP=203.0.113.5\n" + text)


def test_foreign_and_machine_keys_are_removed() -> None:
    """Foreign and machine keys are named and not written."""
    values = {"VPS_IP": "203.0.113.5", "OLD_KEY": "x", "CANONE_DIR": "E:/canone"}
    assert envfile.removed_keys(values) == ["CANONE_DIR", "OLD_KEY"]
    text = envfile.render_config(values)
    assert "OLD_KEY" not in text
    assert "CANONE_DIR" not in text
    assert "VPS_IP=203.0.113.5" in text


def test_the_repo_fields_are_not_removed() -> None:
    """A `Settings` field is the file's, not a foreign key."""
    assert envfile.removed_keys({"HEALTH_TOKEN": "h"}, FIELD) == []
    assert envfile.removed_keys({"HEALTH_TOKEN": "h"}) == ["HEALTH_TOKEN"]


def test_an_absent_file_has_no_text(tmp_path: Path) -> None:
    """Without `config.env` there is no text, and no error."""
    assert envfile.config_text(str(tmp_path)) is None


def test_an_unreadable_file_stops(tmp_path: Path) -> None:
    """A file that exists and cannot be read is not taken as empty."""
    path = Path(envfile.config_path(str(tmp_path)))
    path.parent.mkdir()
    path.write_bytes(b"VPS_IP=\xff\n")
    with pytest.raises(TaskError, match="No se puede leer"):
        envfile.config_text(str(tmp_path))


def _gitignore(repo: Path) -> Path:
    return repo / envfile.CONSOLA_DIR / ".gitignore"


def test_ensure_ignored_writes_the_data_and_the_captures(tmp_path: Path) -> None:
    """A new .gitignore ignores data and captures, not the camera."""
    envfile.ensure_ignored(str(tmp_path))
    assert _gitignore(tmp_path).read_text(encoding="utf-8") == (
        "config.env\nparams.json\nscreenshots/\npublishable/\n"
    )


def test_ensure_ignored_replaces_the_star_that_hid_the_camera(tmp_path: Path) -> None:
    """The `*` from before ADR-0087 goes: it also ignored the camera."""
    _gitignore(tmp_path).parent.mkdir()
    _gitignore(tmp_path).write_text("*\n", encoding="utf-8")
    envfile.ensure_ignored(str(tmp_path))
    assert "*" not in _gitignore(tmp_path).read_text(encoding="utf-8").splitlines()


def test_ensure_ignored_keeps_the_lines_the_repo_added(tmp_path: Path) -> None:
    """A line of the repo stays, and only the missing ones are added."""
    _gitignore(tmp_path).parent.mkdir()
    _gitignore(tmp_path).write_text("config.env\nnotas.txt\n", encoding="utf-8")
    envfile.ensure_ignored(str(tmp_path))
    assert _gitignore(tmp_path).read_text(encoding="utf-8") == (
        "config.env\nnotas.txt\nparams.json\nscreenshots/\npublishable/\n"
    )


def test_ensure_ignored_leaves_a_complete_file_alone(tmp_path: Path) -> None:
    """With every line present, the file is not rewritten."""
    envfile.ensure_ignored(str(tmp_path))
    before = _gitignore(tmp_path).stat().st_mtime_ns
    envfile.ensure_ignored(str(tmp_path))
    assert _gitignore(tmp_path).stat().st_mtime_ns == before
