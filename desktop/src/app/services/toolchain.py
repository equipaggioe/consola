"""Find the build tools and what each one builds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.files import read_text
from app.services.host import HOST
from app.services.language import QT_TRANSLATE_NOOP
from app.services.process import resolve_executable

FLUTTER = "flutter"
FLET = "flet"


@dataclass(frozen=True)
class BuildPlatform:
    """A platform `build_flutter` can compile to.

    Outputs are globs relative to the app's folder: where each framework
    leaves its build unprompted. Flet copies its own to
    `build/<platform>/`; Flutter buries it in its usual tree.
    """

    label: str
    flutter: str  # `flutter build` subcommand
    flet: str  # `flet build` platform
    flutter_out: str
    flet_out: str
    # extension of a build that is one file (`.apk`). Empty: the build
    # is a whole folder (web, desktop).
    suffix: str = ""
    host: str = ""  # `platform.system()` where it can only compile.
    # Neither Flutter nor Flet compiles desktop or iOS for a system
    # other than the one running.

    def output(self, kind: str) -> str:
        """Return the output glob for that framework."""
        return self.flutter_out if kind == FLUTTER else self.flet_out


# Their labels read in the catalog's platforms axis, which translates
# them.
BUILD_PLATFORMS: dict[str, BuildPlatform] = {
    "apk": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "APK"),
        "apk",
        "apk",
        "build/app/outputs/flutter-apk/app-release.apk",
        "build/apk/*.apk",
        suffix=".apk",
    ),
    "aab": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "AAB"),
        "appbundle",
        "aab",
        "build/app/outputs/bundle/release/app-release.aab",
        "build/aab/*.aab",
        suffix=".aab",
    ),
    "web": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "Web"), "web", "web", "build/web", "build/web"
    ),
    "windows": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "Windows"),
        "windows",
        "windows",
        "build/windows/*/runner/Release",
        "build/windows",
        host="Windows",
    ),
    "linux": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "Linux"),
        "linux",
        "linux",
        "build/linux/*/release/bundle",
        "build/linux",
        host="Linux",
    ),
    "macos": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "macOS"),
        "macos",
        "macos",
        "build/macos/Build/Products/Release/*.app",
        "build/macos/*.app",
        suffix=".app",
        host="Darwin",
    ),
    # Signing is the project's business: Flutter takes it from the team
    # configured in Xcode, Flet from `[tool.flet.ios]` in its
    # `pyproject.toml`.
    "ipa": BuildPlatform(
        QT_TRANSLATE_NOOP("catalog", "iOS"),
        "ipa",
        "ipa",
        "build/ios/ipa/*.ipa",
        "build/ipa/*.ipa",
        suffix=".ipa",
        host="Darwin",
    ),
}


def host_platforms() -> list[str]:
    """Return the platforms that can compile on this machine."""
    return [k for k, p in BUILD_PLATFORMS.items() if not p.host or p.host == HOST.system]


def out_key(platform_id: str) -> str:
    """Return the `config.env` key of the build's folder."""
    return f"BUILD_OUT_{platform_id.upper()}"


def flutter_cmd(override: str = "") -> list[str]:
    """Return the argv prefix for `flutter`."""
    return resolve_executable(
        ["flutter", "flutter.bat", "flutter.cmd", "flutter.exe"],
        override=override,
        label=QCoreApplication.translate("toolchain", "Flutter"),
        hint=QCoreApplication.translate(
            "toolchain", "Instala el SDK Flutter con su capacidad, o agrega flutter al PATH."
        ),
    )


def dart_cmd() -> list[str]:
    """Return the SDK's `dart`, in the same folder as `flutter`."""
    return resolve_executable(
        ["dart", "dart.bat", "dart.exe"],
        label=QCoreApplication.translate("toolchain", "Dart"),
        hint=QCoreApplication.translate(
            "toolchain", "Instala el SDK Flutter con su capacidad, o agrega flutter al PATH."
        ),
    )


def flet_cmd(override: str = "") -> list[str]:
    """Return the argv prefix for `flet`."""
    return resolve_executable(
        ["flet", "flet.bat", "flet.cmd", "flet.exe"],
        override=override,
        label=QCoreApplication.translate("toolchain", "Flet"),
        hint=QCoreApplication.translate("toolchain", "Instala flet en el venv del proyecto."),
    )


def python_cmd() -> list[str]:
    """Return the argv prefix for Python."""
    return resolve_executable(
        ["python", "python3", "python.exe"],
        label=QCoreApplication.translate("toolchain", "Python"),
    )


def pnpm_cmd(override: str = "") -> list[str]:
    """Return the argv prefix for `pnpm`."""
    return resolve_executable(
        ["pnpm", "pnpm.cmd", "pnpm.exe"],
        override=override,
        label="pnpm",
        hint=QCoreApplication.translate("toolchain", "Instálalo con corepack enable pnpm."),
    )


