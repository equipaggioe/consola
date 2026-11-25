"""The code that registers the superadmin: `SETUP_CODE`, or a new one.

SSH is replaced: these cover what is kept in config.env and what the
VPS receives.
"""

import base64
import re
import types
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from app.services import canone, envfile
from app.services.context import TaskContext
from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.tasks import vps_setup

CONFIG_PY = '''
class Settings(BaseSettings):
    """Every field is required and has no default."""

    database_url: str
    health_token: str
    setup_code: str
'''


def _ignore(*args: object, **kwargs: object) -> None:
    pass


def _repo(tmp_path: Path) -> None:
    folder = tmp_path / "server" / "src" / "app"
    folder.mkdir(parents=True)
    (folder / "config.py").write_text(CONFIG_PY, encoding="utf-8")


def _vps(monkeypatch: pytest.MonkeyPatch, stored: Sequence[str] = ()) -> list[str]:
    """Return the input of each command the VPS receives."""
    sent: list[str] = []

    def run(ctx: TaskContext, command: str, *, text: str = "") -> None:
        sent.append(text)

    def capture(command: str) -> str:
        asked = command.partition(" in ")[2].partition(";")[0].split()
        return "\n".join(f for f in asked if f in stored)

    entry = types.SimpleNamespace(
        run=run, capture=capture, remote=types.SimpleNamespace(host="vps")
    )
    monkeypatch.setattr(canone, "origin", lambda root: ("equipaggio", "demo"))
    monkeypatch.setattr(vps_setup, "admin", lambda ctx: entry)
    monkeypatch.setattr(vps_setup, "_upload", lambda ctx, entry: "/tmp/consola-canone/infra")
    monkeypatch.setattr(vps_setup, "_cleanup", _ignore)
    return sent


def _context(tmp_path: Path, notes: list[str], **values: str) -> TaskContext:
    return cast(
        TaskContext,
        types.SimpleNamespace(
            config=Config({"SERVER_DIR": "server", **values}),
            root=tmp_path,
            ok=_ignore,
            guard=_ignore,
            note=notes.append,
            warn=_ignore,
            info=_ignore,
        ),
    )


def test_an_empty_setup_code_is_generated_kept_and_shown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Six digits land in config.env, in the log and on the VPS."""
    _repo(tmp_path)
    sent = _vps(monkeypatch)
    notes: list[str] = []
    vps_setup.load_setup_code(_context(tmp_path, notes))
    code = envfile.load_config(str(tmp_path))["SETUP_CODE"]
    assert re.fullmatch(r"[0-9]{6}", code)
    assert any(code in note for note in notes)
    assert sent == [f"setup_code={code}\n"]


def test_the_credentials_carry_the_domain_unmasked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`domain` is the `DOMAIN` of install.py, and the log shows it."""
    folder = tmp_path / "server" / "src" / "app"
    folder.mkdir(parents=True)
    (folder / "config.py").write_text(f"{CONFIG_PY}    domain: str\n", encoding="utf-8")
    sent = _vps(monkeypatch)
    masked: list[str] = []
    ctx = _context(
        tmp_path,
        [],
        CF_DOMAIN_NAME="ejemplo.net",
        HEALTH_TOKEN="token",
        RESTIC_PASSWORD="restic",
        SETUP_CODE="123456",
    )
    monkeypatch.setattr(ctx, "guard", masked.append)
    vps_setup.load_credentials(ctx)
    assert "domain=ejemplo.net\n" in sent[0]
    assert masked == ["token", "123456", "restic"]
    # The development credentials take it from the same key.
    files = canone.credential_files(
        tmp_path / "server",
        Config({**ctx.config.values, "DATABASE_URL": "postgresql://demo@localhost/demo"}),
    )
    assert files["app_domain"] == "ejemplo.net"


SECRETS = ("page_token_key", "refresh_key", "vapid_key")
VALUES = {"HEALTH_TOKEN": "mine", "RESTIC_PASSWORD": "restic", "SETUP_CODE": "123456"}


