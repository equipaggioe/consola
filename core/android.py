from __future__ import annotations
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import TaskError
from .process import capture, which_any

_TOOLS = {
    'adb': ('platform-tools',),
    'emulator': ('emulator',),
    'avdmanager': ('cmdline-tools', 'latest', 'bin'),
    'sdkmanager': ('cmdline-tools', 'latest', 'bin'),
}


def sdk_root() -> Path | None:
    for var in ('ANDROID_SDK_ROOT', 'ANDROID_HOME'):
        value = (os.environ.get(var) or '').strip()
        if value:
            return Path(value)
    return None


@dataclass(frozen=True)
class Sdk:
    """Las cuatro herramientas del SDK que Consola necesita, ya localizadas.

    Los scripts resolvian cada binario por separado y en cada archivo. Aca se
    resuelve el SDK una vez y de ahi salen todas: si falta una, se dice cual y
    donde se buscaba, en vez de fallar mas tarde con 'comando no encontrado'.
    """
    root: Path | None

    def tool(self, name: str) -> str:
        subpath = _TOOLS.get(name)
        if subpath is None:
            raise TaskError(f'Herramienta desconocida del SDK: {name}')

        exe = f'{name}.exe' if os.name == 'nt' else name
        bat = f'{name}.bat' if os.name == 'nt' else name

        if self.root:
            for candidate in (self.root.joinpath(*subpath, exe), self.root.joinpath(*subpath, bat)):
                if candidate.is_file():
                    return str(candidate)
            raise TaskError(
                f'No se encontro "{name}" dentro del SDK ({self.root}). '
                f'Esperado en: {self.root.joinpath(*subpath)}'
            )

        found = which_any([exe, bat])
        if found:
            return found
        raise TaskError(
            f'No se encontro "{name}". Define ANDROID_SDK_ROOT o instala el SDK '
            'con la capacidad SDK Android.'
        )

    @property
    def adb(self) -> str:
        return self.tool('adb')

    @property
    def emulator(self) -> str:
        return self.tool('emulator')


def resolve_sdk() -> Sdk:
    return Sdk(sdk_root())


def avd_home() -> Path:
    configured = (os.environ.get('ANDROID_AVD_HOME') or '').strip()
    return Path(configured) if configured else Path.home() / '.android' / 'avd'


# --- presets ---------------------------------------------------------------

@dataclass(frozen=True)
class Preset:
    """Un perfil de emulador. Los tres `run_emulator_N.py` eran este mismo flujo
    con una constante distinta: aca son valores del eje `preset` (PLAN.md 2.4)."""
    name: str
    device: str
    api_level: str = '36'
    abi: str = 'x86_64'
    target: str = 'google_apis'

    @property
    def image(self) -> str:
        return f'system-images;android-{self.api_level};{self.target};{self.abi}'


PRESETS: dict[str, Preset] = {
    'pixel_4': Preset('pixel_4', 'pixel_4'),
    'pixel_8': Preset('pixel_8', 'pixel_8'),
    'resizable': Preset('resizable', 'resizable'),
}

DEFAULT_FLAGS = ['-no-boot-anim', '-netdelay', 'none', '-netspeed', 'full']


def preset(name: str) -> Preset:
    if name not in PRESETS:
        raise TaskError(f'Perfil de emulador desconocido: {name!r}')
    return PRESETS[name]


# --- inventario ------------------------------------------------------------

def list_avds(sdk: Sdk) -> list[str]:
    salida = capture([sdk.emulator, '-list-avds'], timeout=60, check=False)
    return [line.strip() for line in salida.splitlines() if line.strip() and ' ' not in line.strip()]


def list_images(sdk: Sdk) -> list[str]:
    """System images instaladas, segun el propio sdkmanager."""
    salida = capture([sdk.tool('sdkmanager'), '--list_installed'], timeout=180, check=False)
    return [line.split('|')[0].strip() for line in salida.splitlines()
            if line.strip().startswith('system-images;')]


def list_devices(sdk: Sdk) -> list[str]:
    """Seriales de emuladores vivos, preguntandole a adb.

    El emulador se desprende del proceso que lo lanzo (PLAN.md 7, caso 3), asi
    que su estado no se puede inferir de un PID: hay que sondearlo.
    """
    salida = capture([sdk.adb, 'devices'], timeout=30, check=False)
    return [line.split()[0] for line in salida.splitlines()[1:]
            if line.strip().endswith('device') and line.startswith('emulator-')]


# --- ciclo de vida ---------------------------------------------------------

def ensure_image(ctx, sdk: Sdk, image: str) -> None:
    if image in list_images(sdk):
        ctx.ok(f'System image ya instalada: {image}')
        return
    ctx.info(f'Instalando system image: {image}')
    ctx.run([sdk.tool('sdkmanager'), image])


def ensure_avd(ctx, sdk: Sdk, spec: Preset) -> str:
    """Crea el AVD si falta y le deja el teclado de hardware activo.

    Sin `hw.keyboard=yes` el emulador ignora el teclado real y hay que tipear
    en la pantalla tactil, que es lo que el script original venia parcheando.
    """
    if spec.name in list_avds(sdk):
        ctx.info(f'El AVD "{spec.name}" ya existe.')
    else:
        ctx.info(f'Creando AVD "{spec.name}" ({spec.device}).')
        ctx.run([sdk.tool('avdmanager'), 'create', 'avd', '--name', spec.name,
                 '--package', spec.image, '--device', spec.device])
    _enable_hw_keyboard(ctx, spec.name)
    return spec.name


def _enable_hw_keyboard(ctx, avd_name: str) -> None:
    config = avd_home() / f'{avd_name}.avd' / 'config.ini'
    if not config.is_file():
        ctx.warn(f'No se encontro config.ini del AVD "{avd_name}".')
        return

    lines = config.read_text(encoding='utf-8').splitlines()
    lines = [line for line in lines if not line.strip().startswith('hw.keyboard=')]
    lines.append('hw.keyboard=yes')
    config.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')


def start(ctx, sdk: Sdk, avd_name: str, *, flags: list[str] | None = None) -> int:
    """Arranca el emulador y sigue su salida mientras viva."""
    return ctx.run([sdk.emulator, '-avd', avd_name, *(flags or DEFAULT_FLAGS)], check=False)


def wait_for_boot(ctx, sdk: Sdk, *, timeout: float = 180.0) -> str:
    """Espera a que un emulador termine de arrancar y devuelve su serial."""
    limite = time.time() + timeout
    while time.time() < limite:
        ctx.raise_if_cancelled()
        for serial in list_devices(sdk):
            listo = capture([sdk.adb, '-s', serial, 'shell', 'getprop', 'sys.boot_completed'],
                            timeout=15, check=False)
            if listo.strip() == '1':
                return serial
        time.sleep(2)
    raise TaskError(f'Ningun emulador termino de arrancar en {timeout:.0f}s.')


def stop(ctx, sdk: Sdk, serial: str) -> None:
    """Apaga el emulador por adb: matar el proceso que lo lanzo no alcanza."""
    ctx.run([sdk.adb, '-s', serial, 'emu', 'kill'], check=False)
    ctx.ok(f'Emulador {serial} detenido.')


def remove_avd(ctx, sdk: Sdk, name: str) -> None:
    ctx.run([sdk.tool('avdmanager'), 'delete', 'avd', '--name', name], check=False)


def remove_image(ctx, sdk: Sdk, image: str) -> None:
    ctx.run([sdk.tool('sdkmanager'), '--uninstall', image], check=False)
