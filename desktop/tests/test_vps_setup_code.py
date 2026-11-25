"""The code that registers the superadmin: `SETUP_CODE`, or a new one.

SSH is replaced: these cover what is kept in config.env and what the
VPS receives.
"""

import base64
import re
import types
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


def _vps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Return the input of each command the VPS receives."""
    sent: list[str] = []

    def run(ctx: TaskContext, command: str, *, text: str = "") -> None:
        sent.append(text)

    entry = types.SimpleNamespace(run=run, remote=types.SimpleNamespace(host="vps"))
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


def test_empty_secrets_are_required_or_generated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty ones stop; with `generate` each gets its format, once."""
    _repo(tmp_path)
    config_py = tmp_path / "server" / "src" / "app" / "config.py"
    extra = "".join(f"    {f}: str\n" for f in ("page_token_key", "refresh_key", "vapid_key"))
    config_py.write_text(CONFIG_PY + extra, encoding="utf-8")
    sent = _vps(monkeypatch)
    values = {"HEALTH_TOKEN": "mine", "RESTIC_PASSWORD": "restic", "SETUP_CODE": "123456"}
    with pytest.raises(TaskError, match="Faltan"):
        vps_setup.load_credentials(_context(tmp_path, [], **values))
    assert sent == []

    vps_setup.load_credentials(_context(tmp_path, [], **values), generate=True)
    kept = envfile.load_config(str(tmp_path))
    # 32 bytes each; Fernet reads its key with padding.
    assert len(base64.urlsafe_b64decode(kept["PAGE_TOKEN_KEY"])) == 32
    for key in ("REFRESH_KEY", "VAPID_KEY"):
        assert len(base64.urlsafe_b64decode(kept[key] + "=")) == 32
    # The written one stays.
    assert "health_token=mine\n" in sent[0]
    for field in ("page_token_key", "refresh_key", "vapid_key"):
        assert f"{field}={kept[field.upper()]}\n" in sent[0]

    # A second load sends the same.
    vps_setup.load_credentials(_context(tmp_path, [], **(kept | values)), generate=True)
    assert sent[1] == sent[0]


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