def pyinstaller_cmd(app_dir: Path | None = None) -> list[str]:
    """Return PyInstaller, preferring the venv of the app to package.

    PyInstaller freezes the environment it runs from: the global one
    does not see the project's dependencies and leaves a binary that
    dies at the first import.

    It looks at the same `.venv` the App Python launcher uses
    (`services/tasks/launchers.py`), and prefers it only if PyInstaller
    is really installed there; otherwise it goes to the PATH.
    """
    if app_dir is not None:
        del_venv = _venv_tool(app_dir / ".venv", "pyinstaller")
        if del_venv is not None:
            return [str(del_venv)]
    return resolve_executable(
        ["pyinstaller", "pyinstaller.exe", "pyinstaller.cmd"],
        label="PyInstaller",
        hint=QCoreApplication.translate(
            "toolchain", "Instálalo en el venv de la app: pip install pyinstaller."
        ),
    )


def _venv_tool(venv_dir: Path, name: str) -> Path | None:
    """Return an executable inside a venv, or None if it lacks it."""
    for tool_name in HOST.executable_names(name):
        path = HOST.venv_bin(venv_dir) / tool_name
        if path.is_file():
            return path
    return None


def app_cmd(kind: str) -> list[str]:
    """Return the binary for the detected mobile app type."""
    if kind == FLUTTER:
        return flutter_cmd()
    if kind == FLET:
        return flet_cmd()
    raise TaskError(
        QCoreApplication.translate("toolchain", "Tipo de app desconocido: {0!r}").format(kind)
    )


def venv_python(venv_dir: Path) -> Path:
    """Return a venv's interpreter, in the subfolder each system uses.

    It only locates: it does not relaunch the current process with
    another Python, because here the venv is a subprocess's environment
    and not the app's.
    """
    exe = HOST.venv_python(venv_dir)
    if not exe.is_file():
        raise TaskError(
            QCoreApplication.translate("toolchain", "No existe el Python del venv: {0}").format(
                exe
            )
        )
    return exe


def app_python(app_dir: Path, repo_root: Path) -> list[str]:
    """Return the interpreter a Python app of the repo runs with.

    The app's venv, else the repo root's (a repo with one venv for all),
    and with none the PATH's Python.
    """
    for venv in (app_dir / ".venv", repo_root / ".venv"):
        exe = HOST.venv_python(venv)
        if exe.is_file():
            return [str(exe)]
    return resolve_executable(
        ["python", "python3", "python.exe"],
        label=QCoreApplication.translate("toolchain", "Python"),
        hint=QCoreApplication.translate(
            "toolchain", "Crea el venv de {0} o agrega Python al PATH."
        ).format(app_dir.name),
    )


def detect_app_kind(project_dir: Path) -> str:
    """Tell a Flutter project from a Flet one by their marker files.

    It is the discovered `framework` axis of ADR-0006: declared in no
    catalog by hand, it comes from looking at the open repo.
    """
    pubspec = project_dir / "pubspec.yaml"
    pyproject = project_dir / "pyproject.toml"

    if pubspec.is_file() and pyproject.is_file():
        raise TaskError(
            QCoreApplication.translate(
                "toolchain",
                "{0} tiene pubspec.yaml y pyproject.toml a la vez: no se puede deducir "
                "el framework.",
            ).format(project_dir.name)
        )
    if pubspec.is_file():
        return FLUTTER
    if pyproject.is_file() and "flet" in read_text(pyproject).lower():
        return FLET
    raise TaskError(
        QCoreApplication.translate(
            "toolchain", "{0} no parece un proyecto Flutter ni Flet."
        ).format(project_dir.name)
    )


def devices(ctx: TaskContext, project_dir: Path) -> list[dict[str, Any]]:
    """Return the devices Flutter sees, from its JSON.

    Flet has no detection of its own, since its `flet devices` parses
    the underlying Flutter's text table, so both frameworks ask the same
    way.
    """
    output = ctx.capture([*flutter_cmd(), "devices", "--machine"], cwd=project_dir, timeout=120)
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError as exc:
        raise TaskError(
            QCoreApplication.translate(
                "toolchain", "Respuesta invalida de `flutter devices --machine`."
            )
        ) from exc
    return [d for d in decoded if isinstance(d, dict)] if isinstance(decoded, list) else []


def pick_emulator(found: list[dict[str, Any]]) -> str:
    """Return the active Android emulator's id, or an empty string."""
    for device in found:
        device_id = str(device.get("id") or "").strip()
        platform = str(device.get("targetPlatform") or "").lower()
        if not device_id or not platform.startswith("android"):
            continue
        if device.get("emulator") or device_id.startswith("emulator-"):
            return device_id
    return ""
