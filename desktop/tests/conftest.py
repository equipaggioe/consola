"""The `screen` that `test_accessibility.py`, of canone, measures."""

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QLocale, QSettings, QTranslator
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

import app.rc_resources  # noqa: F401
from app import theme
from app.api import http
from app.services import language, session
from app.services.catalog import applicable_ids, load_catalog
from app.services.context import TaskError
from app.services.registry import Capability, registry
from app.services.tasks import bind_all
from app.widgets.action_menu_bar import choose_language
from app.widgets.tab_panel import TabPanel
from app.windows.main_window import MainWindow


class ConsolaScreen:
    """The window with a repo and four action tabs, one serving.

    Its bands are those of the window, top to bottom: title bar, menu
    row, run tabs, console, right column, its footer and status bar.
    """

    def __init__(self, window: MainWindow, qtbot: QtBot) -> None:
        """Keep the window and what only Consola knows of it."""
        self.window: QWidget = window
        self._window = window
        self._qtbot = qtbot
        workspace = window.current_workspace
        assert workspace is not None
        self._workspace = workspace
        self.bands: Sequence[QWidget] = [
            window.title_bar,
            window.menu_row,
            workspace.sub_bar,
            workspace.content_area,
            workspace.right_column,
            workspace.run_footer,
            window.status_bar,
        ]
        view = workspace.current_view()
        assert view is not None
        notice = workspace.env_panel.notice
        self.status_changes: Sequence[tuple[str, Callable[[], None]]] = [
            ("lo que hace Guardar", lambda: notice.emit("Guardado", "ok")),
            (
                "un endpoint que arranca",
                lambda: view.set_endpoint("http://127.0.0.1:1", "Sonda", False, session.STARTING),
            ),
            ("un endpoint que se cae", view.endpoint_down),
            ("una tarea que termina bien", lambda: self._run(fails=False)),
            ("una tarea que falla", lambda: self._run(fails=True)),
        ]

    def stop_motion(self) -> None:
        """Uncheck «Animaciones» and «RAM disponible» in Ver."""
        menu = self._window.action_menu
        for action in (menu.animations_action, menu.ram_action):
            if action.isChecked():
                action.trigger()

    def _run(self, *, fails: bool) -> None:
        """Run a task that ends at once, well or with an error."""

        def task(ctx: object) -> None:
            if fails:
                raise TaskError("sonda")

        capability = Capability(id="sonda", name="Sonda", group="", kind="once", func=task)
        workspace: TabPanel = self._workspace
        tab = workspace.tabs[0]
        workspace._run_real(tab, workspace._consoles[tab], capability, {})
        self._qtbot.waitUntil(lambda: tab not in workspace._busy, timeout=10000)


@pytest.fixture(params=language.offered())
def screen(
    request: pytest.FixtureRequest, qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ConsolaScreen]:
    """Open the window as `main.py` does, with nothing of the user.

    Once in each language: the texts of each measure differently.
    """
    for variable in ("APPDATA", "LOCALAPPDATA", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    locale = QLocale()
    choose_language(request.param)
    language.install(app)
    monkeypatch.setattr(http, "_network", None)
    http.start()
    load_catalog()
    bind_all()
    theme.apply(app)
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1400, 860)
    window.show()
    repo = tmp_path / "repo"
    repo.mkdir()
    window.project_tabs.open_path(str(repo))
    workspace = window.current_workspace
    assert workspace is not None
    opened = [
        capability
        for capability_id in sorted(applicable_ids(str(repo)))
        if (capability := registry.get_capability(capability_id)) is not None
        and capability.kind != "destructive"
    ][:4]
    for capability in opened:
        workspace.open_tab(capability)
    # A green LED pulses only while something serves.
    for view in workspace._views.values():
        if not (view.capability.has_web_view or view.capability.has_db_view):
            view.set_endpoint("http://127.0.0.1:1", "Sonda", False, session.READY)
            break
    window.activateWindow()
    yield ConsolaScreen(window, qtbot)
    # The translators would pile up in the one QApplication of the run.
    for translator in app.findChildren(QTranslator):
        QCoreApplication.removeTranslator(translator)
        translator.deleteLater()
    QLocale.setDefault(locale)
