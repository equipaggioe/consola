"""«Secretos a generar», with the real panel and form.

One box per random secret the repo declares (ADR-0098).
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


def test_each_random_secret_has_its_box_with_its_state(project: Project, qtbot: QtBot) -> None:
    """All of them, unchecked; one that is not random has none."""
    panel = opened(project, qtbot)
    boxes = panel._checks["generate"]
    assert list(boxes) == ["health_token", "refresh_key", "vapid_key"]
    assert "con valor" in boxes["health_token"].text()
    assert "vacío" in boxes["refresh_key"].text()
    assert panel.selection("generate") == []
    assert [box.isChecked() for box in panel._options["replace"].values()] == [False]
    chosen = panel.capability.kwargs_from(panel.payload())
    assert chosen == {"generate": [], "replace": False}


def test_what_is_chosen_runs_and_is_not_remembered(project: Project, qtbot: QtBot) -> None:
    """It reaches the function, survives a reread, and not a reopen."""
    panel = opened(project, qtbot)
    panel._checks["generate"]["vapid_key"].setChecked(True)
    panel._options["replace"]["replace"].setChecked(True)
    chosen = {"generate": ["vapid_key"], "replace": True}
    assert panel.capability.kwargs_from(panel.payload()) == chosen
    panel._options["replace"]["replace"].setChecked(False)
    assert panel.capability.kwargs_from(panel.payload())["replace"] is False
    panel._options["replace"]["replace"].setChecked(True)
    panel.reload_catalogs()
    qtbot.waitUntil(lambda: not panel._loading, timeout=10000)
    assert panel.capability.kwargs_from(panel.payload()) == chosen
    again = opened(project, qtbot)
    assert again.capability.kwargs_from(again.payload()) == {"generate": [], "replace": False}


def test_a_repo_without_them_does_not_block(project: Project, qtbot: QtBot) -> None:
    """The axis says there is none, and asks for nothing."""
    config_py = Path(project.path) / "server" / "src" / "app" / "config.py"
    config_py.write_text("class Settings(BaseSettings):\n    contact: str\n", encoding="utf-8")
    panel = opened(project, qtbot)
    assert "Settings" in panel._empty_notes["generate"].text()
    assert not any("secretos" in reason for reason in panel.blockers())


def test_the_form_takes_what_a_failed_task_wrote(project: Project, qtbot: QtBot) -> None:
    """New and replaced values come, and an unsaved edit stays."""
    repo = Path(project.path)
    write(repo, HEALTH_TOKEN="mine", VAPID_KEY="old")
    form = EnvPanel(project)
    qtbot.addWidget(form)
    form.rows["HEALTH_TOKEN"].set_value("unsaved")
    write(repo, HEALTH_TOKEN="mine", VAPID_KEY="new", REFRESH_KEY="generated")
    form.take_written()
    values = form.values()
    assert values["REFRESH_KEY"] == "generated"
    assert values["VAPID_KEY"] == "new"
    assert values["HEALTH_TOKEN"] == "unsaved"
