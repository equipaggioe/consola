"""What Consola passes to canone's programs.

`core/canone.py` builds the arguments of `install.py` and the lines of
`credentials.py` without touching the network: it tests against a fake
repo on disk.
"""

from pathlib import Path
from typing import Any, cast

import pytest

from app.core import canone, envfile, fields, process, runner
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
    valkey_url: str
'''

TASKS_PY = """
TASKS: dict[str, Callable[[], Awaitable[None]]] = {
    "migrate": migrate,
    "purge": events.purge,
    "sweep": files.sweep,
}
"""


def repo(tmp_path: Path, state: str = "en desarrollo", **values: str) -> tuple[Path, Config]:
    """Return a fake repo and its config."""
    (tmp_path / "README.md").write_text(f"# demo\n\nEstado: {state}\n", encoding="utf-8")
    (tmp_path / "server" / "src" / "app").mkdir(parents=True)
    (tmp_path / "server" / "src" / "app" / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    (tmp_path / "server" / "src" / "app" / "tasks.py").write_text(TASKS_PY, encoding="utf-8")
    (tmp_path / "panel").mkdir()
    base = {
        "DOMAIN": "ejemplo.net",
        "VALKEY_MEMORY": "256mb",
        "VPS_USER": "pablo",
        "DB_EXTENSIONS": "",
        **values,
    }
    envfile.save_config(str(tmp_path), base, fields.field_settings(tmp_path / "server"))
    return tmp_path, Config.for_project(str(tmp_path))


def test_install_args_come_from_the_repo_and_the_configuration(tmp_path: Path) -> None:
    """Install arguments come from the repo and the configuration."""
    root, config = repo(tmp_path, PRIVATE="si")
    (root / "permissions").write_text("camera\ngeolocation\n", encoding="utf-8")
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "jobs:\n"
        "  desktop:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        include:\n"
        "          - os: ubuntu-latest\n"
        "            archivo: desktop-linux.bin\n"
        "          - os: windows-latest\n"
        "            archivo: desktop-windows.exe\n"
        "  mobile:\n"
        '      - run: gh release upload "$GITHUB_REF_NAME" mobile-customer.apk\n',
        encoding="utf-8",
    )
    args = canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")
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
    mobile = args.index("--mobile")
    assert args[mobile : mobile + 2] == ["--mobile", "mobile-customer"]
    # It has panel/, not web/ or landing/.
    sin = [args[i + 1] for i, a in enumerate(args) if a == "--without"]
    assert sin == ["web", "landing"]
    allowed = [args[i + 1] for i, a in enumerate(args) if a == "--allow"]
    assert allowed == ["camera", "geolocation"]
    assert "--turn" not in args
    assert "--logs" not in args
    assert "--development" in args


def test_each_piece_in_java_goes_to_packages_and_install(tmp_path: Path) -> None:
    """Each piece release.yml builds with java.py goes as --java."""
    root, config = repo(tmp_path)
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "jobs:\n  artifact:\n      - run: python3 scripts/java.py fingerprint Afis dist\n",
        encoding="utf-8",
    )
    assert canone.package_args(root, config) == ["--java", "fingerprint"]
    args = canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")
    java = args.index("--java")
    assert args[java : java + 2] == ["--java", "fingerprint"]
    assert canone.java_pieces(tmp_path / "otro") == []


def test_a_server_without_sweep_installs_without_its_timer(tmp_path: Path) -> None:
    """A server whose TASKS lacks `sweep` goes `--without sweep`."""
    root, config = repo(tmp_path)
    (root / "server" / "src" / "app" / "tasks.py").write_text(
        'TASKS = {"migrate": migrate, "purge": purge}\n', encoding="utf-8"
    )
    args = canone.install_args(root, config, "app", "duenio", KEYS, "256mb")
    sin = [args[i + 1] for i, a in enumerate(args) if a == "--without"]
    assert sin == ["web", "landing", "sweep"]


def test_each_task_of_timers_goes_with_its_calendar(tmp_path: Path) -> None:
    """Each task of TIMERS goes as `--task <task>=<OnCalendar>`.

    Without TIMERS no `--task` goes.
    """
    root, config = repo(tmp_path)
    args = canone.install_args(root, config, "app", "duenio", KEYS, "256mb")
    assert "--task" not in args
    tasks_py = root / "server" / "src" / "app" / "tasks.py"
    tasks_py.write_text(
        'TASKS = {"migrate": migrate, "alert": alert, "sweep": sweep}\n'
        'TIMERS: dict[str, str] = {"alert": "minutely"}\n',
        encoding="utf-8",
    )
    args = canone.install_args(root, config, "app", "duenio", KEYS, "256mb")
    assert [args[i + 1] for i, a in enumerate(args) if a == "--task"] == ["alert=minutely"]


def test_a_timer_of_a_task_that_does_not_exist_stops(tmp_path: Path) -> None:
    """A task of TIMERS that TASKS lacks stops.

    So does a calendar that is not a text.
    """
    root, config = repo(tmp_path)
    tasks_py = root / "server" / "src" / "app" / "tasks.py"
    tasks_py.write_text(
        'TASKS = {"migrate": migrate}\nTIMERS = {"alert": "minutely"}\n', encoding="utf-8"
    )
    with pytest.raises(TaskError, match="no en TASKS"):
        canone.install_args(root, config, "app", "duenio", KEYS, "256mb")
    tasks_py.write_text('TASKS = {"alert": alert}\nTIMERS = {"alert": MINUTE}\n', encoding="utf-8")
    with pytest.raises(TaskError, match="es un texto"):
        canone.install_args(root, config, "app", "duenio", KEYS, "256mb")


def test_a_server_without_tasks_stops(tmp_path: Path) -> None:
    """A server without tasks.py stops: its units run them."""
    root, config = repo(tmp_path)
    (root / "server" / "src" / "app" / "tasks.py").unlink()
    with pytest.raises(TaskError, match="tareas de canone"):
        canone.install_args(root, config, "app", "duenio", KEYS, "256mb")


def test_without_permissions_nothing_is_allowed(tmp_path: Path) -> None:
    """Without the repo's `permissions`, no `--allow` goes."""
    root, config = repo(tmp_path)
    assert "--allow" not in canone.install_args(root, config, "demo", "equipaggio", KEYS, "1mb")


def test_valkey_memory_is_a_share_of_memtotal() -> None:
    """`VALKEY_PERCENT` of `MemTotal`, in whole MB."""
    meminfo = "MemTotal:        2014000 kB\nMemFree:          500000 kB\n"
    assert canone.valkey_memory(meminfo, "12.5") == "245mb"
    assert canone.valkey_memory(meminfo, "25") == "491mb"


@pytest.mark.parametrize("percent", ["", "doce", "0", "120"])
def test_a_wrong_percent_stops(percent: str) -> None:
    """A percent that is not a number from 0 to 100 stops."""
    with pytest.raises(TaskError, match="VALKEY_PERCENT"):
        canone.valkey_memory("MemTotal: 1000 kB\n", percent)


def test_a_repo_in_production_installs_without_the_development_mark(tmp_path: Path) -> None:
    """A repo in production installs without `--development`."""
    root, config = repo(tmp_path, state="en producción")
    assert "--development" not in canone.install_args(
        root, config, "demo", "equipaggio", KEYS, "256mb"
    )


def test_a_readme_without_a_state_stops(tmp_path: Path) -> None:
    """A README without its state stops: none is assumed."""
    root, config = repo(tmp_path)
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    with pytest.raises(TaskError, match="Estado"):
        canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")


def test_database_py_only_receives_its_commands() -> None:
    """`database.py` only receives its own commands."""
    assert (
        canone.database_command("demo", "seed --mock")
        == "/usr/local/sbin/demo-database seed --mock"
    )
    with pytest.raises(TaskError):
        canone.database_command("demo", "empty; reboot")


def test_logs_go_all_three_or_none(tmp_path: Path) -> None:
    """The log arguments go all three or none."""
    root, config = repo(tmp_path)
    # LOGS belongs to the machine: it reaches the run from QSettings,
    # not from config.env.
    config = Config({**config.values, "LOGS": "equipaggio.net:51820"}, repo_name="demo")
    with pytest.raises(TaskError):
        canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")


def _with_calls(root: Path) -> None:
    """Declare `turn_secret` in Settings: an app with calls."""
    config_py = root / "server" / "src" / "app" / "config.py"
    config_py.write_text(CONFIG_PY + "    turn_secret: str\n", encoding="utf-8")


def test_turn_ip_without_calls_stops(tmp_path: Path) -> None:
    """`TURN_IP` in a repo without `turn_secret` stops."""
    root, config = repo(tmp_path, TURN_IP="203.0.113.5")
    with pytest.raises(TaskError, match="turn_secret"):
        canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")


def test_turn_comes_from_turn_secret(tmp_path: Path) -> None:
    """A Settings with `turn_secret` installs coturn, with its IP."""
    root, config = repo(tmp_path, TURN_IP="203.0.113.5")
    _with_calls(root)
    args = canone.install_args(root, config, "demo", "equipaggio", KEYS, "256mb")
    assert args[args.index("--turn") :][:3] == ["--turn", "--turn-ip", "203.0.113.5"]


def test_package_options_by_repo(tmp_path: Path) -> None:
    """The options of packages.py depend on the repo."""
    root, config = repo(tmp_path, DB_EXTENSIONS="postgis")
    assert canone.package_args(root, config) == ["--extension", "postgis"]
    _with_calls(root)
    assert canone.package_args(root, config) == ["--extension", "postgis", "--turn"]


def test_packages_come_from_packages_py(tmp_path: Path) -> None:
    """The packages are what packages.py --list prints."""
    infra = tmp_path / "canone" / "plantilla" / "infra"
    infra.mkdir(parents=True)
    (infra / "install.py").write_text("", encoding="utf-8")
    (infra / "packages.py").write_text(
        "import sys\nprint(*['base', *sys.argv[1:]], sep='\\n')\n", encoding="utf-8"
    )
    config = Config({"DB_EXTENSIONS": "postgis", "CANONE_DIR": str(tmp_path / "canone")})
    assert canone.packages(tmp_path, config) == ["base", "--list", "--extension", "postgis"]


def test_without_packages_py_it_says_so(tmp_path: Path) -> None:
    """A canone copy without packages.py stops and says so."""
    infra = tmp_path / "canone" / "plantilla" / "infra"
    infra.mkdir(parents=True)
    (infra / "install.py").write_text("", encoding="utf-8")
    config = Config({"CANONE_DIR": str(tmp_path / "canone")})
    with pytest.raises(TaskError, match="packages.py"):
        canone.packages(tmp_path, config)


def test_credentials_by_source(tmp_path: Path) -> None:
    """Credentials come by source."""
    root, config = repo(tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r")
    assert canone.credential_lines(root, config) == (
        "health_token=h\npage_token_key=p\nrestic_password=r\n"
    )


def test_valkey_url_is_local_only(tmp_path: Path) -> None:
    """valkey_url goes to the local credentials, not credentials.py."""
    root, config = repo(
        tmp_path,
        DATABASE_URL="d",
        HEALTH_TOKEN="h",
        PAGE_TOKEN_KEY="p",
        RESTIC_PASSWORD="r",
        VALKEY_URL="v",
    )
    assert "valkey_url" not in canone.credential_lines(root, config)
    files = canone.credential_files(root / "server", config)
    assert files["app_valkey_url"] == "v"


def test_turn_secret_is_local_only(tmp_path: Path) -> None:
    """turn_secret goes to the local credentials, not credentials.py."""
    root, config = repo(
        tmp_path,
        DATABASE_URL="d",
        HEALTH_TOKEN="h",
        PAGE_TOKEN_KEY="p",
        RESTIC_PASSWORD="r",
        VALKEY_URL="v",
        TURN_SECRET="t",
    )
    config_py = root / "server" / "src" / "app" / "config.py"
    config_py.write_text(CONFIG_PY + "    turn_secret: str\n", encoding="utf-8")
    assert "turn_secret" not in canone.credential_lines(root, config)
    assert canone.credential_files(root / "server", config)["app_turn_secret"] == "t"


def test_a_foreign_key_stops_before_sending(tmp_path: Path) -> None:
    """A key in no source stops before sending."""
    root, _ = repo(tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r")
    # Written by hand: Consola's save writes no key without a source.
    with open(envfile.config_path(str(root)), "a", encoding="utf-8") as fh:
        fh.write("SECRET_FILES=viejo\n")
    config = Config.for_project(str(root))
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, config)
    assert "SECRET_FILES" in str(error.value)


def test_the_config_it_receives_is_checked_not_the_file(tmp_path: Path) -> None:
    """The foreign keys are those of the config the task runs with."""
    root, config = repo(tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r")
    with open(envfile.config_path(str(root)), "a", encoding="utf-8") as fh:
        fh.write("SECRET_FILES=viejo\n")
    assert "SECRET_FILES" not in canone.credential_lines(root, config)
    built = Config({**config.values, "SECRET_FILES": "viejo"})
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, built)
    assert "SECRET_FILES" in str(error.value)


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
    assert canone.deploy_command("demo", "v1.4.0") == "/usr/local/sbin/demo-deploy v1.4.0"
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
        {
            "DATABASE_URL": "postgresql://app@h/app",
            "HEALTH_TOKEN": "t",
            "PAGE_TOKEN_KEY": "k",
            "VALKEY_URL": "v",
        }
    )
    assert canone.credential_files(_server(tmp_path), config) == {
        "app_database_url": "postgresql://app@h/app",
        "app_health_token": "t",
        "app_page_token_key": "k",
        "app_valkey_url": "v",
    }


def test_alembic_enters_as_the_owner(tmp_path: Path) -> None:
    """Alembic enters as the owner."""
    config = Config(
        {
            "DATABASE_URL": "postgresql://app@h/app",
            "HEALTH_TOKEN": "t",
            "PAGE_TOKEN_KEY": "k",
            "VALKEY_URL": "v",
        }
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
