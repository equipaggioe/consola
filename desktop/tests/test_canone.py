"""What Consola passes to canone's programs.

`core/canone.py` builds the arguments of `install.py` and the lines of
`credentials.py` without touching the network: it tests against a fake
repo on disk.
"""

from pathlib import Path
from typing import Any, cast

import pytest

from app.core import canone, envfile, process, runner
from app.core.context import TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError

KEYS = ("ssh-ed25519 AAAA uno", "sk-ssh-ed25519@openssh.com BBBB dos")
CONFIG_PY = '''
class Settings(BaseSettings):
    """Every field is required and has no default."""

    model_config = SettingsConfigDict(env_prefix="app_")

    database_url: str
    health_token: str
    page_token_key: str
'''


def repo(tmp_path: Path, **values: str) -> tuple[Path, Config]:
    """Return a fake repo and its config."""
    (tmp_path / "server" / "src" / "app").mkdir(parents=True)
    (tmp_path / "server" / "src" / "app" / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    (tmp_path / "panel").mkdir()
    base = {
        "DOMAIN": "ejemplo.net",
        "VALKEY_MEMORY": "256mb",
        "VPS_USER": "pablo",
        "DB_EXTENSIONS": "",
        **values,
    }
    envfile.save_config(str(tmp_path), base)
    return tmp_path, Config.for_project(str(tmp_path))


def test_install_args_come_from_the_repo_and_the_configuration(tmp_path: Path) -> None:
    """Install arguments come from the repo and the configuration."""
    root, config = repo(tmp_path, PRIVATE="si", PERMISSIONS_ALLOW="camera")
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "jobs:\n  web:\n  desktop-linux:\n  desktop-windows:\n", encoding="utf-8"
    )
    args = canone.install_args(root, config, "demo", "equipaggio", KEYS)
    assert args[:7] == [
        "demo",
        "ejemplo.net",
        "256mb",
        "--owner",
        "equipaggio",
        "--admin",
        "pablo",
    ]
    assert args.count("--key") == 2
    assert args.count("--signer") == 2
    assert "--private" in args
    assert ["--desktop", "linux"] == args[args.index("--desktop") : args.index("--desktop") + 2]
    # It has panel/, not web/ or landing/.
    sin = [args[i + 1] for i, a in enumerate(args) if a == "--without"]
    assert sin == ["web", "landing"]
    assert "--turn" not in args
    assert "--logs" not in args


def test_logs_go_all_three_or_none(tmp_path: Path) -> None:
    """The log arguments go all three or none."""
    root, config = repo(tmp_path)
    # LOGS belongs to the machine: it reaches the run from QSettings,
    # not from config.env.
    config = Config({**config.values, "LOGS": "equipaggio.net:51820"}, repo_name="demo")
    with pytest.raises(TaskError):
        canone.install_args(root, config, "demo", "equipaggio", KEYS)


def test_turn_ip_without_turn_stops(tmp_path: Path) -> None:
    """`TURN_IP` without `TURN` stops."""
    root, config = repo(tmp_path, TURN_IP="203.0.113.5")
    with pytest.raises(TaskError):
        canone.install_args(root, config, "demo", "equipaggio", KEYS)


def test_packages_by_repo(tmp_path: Path) -> None:
    """Packages depend on the repo."""
    _, config = repo(tmp_path, DB_EXTENSIONS="postgis", TURN="si")
    packages = canone.packages(config)
    assert canone.POSTGIS_PACKAGE in packages
    assert "coturn" in packages
    assert "wireguard-tools" not in packages


def test_credentials_by_source(tmp_path: Path) -> None:
    """Credentials come by source."""
    root, config = repo(tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r")
    assert canone.credential_lines(root, config) == (
        "health_token=h\npage_token_key=p\nrestic_password=r\n"
    )


def test_a_foreign_key_stops_before_sending(tmp_path: Path) -> None:
    """A key in no source stops before sending."""
    root, config = repo(
        tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r", TURN_SECRET="viejo"
    )
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, config)
    assert "TURN_SECRET" in str(error.value)


def test_an_empty_field_stops(tmp_path: Path) -> None:
    """An empty field stops."""
    root, config = repo(tmp_path, HEALTH_TOKEN="h", RESTIC_PASSWORD="r", PRIVATE="si")
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, config)
    assert "PAGE_TOKEN_KEY" in str(error.value)
    assert "GITHUB_TOKEN" in str(error.value)


def test_the_tag_follows_the_highest() -> None:
    """The tag follows the highest."""
    tags = ["v1.2.9", "v1.10.0", "v0.9.0", "probar", "v2.0"]
    assert canone.next_tag(tags, "patch") == "v1.10.1"
    assert canone.next_tag(tags, "minor") == "v1.11.0"
    assert canone.next_tag(tags, "major") == "v2.0.0"


def test_without_tags_it_rises_from_zero() -> None:
    """Without tags it rises from zero."""
    assert canone.next_tag([], "patch") == "v0.0.1"
    assert canone.next_tag([], "minor") == "v0.1.0"


