from __future__ import annotations
import json
import os
from pathlib import Path

from .errors import TaskError
from .files import read_text
from .process import resolve_executable

FLUTTER = 'flutter'
FLET = 'flet'


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
