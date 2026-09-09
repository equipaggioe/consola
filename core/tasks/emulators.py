from __future__ import annotations
import shlex

from .. import android, cache, files, session
from ..errors import TaskError
from ..registry import registry

"""
Grupo Emulators.

`android_emulator.py` era un solo `run()` que hacia cuatro cosas en fila:
descargar la system image, crear el AVD, parchear su `config.ini` y arrancar el
emulador — las tres primeras escondidas detras de una constante (`pixel_4`,
`pixel_8`, `resizable`) que decidia todo de una vez.

Aca son tres actividades separadas, cada una con su propio catalogo:

  Instalar maquina  ->  elige del catalogo de system images del SDK
  Crear AVD         ->  elige del catalogo de dispositivos + una maquina instalada
  Emulador          ->  elige entre los AVD que ya existen

Ya no hay compuesta que las encadene. Cuando un paso deja de ser "el mismo de
siempre" y pasa a tener opciones propias, deja de caber en una casilla: instalar
una maquina virtual se hace una vez cada varios meses, crear un AVD una vez por
modelo, y arrancar, veinte veces por dia. Encadenarlos obligaria a contestar
tres catalogos para hacer lo que casi siempre es lo tercero.

Apagar no tiene boton en el rail: cerrar la pestana apaga el emulador que esa
pestana lanzo, y los huerfanos se apagan desde la cabecera de estado del panel.
"""

# El serial del ultimo emulador arrancado, para que la app movil no tenga que
# adivinar contra cual correr. Es estado de sesion como `SERVER_PORT`
# (PLAN.md 7, caso 4), pero de la maquina y no de un repo: el emulador no es de
# nadie en particular.
EMULATOR_SERIAL = 'EMULATOR_SERIAL'


# --- instalacion -----------------------------------------------------------

def install_system_image(ctx, image: str = '') -> str:
    """Descarga una maquina virtual del catalogo del SDK si falta.

    Es la parte lenta de todo el grupo — varios GB — y por eso tiene boton
    propio: se hace una vez y despues sirve para todos los AVD que la usen.
    """
    if not image:
        raise TaskError('Elige que maquina virtual instalar.')
    sdk = android.resolve_sdk()
    spec = android.parse_image(image)
    ctx.info(f'Maquina: {spec.label}')
    android.ensure_image(ctx, sdk, image)
    cache.forget('android-installed')
    return image


def create_avd(ctx, device: str = '', image: str = '', name: str = '') -> str:
    """Crea el dispositivo virtual con el modelo y la maquina elegidos.

    Sin nombre propio se deriva del dispositivo y la API (`pixel_4_api36`), que
    es lo que se quiere casi siempre: el nombre solo importa cuando hay dos AVD
    del mismo modelo.
    """
    if not device:
        raise TaskError('Elige un dispositivo del catalogo.')
    if not image:
        raise TaskError('Elige una maquina virtual instalada. Si no hay ninguna, '
                        'instalala primero con "Instalar maquina".')

    sdk = android.resolve_sdk()
    spec = android.AvdSpec(name.strip() or android.suggest_avd_name(device, image),
                           device, image)
    creado = android.ensure_avd(ctx, sdk, spec)
    cache.forget('android-avds')
    ctx.ok(f'AVD listo: {creado}')
    return creado


# --- uso -------------------------------------------------------------------

def launch_emulator(ctx, avd: str = '', wipe: bool = False, flags: str = '') -> str:
    """Arranca un AVD ya creado y sigue su salida hasta que se cierra.

    Tres cosas que el script original no hacia:

    - El puerto se elige antes de arrancar, asi el serial se conoce desde el
      principio: sin eso no hay forma de saber cual de los emuladores vivos es
      el de esta pestana.
    - Si ese AVD ya esta corriendo, la segunda copia va en `-read-only`, que es
      lo unico que permite tener dos abiertos a la vez.
    - Detener la pestana le pide al emulador que se cierre por adb en vez de
      matarle el proceso (PLAN.md 7, caso 3).

    `flags` es una linea de comandos y no una lista: es lo que se escribe en el
    campo del panel, y ahi `-gpu host` son dos tokens escritos juntos. Se suma a
    los flags de siempre en vez de reemplazarlos — quien escribe uno pide *ese
    ademas*, no quedarse sin la animacion de arranque desactivada.
    """
    if not avd:
        raise TaskError('Elige un AVD. Si no hay ninguno, crealo con "Crear AVD".')

    sdk = android.resolve_sdk()
    if avd not in android.list_avds(sdk):
        raise TaskError(f'No existe el AVD "{avd}".')

    vivos = android.running(sdk)
    duplicado = avd in vivos.values()
    if duplicado:
        ctx.info(f'"{avd}" ya esta corriendo: esta copia arranca en solo lectura '
                 '(no guarda cambios en el disco del AVD).')

    puerto = android.free_port(sdk)
    serial = f'emulator-{puerto}'
    ctx.info(f'Arrancando {avd} como {serial}.')

    session.publish(session.MACHINE, EMULATOR_SERIAL, serial)
    ctx.on_cancel(lambda: android.stop_quiet(sdk, serial))
    try:
        android.start(ctx, sdk, avd, port=puerto,
                      flags=[*android.DEFAULT_FLAGS, *shlex.split(flags)],
                      read_only=duplicado, wipe=wipe)
    finally:
        if session.read(session.MACHINE, EMULATOR_SERIAL) == serial:
            session.forget(session.MACHINE, EMULATOR_SERIAL)
        ctx.info(f'{serial} se cerro.')
    return serial