def test_only_published_and_signed_releases_count() -> None:
    """Only published and signed releases count."""

    def release(tag: str, *names: str, draft: bool = False) -> dict[str, Any]:
        return {"tag_name": tag, "draft": draft, "assets": [{"name": n} for n in names]}

    items = [
        release("v1.2.0", "demo-v1.2.0.tar.gz", "demo-v1.2.0.sha256"),
        release("v1.1.0", "demo-v1.1.0.sha256", "demo-v1.1.0.sha256.sig"),
        release("v1.0.1", "demo-v1.0.1.sha256.sig", draft=True),
        release("v1.0.0", "otro-v1.0.0.sha256.sig"),
    ]
    assert [r["tag_name"] for r in canone.signed("demo", items)] == ["v1.1.0"]


def test_deploy_py_only_receives_a_tag() -> None:
    """`deploy.py` only receives a tag."""
    assert (
        canone.deploy_command("demo", "v1.4.0") == "python3 /usr/local/lib/demo/deploy.py v1.4.0"
    )
    with pytest.raises(TaskError):
        canone.deploy_command("demo", "v1.4.0; reboot")


def test_the_events_summary_says_none_if_there_are_none() -> None:
    """The events summary says none if there are none."""
    summary = canone.events_summary(
        {
            "lastEventAt": "2026-11-02T08:00:00Z",
            "lastCriticalAt": None,
            "lastBackupAt": None,
            "diskFreeBytes": 5_000_000_000,
            "diskTotalBytes": 10_000_000_000,
        }
    )
    assert summary == {
        "último evento": "2026-11-02T08:00:00Z",
        "último crítico": "ninguno",
        "último respaldo": "ninguno",
        "disco libre": "5.0 GB de 10.0 GB",
    }


def test_the_owner_is_the_role_with_owner() -> None:
    """The owner is the role with `_owner`."""
    assert (
        canone.owner_url("postgresql+asyncpg://app@127.0.0.1:5440/app")
        == "postgresql+asyncpg://app_owner@127.0.0.1:5440/app"
    )
    assert (
        canone.owner_url("postgresql+asyncpg://app:clave@127.0.0.1:5440/app")
        == "postgresql+asyncpg://app_owner:clave@127.0.0.1:5440/app"
    )


def test_a_url_without_a_role_has_no_owner() -> None:
    """A URL without a role has no owner."""
    with pytest.raises(TaskError, match="no nombra su rol"):
        canone.owner_url("postgresql+asyncpg://127.0.0.1:5440/app")


def _server(tmp_path: Path) -> Path:
    config = tmp_path / "server" / "src" / "app" / "config.py"
    config.parent.mkdir(parents=True)
    config.write_text(CONFIG_PY, encoding="utf-8")
    return tmp_path / "server"


def test_the_development_files_come_from_config_env(tmp_path: Path) -> None:
    """The development files come from `config.env`."""
    config = Config(
        {"DATABASE_URL": "postgresql://app@h/app", "HEALTH_TOKEN": "t", "PAGE_TOKEN_KEY": "k"}
    )
    assert canone.credential_files(_server(tmp_path), config) == {
        "app_database_url": "postgresql://app@h/app",
        "app_health_token": "t",
        "app_page_token_key": "k",
    }


def test_alembic_enters_as_the_owner(tmp_path: Path) -> None:
    """Alembic enters as the owner."""
    config = Config(
        {"DATABASE_URL": "postgresql://app@h/app", "HEALTH_TOKEN": "t", "PAGE_TOKEN_KEY": "k"}
    )
    files = canone.credential_files(_server(tmp_path), config, owner=True)
    assert files["app_database_url"] == "postgresql://app_owner@h/app"
    assert files["app_health_token"] == "t"


def test_the_development_files_stop_if_a_field_is_missing(tmp_path: Path) -> None:
    """The development files stop if a field is missing."""
    with pytest.raises(TaskError, match="DATABASE_URL, PAGE_TOKEN_KEY"):
        canone.credential_files(_server(tmp_path), Config({"HEALTH_TOKEN": "t"}))


class _GitContext:
    def capture(self, argv: list[str], *, cwd: Path | str | None = None) -> str:
        return process.capture(argv, cwd=cwd)


def _repo_with_canone_gitignore(tmp_path: Path) -> Path:
    process.capture(["git", "init", "-q", str(tmp_path)])
    (tmp_path / ".gitignore").write_text("credentials/\n", encoding="utf-8")
    server = tmp_path / "server"
    server.mkdir()
    return server


def test_the_owner_folder_only_needs_the_canone_gitignore(tmp_path: Path) -> None:
    """The owner's folder only needs canone's gitignore."""
    server = _repo_with_canone_gitignore(tmp_path)
    folder = runner.write_credentials(
        cast(TaskContext, _GitContext()),
        server,
        runner.MIGRATE_CREDENTIALS,
        {"app_database_url": "owner"},
    )
    assert folder == server / "credentials" / "migrate"
    assert (folder / "app_database_url").read_text(encoding="utf-8") == "owner"


def test_the_server_folder_keeps_the_owner_folder(tmp_path: Path) -> None:
    """The server's folder keeps the owner's folder."""
    server = _repo_with_canone_gitignore(tmp_path)
    owner = runner.write_credentials(
        cast(TaskContext, _GitContext()),
        server,
        runner.MIGRATE_CREDENTIALS,
        {"app_database_url": "owner"},
    )
    runner.write_credentials(
        cast(TaskContext, _GitContext()),
        server,
        runner.CREDENTIALS,
        {"app_database_url": "server"},
    )
    assert (owner / "app_database_url").is_file()
