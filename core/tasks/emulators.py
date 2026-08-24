from __future__ import annotations

from .. import android, files
from ..errors import TaskError
from ..registry import registry

"""
Grupo Emulators.

`android_emulator.py` era un solo `run()` que hacia cuatro cosas en fila:
descargar la system image, crear el AVD, parchear su `config.ini` y arrancar el
emulador. Ninguna de las cuatro era invocable por separado, asi que "solo crear
la maquina sin arrancarla" o "solo bajar la imagen" no existian como operacion.

Aca son cuatro atomicas con boton propio, y `start_emulator` es la compuesta que
las encadena en el mismo orden. Cada una detecta su estado antes de actuar, asi
que correr la compuesta dos veces no vuelve a descargar ni a recrear nada.
"""


# --- atomicas --------------------------------------------------------------

def install_system_image(ctx, preset: str = 'pixel_4') -> str:
    """Descarga la system image del perfil si todavia no esta instalada."""
    spec = android.preset(preset)
    android.ensure_image(ctx, android.resolve_sdk(), spec.image)
    return spec.image


def create_avd(ctx, preset: str = 'pixel_4') -> str:
    """Crea la maquina virtual del perfil. Requiere que la imagen ya este."""
    spec = android.preset(preset)
    sdk = android.resolve_sdk()
    if spec.image not in android.list_images(sdk):
        raise TaskError(
            f'Falta la system image {spec.image}. Corre "Descargar imagen" primero '
            'o usa el boton compuesto.'
        )
    return android.ensure_avd(ctx, sdk, spec)


def launch_emulator(ctx, preset: str = 'pixel_4', flags: list[str] | None = None) -> int:
    """Arranca el emulador y sigue su salida. No espera a que termine de bootear."""
    spec = android.preset(preset)
    sdk = android.resolve_sdk()
    if spec.name not in android.list_avds(sdk):
        raise TaskError(f'No existe el AVD "{spec.name}". Crea el AVD primero.')
    ctx.info(f'Arrancando emulador {spec.name} ({spec.device}).')
    return android.start(ctx, sdk, spec.name, flags=flags)


def await_emulator(ctx, timeout: float = 180.0) -> str:
    """Espera a que un emulador termine de bootear y devuelve su serial.

    Lo usan los launchers de app movil antes de instalar el APK: sin esto,
    `flutter run` arranca contra un dispositivo que todavia no acepta comandos.
    """
    serial = android.wait_for_boot(ctx, android.resolve_sdk(), timeout=timeout)
    ctx.ok(f'Emulador listo: {serial}')
    return serial


def stop_emulator(ctx, serial: str = '') -> None:
    """Apaga uno o todos los emuladores vivos."""
    sdk = android.resolve_sdk()
    objetivos = [serial] if serial else android.list_devices(sdk)
    if not objetivos:
        ctx.info('No hay ningun emulador corriendo.')
        return
    for uno in objetivos:
        android.stop(ctx, sdk, uno)


def delete_avd(ctx, name: str) -> None:
    android.remove_avd(ctx, android.resolve_sdk(), name)
    ctx.ok(f'AVD eliminado: {name}')


def delete_system_image(ctx, image: str) -> None:
    android.remove_image(ctx, android.resolve_sdk(), image)
    ctx.ok(f'System image eliminada: {image}')


# --- compuestas ------------------------------------------------------------

def start_emulator(
    ctx,
    preset: str = 'pixel_4',
    *,
    install_image: bool = True,
    create: bool = True,
    launch: bool = True,
) -> None:
    """Compuesta: descargar imagen -> crear AVD -> arrancar.

    Los tres pasos son casillas del panel porque cada uno tiene sentido suelto:
    bajar la imagen puede tardar diez minutos y conviene hacerlo una vez.
    """
    if install_image:
        ctx.step('System image')
        install_system_image(ctx, preset)
    if create:
        ctx.step('AVD')
        create_avd(ctx, preset)
    if launch:
        ctx.step('Emulador')
        launch_emulator(ctx, preset)


def purge_avds(ctx, apply: bool = False) -> list[str]:
    """Destructivo con simulacro: primero la lista exacta, despues el borrado.

    `purge_avds.py` borraba sin preguntar, a un clic de distancia de perder
    todos los emuladores configurados (PLAN.md 7, caso 5).
    """
    sdk = android.resolve_sdk()
    encontrados = android.list_avds(sdk)
    if not encontrados:
        ctx.info('No hay AVDs para borrar.')
        return []

    ctx.warn(f'Se van a borrar {len(encontrados)} AVD(s):')
    for nombre in encontrados:
        ruta = android.avd_home() / f'{nombre}.avd'
        ctx.info(f'  {nombre}  ({files.human_size(files.size_of(ruta)) if ruta.exists() else "?"})')

    if not apply:
        ctx.info('Simulacro: no se borro nada. Marca "Aplicar" para confirmar.')
        return encontrados

    if not ctx.confirm(f'Escribe BORRAR para eliminar {len(encontrados)} AVD(s).',
                       danger=True, expect='BORRAR'):
        ctx.warn('Cancelado: no se borro nada.')
        return []

    for nombre in encontrados:
        delete_avd(ctx, nombre)
    ctx.note(f'Purga de AVDs: {len(encontrados)} eliminados.')
    return encontrados


def purge_system_images(ctx, apply: bool = False) -> list[str]:
    """Mismo patron que `purge_avds`, sobre las imagenes descargadas del SDK."""
    sdk = android.resolve_sdk()
    encontradas = android.list_images(sdk)
    if not encontradas:
        ctx.info('No hay system images instaladas.')
        return []

    ctx.warn(f'Se van a desinstalar {len(encontradas)} imagen(es):')
    for imagen in encontradas:
        ctx.info(f'  {imagen}')

    if not apply:
        ctx.info('Simulacro: no se desinstalo nada. Marca "Aplicar" para confirmar.')
        return encontradas

    if not ctx.confirm(f'Escribe BORRAR para desinstalar {len(encontradas)} imagen(es).',
                       danger=True, expect='BORRAR'):
        ctx.warn('Cancelado: no se desinstalo nada.')
        return []

    for imagen in encontradas:
        delete_system_image(ctx, imagen)
    return encontradas


def inventory(ctx) -> dict[str, list[str]]:
    """Lo que muestra el Gestor de AVD: no corre nada, solo mira."""
    sdk = android.resolve_sdk()
    return {
        'avds': android.list_avds(sdk),
        'imagenes': android.list_images(sdk),
        'corriendo': android.list_devices(sdk),
    }


def bind_all() -> None:
    registry.bind('start_emulator', start_emulator)
    registry.bind('avd_manager', inventory)
    registry.bind('purge_avds', purge_avds)
    registry.bind('purge_images', purge_system_images)