def _with_secrets(tmp_path: Path) -> None:
    _repo(tmp_path)
    config_py = tmp_path / "server" / "src" / "app" / "config.py"
    extra = "".join(f"    {f}: str\n" for f in SECRETS)
    config_py.write_text(CONFIG_PY + extra, encoding="utf-8")


def test_the_chosen_secrets_get_a_value_of_their_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """They are kept for the next load, and what has a value stays."""
    _with_secrets(tmp_path)
    sent = _vps(monkeypatch)
    every = list(canone.GENERATED)
    vps_setup.load_credentials(_context(tmp_path, [], **VALUES), every)
    kept = envfile.load_config(str(tmp_path))
    # 32 bytes each; Fernet reads its key with padding.
    assert len(base64.urlsafe_b64decode(kept["PAGE_TOKEN_KEY"])) == 32
    for key in ("REFRESH_KEY", "VAPID_KEY"):
        assert len(base64.urlsafe_b64decode(kept[key] + "=")) == 32
    assert "health_token=mine\n" in sent[0]
    for field in SECRETS:
        assert f"{field}={kept[field.upper()]}\n" in sent[0]

    # A second load sends the same, though the VPS has them all.
    again = _vps(monkeypatch, stored=every)
    vps_setup.load_credentials(_context(tmp_path, [], **(kept | VALUES)), every)
    assert again == sent


def test_replacing_changes_only_the_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With `replace`, a value here or on the VPS does not keep it."""
    _with_secrets(tmp_path)
    sent = _vps(monkeypatch, stored=["refresh_key"])
    old = {field.upper(): "old" for field in SECRETS}
    ctx = _context(tmp_path, [], **VALUES, **old)
    vps_setup.load_credentials(ctx, ["refresh_key"], replace=True)
    new = envfile.load_config(str(tmp_path))["REFRESH_KEY"]
    assert new != "old"
    assert f"refresh_key={new}\n" in sent[0]
    assert "vapid_key=old\n" in sent[0]


@pytest.mark.parametrize(
    ("stored", "chosen", "reason"),
    [
        # Nothing chosen: the empty ones are required.
        ([], [], "PAGE_TOKEN_KEY, REFRESH_KEY, VAPID_KEY"),
        # One chosen: the others are.
        ([], ["refresh_key"], "PAGE_TOKEN_KEY, VAPID_KEY"),
        # Its value is on the VPS and not here.
        (["refresh_key"], list(SECRETS), "El VPS ya tiene refresh_key"),
    ],
)
def test_what_stops_leaves_everything_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stored: list[str],
    chosen: list[str],
    reason: str,
) -> None:
    """Neither config.env nor the VPS change."""
    _with_secrets(tmp_path)
    sent = _vps(monkeypatch, stored=stored)
    with pytest.raises(TaskError, match=reason):
        vps_setup.load_credentials(_context(tmp_path, [], **VALUES), chosen)
    assert sent == []
    assert not envfile.has_config(str(tmp_path))


def test_a_written_setup_code_is_the_one_sent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The code of the field goes as is, and nothing is generated."""
    _repo(tmp_path)
    sent = _vps(monkeypatch)
    notes: list[str] = []
    vps_setup.load_setup_code(_context(tmp_path, notes, SETUP_CODE="mi-codigo"))
    assert sent == ["setup_code=mi-codigo\n"]
    assert notes == []
    assert not envfile.has_config(str(tmp_path))


def test_the_credentials_carry_the_setup_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«Cargar credenciales» generates it too and sends it."""
    _repo(tmp_path)
    sent = _vps(monkeypatch)
    notes: list[str] = []
    ctx = _context(tmp_path, notes, HEALTH_TOKEN="token", RESTIC_PASSWORD="restic")
    vps_setup.load_credentials(ctx)
    code = envfile.load_config(str(tmp_path))["SETUP_CODE"]
    assert sent == [f"health_token=token\nsetup_code={code}\nrestic_password=restic\n"]
