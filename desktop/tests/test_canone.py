"""Lo que Consola le pasa a los programas de canone.

`core/canone.py` arma los argumentos de `install.py` y las lineas de
`credentials.py` sin tocar red: se prueba contra un repo falso en disco.
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


def test_install_args_salen_del_repo_y_de_la_configuracion(tmp_path: Path) -> None:
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
    assert args.count("--key") == 2 and args.count("--signer") == 2
    assert "--private" in args
    assert ["--desktop", "linux"] == args[args.index("--desktop") : args.index("--desktop") + 2]
    # Tiene panel/, no web/ ni landing/.
    sin = [args[i + 1] for i, a in enumerate(args) if a == "--without"]
    assert sin == ["web", "landing"]
    assert "--turn" not in args and "--logs" not in args


def test_logs_van_los_tres_o_ninguno(tmp_path: Path) -> None:
    root, config = repo(tmp_path)
    # LOGS es de la maquina: llega a la corrida desde QSettings, no desde config.env.
    config = Config({**config.values, "LOGS": "equipaggio.net:51820"}, repo_name="demo")
    with pytest.raises(TaskError):
        canone.install_args(root, config, "demo", "equipaggio", KEYS)


def test_turn_ip_sin_turn_corta(tmp_path: Path) -> None:
    root, config = repo(tmp_path, TURN_IP="203.0.113.5")
    with pytest.raises(TaskError):
        canone.install_args(root, config, "demo", "equipaggio", KEYS)


def test_paquetes_segun_el_repo(tmp_path: Path) -> None:
    _, config = repo(tmp_path, DB_EXTENSIONS="postgis", TURN="si")
    packages = canone.packages(config)
    assert canone.POSTGIS_PACKAGE in packages and "coturn" in packages
    assert "wireguard-tools" not in packages


def test_credenciales_por_fuente(tmp_path: Path) -> None:
    root, config = repo(tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r")
    assert canone.credential_lines(root, config) == (
        "health_token=h\npage_token_key=p\nrestic_password=r\n"
    )


def test_una_clave_ajena_corta_antes_de_enviar(tmp_path: Path) -> None:
    root, config = repo(
        tmp_path, HEALTH_TOKEN="h", PAGE_TOKEN_KEY="p", RESTIC_PASSWORD="r", TURN_SECRET="viejo"
    )
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, config)
    assert "TURN_SECRET" in str(error.value)


def test_un_campo_vacio_corta(tmp_path: Path) -> None:
    root, config = repo(tmp_path, HEALTH_TOKEN="h", RESTIC_PASSWORD="r", PRIVATE="si")
    with pytest.raises(TaskError) as error:
        canone.credential_lines(root, config)
    assert "PAGE_TOKEN_KEY" in str(error.value) and "GITHUB_TOKEN" in str(error.value)


def test_el_tag_sigue_al_mas_alto() -> None:
    tags = ["v1.2.9", "v1.10.0", "v0.9.0", "probar", "v2.0"]
    assert canone.next_tag(tags, "patch") == "v1.10.1"
    assert canone.next_tag(tags, "minor") == "v1.11.0"
    assert canone.next_tag(tags, "major") == "v2.0.0"


def test_sin_tags_sube_desde_cero() -> None:
    assert canone.next_tag([], "patch") == "v0.0.1"
    assert canone.next_tag([], "minor") == "v0.1.0"


def test_solo_cuentan_los_releases_publicados_y_firmados() -> None:
    def release(tag: str, *names: str, draft: bool = False) -> dict[str, Any]:
        return {"tag_name": tag, "draft": draft, "assets": [{"name": n} for n in names]}

    items = [
        release("v1.2.0", "demo-v1.2.0.tar.gz", "demo-v1.2.0.sha256"),
        release("v1.1.0", "demo-v1.1.0.sha256", "demo-v1.1.0.sha256.sig"),
        release("v1.0.1", "demo-v1.0.1.sha256.sig", draft=True),
        release("v1.0.0", "otro-v1.0.0.sha256.sig"),
    ]
    assert [r["tag_name"] for r in canone.signed("demo", items)] == ["v1.1.0"]


def test_deploy_py_solo_recibe_un_tag() -> None:
    assert (
        canone.deploy_command("demo", "v1.4.0") == "python3 /usr/local/lib/demo/deploy.py v1.4.0"
    )
    with pytest.raises(TaskError):
        canone.deploy_command("demo", "v1.4.0; reboot")


def test_el_resumen_de_eventos_dice_ninguno_si_no_hay() -> None:
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


def test_el_dueno_es_el_rol_con_owner() -> None:
    assert (
        canone.owner_url("postgresql+asyncpg://app@127.0.0.1:5440/app")
        == "postgresql+asyncpg://app_owner@127.0.0.1:5440/app"
    )
    assert (
        canone.owner_url("postgresql+asyncpg://app:clave@127.0.0.1:5440/app")
        == "postgresql+asyncpg://app_owner:clave@127.0.0.1:5440/app"
    )


def test_una_url_sin_rol_no_tiene_dueno() -> None:
    with pytest.raises(TaskError, match="no nombra su rol"):
        canone.owner_url("postgresql+asyncpg://127.0.0.1:5440/app")


def _server(tmp_path: Path) -> Path:
    config = tmp_path / "server" / "src" / "app" / "config.py"
    config.parent.mkdir(parents=True)
    config.write_text(CONFIG_PY, encoding="utf-8")
    return tmp_path / "server"


def test_los_archivos_de_desarrollo_salen_de_config_env(tmp_path: Path) -> None:
    config = Config(
        {"DATABASE_URL": "postgresql://app@h/app", "HEALTH_TOKEN": "t", "PAGE_TOKEN_KEY": "k"}
    )
    assert canone.credential_files(_server(tmp_path), config) == {
        "app_database_url": "postgresql://app@h/app",
        "app_health_token": "t",
        "app_page_token_key": "k",
    }


def test_alembic_entra_como_el_dueno(tmp_path: Path) -> None:
    config = Config(
        {"DATABASE_URL": "postgresql://app@h/app", "HEALTH_TOKEN": "t", "PAGE_TOKEN_KEY": "k"}
    )
    files = canone.credential_files(_server(tmp_path), config, owner=True)
    assert files["app_database_url"] == "postgresql://app_owner@h/app"
    assert files["app_health_token"] == "t"


def test_los_archivos_de_desarrollo_cortan_si_falta_un_campo(tmp_path: Path) -> None:
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
