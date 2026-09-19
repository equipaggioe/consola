from __future__ import annotations
import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path

from .errors import TaskError
from .files import read_text
from .process import resolve_executable

FLUTTER = 'flutter'
FLET = 'flet'


@dataclass(frozen=True)
class BuildPlatform:
    """Una plataforma a la que `build_flutter` sabe compilar.

    Las salidas son globs relativos a la carpeta de la app: donde deja el build
    cada framework sin que nadie le diga nada. Flet copia lo suyo a
    `build/<plataforma>/`, Flutter lo deja enterrado en su arbol de siempre.
    """
    label: str
    flutter: str        # subcomando de `flutter build`
    flet: str           # plataforma de `flet build`
    flutter_out: str
    flet_out: str
    suffix: str = ''    # extension de un build que es una pieza (`.apk`). Vacio:
                        # el build es una carpeta entera (web, escritorio).
    host: str = ''      # `platform.system()` donde unicamente se puede compilar.
                        # Ni Flutter ni Flet compilan escritorio o iOS para otro
                        # sistema que el que corre.

    def output(self, kind: str) -> str:
        return self.flutter_out if kind == FLUTTER else self.flet_out


BUILD_PLATFORMS: dict[str, BuildPlatform] = {
    'apk': BuildPlatform('APK', 'apk', 'apk',
                         'build/app/outputs/flutter-apk/app-release.apk',
                         'build/apk/*.apk', suffix='.apk'),
    'aab': BuildPlatform('AAB', 'appbundle', 'aab',
                         'build/app/outputs/bundle/release/app-release.aab',
                         'build/aab/*.aab', suffix='.aab'),
    'web': BuildPlatform('Web', 'web', 'web', 'build/web', 'build/web'),
    'windows': BuildPlatform('Windows', 'windows', 'windows',
                             'build/windows/*/runner/Release', 'build/windows',
                             host='Windows'),
    'linux': BuildPlatform('Linux', 'linux', 'linux',
                           'build/linux/*/release/bundle', 'build/linux', host='Linux'),
    'macos': BuildPlatform('macOS', 'macos', 'macos',
                           'build/macos/Build/Products/Release/*.app',
                           'build/macos/*.app', suffix='.app', host='Darwin'),
    # Firmar es asunto del proyecto: Flutter lo toma del equipo configurado en
    # Xcode, Flet de `[tool.flet.ios]` en su `pyproject.toml`.
    'ipa': BuildPlatform('iOS', 'ipa', 'ipa', 'build/ios/ipa/*.ipa', 'build/ipa/*.ipa',
                         suffix='.ipa', host='Darwin'),
}


def host_platforms() -> list[str]:
    """Las plataformas que se pueden compilar en esta maquina."""
    return [k for k, p in BUILD_PLATFORMS.items() if not p.host or p.host == platform.system()]


def out_key(platform_id: str) -> str:
    """La clave de `config.env` con la carpeta donde queda el build."""
    return f'BUILD_OUT_{platform_id.upper()}'


def flutter_cmd(override: str = '') -> list[str]:
    return resolve_executable(
        ['flutter', 'flutter.bat', 'flutter.cmd', 'flutter.exe'],
        override=override, label='Flutter',
        hint='Instala el SDK Flutter con su capacidad, o agrega flutter al PATH.',
    )


def flet_cmd(override: str = '') -> list[str]:
    return resolve_executable(
        ['flet', 'flet.bat', 'flet.cmd', 'flet.exe'],
        override=override, label='Flet', hint='Instala flet en el venv del proyecto.',
    )


def npm_cmd(override: str = '') -> list[str]:
    return resolve_executable(
        ['npm', 'npm.cmd', 'npm.exe'], override=override, label='npm',
        hint='Instala Node.js.',
    )