def await_emulator(ctx, timeout: float = 180.0, serial: str = '') -> str:
    """Espera a que un emulador termine de bootear y devuelve su serial.

    No es un boton: nadie pide "espera el boot" suelto. La usan los launchers de
    app movil antes de instalar el APK, porque `flutter run` contra un
    dispositivo que todavia no acepta comandos falla sin explicar por que.
    """
    encontrado = android.wait_for_boot(ctx, android.resolve_sdk(),
                                       timeout=timeout, serial=serial)
    ctx.ok(f'Emulador listo: {encontrado}')
    return encontrado


def stop_emulator(ctx, serial: str = '') -> None:
    """Apaga uno o todos los emuladores vivos.

    Se corre desde el ✕ de la cabecera de estado del panel (los huerfanos: un
    emulador de una sesion anterior, o arrancado desde Android Studio). El
    emulador de una pestana abierta se apaga solo al cerrarla.
    """
    sdk = android.resolve_sdk()
    objetivos = [serial] if serial else android.list_devices(sdk)
    if not objetivos:
        ctx.info('No hay ningun emulador corriendo.')
        return
    for uno in objetivos:
        android.stop(ctx, sdk, uno)


# --- limpieza --------------------------------------------------------------

def purge_emulators(ctx, avds: list[str] | None = None, images: list[str] | None = None,
                    apply: bool = False) -> dict[str, list[str]]:
    """Borra los AVD y las maquinas virtuales marcados, con simulacro primero.

    `purge_avds.py` y `purge_system_images.py` borraban *todo* y sin preguntar,
    a un clic de distancia de perder los emuladores configurados (PLAN.md 7,
    caso 5). Aca se elige que se borra, se ve la lista con su tamano, y recien
    despues se pide escribir BORRAR.
    """
    sdk = android.resolve_sdk()
    avds = list(avds or [])
    images = list(images or [])
    if not avds and not images:
        ctx.info('No hay nada marcado para borrar.')
        return {'avds': [], 'images': []}

    if avds:
        ctx.warn(f'AVD a borrar ({len(avds)}):')
        for nombre in avds:
            ruta = android.avd_home() / f'{nombre}.avd'
            peso = files.human_size(files.size_of(ruta)) if ruta.exists() else '?'
            ctx.info(f'  {nombre}  ({peso})')
    if images:
        ctx.warn(f'Maquinas virtuales a desinstalar ({len(images)}):')
        for paquete in images:
            ctx.info(f'  {android.parse_image(paquete).label}')

    if not apply:
        ctx.info('Simulacro: no se borro nada. Marca "borrar" para confirmar.')
        return {'avds': avds, 'images': images}

    total = len(avds) + len(images)
    if not ctx.confirm(f'Escribe BORRAR para eliminar {total} elemento(s).',
                       danger=True, expect='BORRAR'):
        ctx.warn('Cancelado: no se borro nada.')
        return {'avds': [], 'images': []}

    for nombre in avds:
        android.remove_avd(ctx, sdk, nombre)
        ctx.ok(f'AVD eliminado: {nombre}')
    for paquete in images:
        android.remove_image(ctx, sdk, paquete)
        ctx.ok(f'Maquina desinstalada: {paquete}')

    cache.forget('android-avds')
    cache.forget('android-installed')
    ctx.note(f'Limpieza de emuladores: {len(avds)} AVD, {len(images)} maquina(s).')
    return {'avds': avds, 'images': images}


def inventory(ctx=None) -> dict[str, list[str]]:
    """Lo que hay en la maquina ahora mismo. No corre nada, solo mira."""
    sdk = android.resolve_sdk()
    return {
        'avds': android.list_avds(sdk),
        'imagenes': android.list_images(sdk),
        'corriendo': android.list_devices(sdk),
    }


def bind_all() -> None:
    registry.bind('install_system_image', install_system_image)
    registry.bind('create_avd', create_avd)
    registry.bind('launch_emulator', launch_emulator)
    registry.bind('stop_emulator', stop_emulator)
    registry.bind('purge_emulators', purge_emulators)
