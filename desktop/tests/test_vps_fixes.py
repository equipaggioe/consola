"""What canone rules out in the VPS buttons, and what they do when a step fails.

SSH is replaced: these cover the decisions around it, not the remote commands.
"""
import types
from pathlib import Path

import pytest


from app.core import canone
from app.core import database as db
from app.core import ssh
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.tasks import database, vps_ops, vps_server


def _revoke_context(monkeypatch, tmp_path):
    folder = tmp_path / '.ssh'
    folder.mkdir()
    (folder / 'key').write_text('private', encoding='utf-8')
    (folder / 'key.pub').write_text('ssh-ed25519 AAA me', encoding='utf-8')
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    return folder, types.SimpleNamespace(
        config=Config({'VPS_IP': 'host', 'VPS_USER': 'admin', 'VPS_KEY_NAME': 'key'}),
        warn=lambda message: None, ok=lambda message: None)


def test_a_failed_remote_revoke_keeps_the_local_key(monkeypatch, tmp_path):
    folder, ctx = _revoke_context(monkeypatch, tmp_path)

    def fails(*args, **kwargs):
        raise TaskError('El comando termino con codigo 255.')

    monkeypatch.setattr(ssh, 'run', fails)
    with pytest.raises(TaskError, match='La llave local sigue'):
        vps_ops.revoke_ssh_key(ctx)
    assert (folder / 'key').is_file() and (folder / 'key.pub').is_file()


def test_a_good_remote_revoke_removes_the_local_key(monkeypatch, tmp_path):
    folder, ctx = _revoke_context(monkeypatch, tmp_path)
    monkeypatch.setattr(ssh, 'run', lambda *args, **kwargs: 0)
    vps_ops.revoke_ssh_key(ctx)
    assert not (folder / 'key').exists()


@pytest.mark.parametrize('action', ['start', 'restart'])
def test_the_backup_is_not_started_from_the_service_control(action):
    with pytest.raises(TaskError, match='receptora'):
        vps_server.systemd_action(types.SimpleNamespace(), action=action, service='backup')


def test_a_declared_extension_the_system_lacks_stops_the_task(monkeypatch):
    created = []
    admin = types.SimpleNamespace(query=lambda *args, **kwargs: '',
                                  execute=lambda *args, **kwargs: created.append(args))
    monkeypatch.setattr(db, 'resolve_admin', lambda ctx, scope: admin)
    ctx = types.SimpleNamespace(
        config=Config({'DB_EXTENSIONS': 'postgis', 'DB_USER': 'u', 'DB_NAME': 'n',
                       'DB_PASSWORD': 'p'}),
        ok=lambda message: None, info=lambda message: None)
    with pytest.raises(TaskError, match='postgis'):
        database.enable_extensions(ctx)
    assert created == []


@pytest.mark.parametrize('values', [{}, {'DB_EXTENSIONS': ''}])
def test_no_declared_extension_reaches_no_package_or_argument(tmp_path, values):
    config = Config({'DOMAIN': 'example.net', 'VALKEY_MEMORY': '256mb', 'VPS_USER': 'admin',
                     **values})
    assert canone.POSTGIS_PACKAGE not in canone.packages(config)
    args = canone.install_args(tmp_path, config, 'demo', 'owner', ('key one', 'key two'))
    assert '--extension' not in args


def test_an_empty_list_enables_nothing():
    messages = []
    ctx = types.SimpleNamespace(config=Config({'DB_EXTENSIONS': ''}), info=messages.append)
    assert database.enable_extensions(ctx) == []
    assert messages
