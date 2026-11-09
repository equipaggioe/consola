"""The form of `.consola/config.env` and when it is up to date."""

from pathlib import Path

import pytest

from app.core import envfile
from app.core.errors import TaskError
from app.core.settings import Setting

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
