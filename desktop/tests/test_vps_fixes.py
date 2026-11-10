"""What canone rules out in the VPS buttons.

And what they do when a step fails.

SSH is replaced: these cover the decisions around it, not the remote
commands.
"""

import types
from pathlib import Path
from typing import cast

import pytest

from app.core import canone, ssh
from app.core import database as db
from app.core.context import TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.tasks import database, vps_ops, vps_server


def _ignore(*args: object, **kwargs: object) -> None:
    pass


def _revoke_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, TaskContext]:
    folder = tmp_path / ".ssh"
    folder.mkdir()
    (folder / "key").write_text("private", encoding="utf-8")
    (folder / "key.pub").write_text("ssh-ed25519 AAA me", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return folder, cast(
        TaskContext,
        types.SimpleNamespace(
            config=Config({"VPS_IP": "host", "VPS_USER": "admin", "VPS_KEY_NAME": "key"}),
            warn=_ignore,
            ok=_ignore,
        ),
    )


def test_a_failed_remote_revoke_keeps_the_local_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed remote revoke keeps the local key."""
    folder, ctx = _revoke_context(monkeypatch, tmp_path)

    def fails(*args: object, **kwargs: object) -> None:
        raise TaskError("El comando termino con codigo 255.")

    monkeypatch.setattr(ssh, "run", fails)
    with pytest.raises(TaskError, match="La llave local sigue"):
        vps_ops.revoke_ssh_key(ctx)
    assert (folder / "key").is_file()
    assert (folder / "key.pub").is_file()


def test_a_good_remote_revoke_removes_the_local_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A good remote revoke removes the local key."""
    folder, ctx = _revoke_context(monkeypatch, tmp_path)
    monkeypatch.setattr(ssh, "run", _ignore)
    vps_ops.revoke_ssh_key(ctx)
    assert not (folder / "key").exists()


@pytest.mark.parametrize("action", ["start", "restart"])
def test_the_backup_is_not_started_from_the_service_control(action: str) -> None:
    """The backup does not start from the service control."""
    with pytest.raises(TaskError, match="receptora"):
        vps_server.systemd_action(
            cast(TaskContext, types.SimpleNamespace()), action=action, service="backup"
        )


def test_a_declared_extension_the_system_lacks_stops_the_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declared extension the system lacks stops the task."""
    created: list[tuple[object, ...]] = []

    def query(*args: object, **kwargs: object) -> str:
        return ""

    def execute(*args: object, **kwargs: object) -> None:
        created.append(args)

    admin = types.SimpleNamespace(query=query, execute=execute)

    def resolve_admin(ctx: TaskContext) -> types.SimpleNamespace:
        return admin

    monkeypatch.setattr(db, "resolve_admin", resolve_admin)
    ctx = cast(
        TaskContext,
        types.SimpleNamespace(
            config=Config(
                {"DB_EXTENSIONS": "postgis", "DB_USER": "u", "DB_NAME": "n", "DB_PASSWORD": "p"}
            ),
            ok=_ignore,
            info=_ignore,
        ),
    )
    with pytest.raises(TaskError, match="postgis"):
        database.enable_extensions(ctx)
    assert created == []


@pytest.mark.parametrize("values", [{}, {"DB_EXTENSIONS": ""}])
def test_without_a_declared_extension_no_package_or_argument_is_added(
    tmp_path: Path, values: dict[str, str]
) -> None:
    """Without a declared extension, no package or argument is added."""
    (tmp_path / "README.md").write_text("Estado: en desarrollo\n", encoding="utf-8")
    config = Config(
        {"DOMAIN": "example.net", "VALKEY_MEMORY": "256mb", "VPS_USER": "admin", **values}
    )
    assert "--extension" not in canone.package_args(tmp_path, config)
    args = canone.install_args(tmp_path, config, "demo", "owner", ("key one", "key two"), "1mb")
    assert "--extension" not in args


def test_an_empty_list_enables_nothing() -> None:
    """An empty list enables nothing."""
    messages: list[str] = []
    ctx = cast(
        TaskContext,
        types.SimpleNamespace(config=Config({"DB_EXTENSIONS": ""}), info=messages.append),
    )
    assert database.enable_extensions(ctx) == []
    assert messages
