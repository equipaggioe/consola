"""«Secretos a generar», with the real panel and form.

One box per empty secret the repo declares (ADR-0097).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from app.services import envfile, fields, palettes, params_store
from app.services.catalog import load_catalog
from app.services.projects import Project
from app.services.registry import registry
from app.widgets.env_panel import EnvPanel
from app.widgets.params_panel import ParamsPanel

CONFIG_PY = """
class Settings(BaseSettings):
    contact: str
    health_token: str
    refresh_key: str
    vapid_key: str
"""


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    """Return a repo whose `health_token` has a value."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    load_catalog()
    repo = tmp_path / "demo"
    folder = repo / "server" / "src" / "app"
    folder.mkdir(parents=True)
    (folder / "config.py").write_text(CONFIG_PY, encoding="utf-8")
    write(repo, HEALTH_TOKEN="mine")
    yield Project("demo", str(repo), next(iter(palettes.THEMES)))
    params_store.flush()
    QSettings().clear()


def write(repo: Path, **values: str) -> None:
    """Write `config.env` as the form does."""
    envfile.save_config(str(repo), values, fields.field_settings(repo / "server"))


def opened(project: Project, qtbot: QtBot) -> ParamsPanel:
    """Return the panel of «Cargar credenciales», its query answered."""
    capability = registry.get_capability("load_credentials")
    assert capability is not None
    env_panel = EnvPanel(project)
    qtbot.addWidget(env_panel)
    panel = ParamsPanel(capability, project, env_panel)
    qtbot.addWidget(panel)
    qtbot.waitUntil(lambda: not panel._loading, timeout=10000)
    return panel


def test_each_empty_secret_has_its_box_unchecked(project: Project, qtbot: QtBot) -> None:
    """Those with a value, or that are not random, have none."""
    panel = opened(project, qtbot)
    assert list(panel._checks["generate"]) == ["refresh_key", "vapid_key"]
    assert panel.selection("generate") == []


def test_what_is_checked_runs_and_is_not_remembered(project: Project, qtbot: QtBot) -> None:
    """It reaches the function, survives a reread, and not a reopen."""
    panel = opened(project, qtbot)
    panel._checks["generate"]["vapid_key"].setChecked(True)
    assert panel.capability.kwargs_from(panel.payload()) == {"generate": ["vapid_key"]}
    panel.reload_catalogs()
    qtbot.waitUntil(lambda: not panel._loading, timeout=10000)
    assert panel.selection("generate") == ["vapid_key"]
    assert opened(project, qtbot).selection("generate") == []


def test_with_none_empty_it_does_not_block(project: Project, qtbot: QtBot) -> None:
    """The axis says there is none, and asks for nothing."""
    write(Path(project.path), HEALTH_TOKEN="a", REFRESH_KEY="b", VAPID_KEY="c")
    panel = opened(project, qtbot)
    assert panel.selection("generate") == []
    assert "config.env" in panel._empty_notes["generate"].text()
    assert not any("secretos" in reason for reason in panel.blockers())


def test_the_form_takes_what_a_failed_task_generated(project: Project, qtbot: QtBot) -> None:
    """The empty row fills, and an unsaved edit stays."""
    form = EnvPanel(project)
    qtbot.addWidget(form)
    form.rows["HEALTH_TOKEN"].set_value("unsaved")
    write(Path(project.path), HEALTH_TOKEN="mine", REFRESH_KEY="generated")
    form.take_generated()
    assert form.values()["REFRESH_KEY"] == "generated"
    assert form.values()["HEALTH_TOKEN"] == "unsaved"