def pyinstaller_cmd(app_dir: Path | None = None, override: str = '') -> list[str]:
    """PyInstaller, prefiriendo el del venv de la app que se va a empaquetar.

    PyInstaller congela el entorno desde el que corre: el global no ve las
    dependencias del proyecto y deja un binario que muere al primer import. El
    script original resolvia solo por PATH (o `PYINSTALLER_BIN`), asi que
    empaquetar bien dependia de haber activado el venv correcto antes de
    lanzarlo — algo que un boton no puede pedir.

    Se mira el mismo `.venv` que usa el launcher de la terminal
    (`core/tasks/launchers.py`), y solo se prefiere si PyInstaller esta
    realmente instalado ahi; si no, se cae al PATH como antes.
    """
    if not override and app_dir is not None:
        del_venv = _venv_tool(app_dir / '.venv', 'pyinstaller')
        if del_venv is not None:
            return [str(del_venv)]
    return resolve_executable(
        ['pyinstaller', 'pyinstaller.exe', 'pyinstaller.cmd'],
        override=override, label='PyInstaller',
        hint='Instalalo en el venv de la app (pip install pyinstaller) o '
             'escribe su ruta en PYINSTALLER_BIN.',
    )


def _venv_tool(venv_dir: Path, name: str) -> Path | None:
    """Un ejecutable dentro de un venv, o None si ese venv no lo tiene."""
    carpeta = venv_dir / ('Scripts' if os.name == 'nt' else 'bin')
    nombres = (f'{name}.exe', f'{name}.cmd', name) if os.name == 'nt' else (name,)
    for nombre in nombres:
        ruta = carpeta / nombre
        if ruta.is_file():
            return ruta
    return None


def app_cmd(kind: str) -> list[str]:
    """El binario que corresponde al tipo de app movil detectado."""
    if kind == FLUTTER:
        return flutter_cmd()
    if kind == FLET:
        return flet_cmd()
    raise TaskError(f'Tipo de app desconocido: {kind!r}')


def venv_python(venv_dir: Path) -> Path:
    """El interprete de un venv, en el subdirectorio que use cada sistema.

    Solo ubica: a diferencia de los scripts, no relanza el proceso actual con
    otro Python (`os.execv`) porque aca el venv es el entorno de un subproceso,
    no el de la app.
    """
    exe = venv_dir / ('Scripts' if os.name == 'nt' else 'bin') / ('python.exe' if os.name == 'nt' else 'python')
    if not exe.is_file():
        raise TaskError(f'No existe el Python del venv: {exe}')
    return exe


def detect_app_kind(project_dir: Path) -> str:
    """Distingue un proyecto Flutter de uno Flet por sus marcadores de archivo.

    Es el eje `framework` descubierto de PLAN.md 2.4: no se declara a mano en
    ningun catalogo, sale de mirar el repo abierto.
    """
    pubspec = project_dir / 'pubspec.yaml'
    pyproject = project_dir / 'pyproject.toml'

    if pubspec.is_file() and pyproject.is_file():
        raise TaskError(
            f'{project_dir.name} tiene pubspec.yaml y pyproject.toml a la vez: '
            'no se puede deducir el framework.'
        )
    if pubspec.is_file():
        return FLUTTER
    if pyproject.is_file() and 'flet' in read_text(pyproject).lower():
        return FLET
    raise TaskError(f'{project_dir.name} no parece un proyecto Flutter ni Flet.')


def devices(ctx, project_dir: Path) -> list[dict]:
    """Dispositivos que ve Flutter, en JSON.

    Flet no tiene deteccion propia (su `flet devices` parsea la tabla de texto
    del Flutter subyacente), asi que ambos frameworks preguntan por el mismo lado.
    """
    salida = ctx.capture([*flutter_cmd(), 'devices', '--machine'], cwd=project_dir, timeout=120)
    try:
        decoded = json.loads(salida)
    except json.JSONDecodeError as exc:
        raise TaskError('Respuesta invalida de `flutter devices --machine`.') from exc
    return [d for d in decoded if isinstance(d, dict)] if isinstance(decoded, list) else []


def pick_emulator(found: list[dict]) -> str:
    """Id del emulador Android activo, o cadena vacia si no hay ninguno."""
    for device in found:
        device_id = str(device.get('id') or '').strip()
        plataforma = str(device.get('targetPlatform') or '').lower()
        if not device_id or not plataforma.startswith('android'):
            continue
        if device.get('emulator') or device_id.startswith('emulator-'):
            return device_id
    return ''
