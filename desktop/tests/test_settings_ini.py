"""What the app saves in QSettings reads back the same from its INI.

An INI file gives back text: a list of one element is a string, a
boolean is `"true"`, and a value with commas has to stay one value.
Each case writes in one process and reads in another, so the reading
comes from the file and not from Qt's cache.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SETUP = """
import json, sys
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
app = QApplication([])
app.setOrganizationName("Prueba")
app.setApplicationName("Prueba")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[1])
from app.services import favorites, params_store, project_store, section_visibility
from app.services.catalog import load_catalog
from app.services.projects import Project
from app.services.settings import machine_settings
from app.services.tasks import bind_all
from app.windows.main_window import MainWindow
load_catalog()
bind_all()
"""

WRITE = """
favorites.set_favorite("solo", True)
favorites.set_only_favorites(True)
section_visibility.set_section_hidden("maquina", False)
project_store.save([Project(name="a, b", path=sys.argv[2], theme="blue")])
params_store.save_machine_env({machine_settings()[0].key: "x, y"})
window = MainWindow()
window.resize(1234, 777)
window.close()
QSettings().sync()
print(bytes(window.saveGeometry().toBase64()).decode())
"""

READ = """
print(json.dumps({
    "favorites": sorted(favorites.favorite_ids()),
    "only": favorites.only_favorites(),
    "hidden": sorted(section_visibility.hidden_sections()),
    "projects": [[p.name, p.path] for p in project_store.load()],
    "machine": params_store.machine_env()[machine_settings()[0].key],
    "geometry": bytes(QSettings().value("main_window/geometry").toBase64()).decode(),
}))
"""


def _run(code: str, *args: str) -> str:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    done = subprocess.run(
        [sys.executable, "-c", SETUP + code, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_what_is_saved_reads_back_from_the_ini(tmp_path: Path) -> None:
    """Lists of one, booleans, commas and geometry survive the file."""
    folder = tmp_path / "settings"
    repo = tmp_path / "repo, con coma"
    repo.mkdir()
    geometry = _run(WRITE, str(folder), repo.as_posix()).splitlines()[-1]
    read: dict[str, Any] = json.loads(_run(READ, str(folder)).splitlines()[-1])
    assert read["favorites"] == ["solo"]
    assert read["only"] is True
    assert read["hidden"] == []
    assert read["projects"] == [["a, b", repo.as_posix()]]
    assert read["machine"] == "x, y"
    assert read["geometry"] == geometry
