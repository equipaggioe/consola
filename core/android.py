from __future__ import annotations
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import cache, ports
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

# --- catalogos y perfiles --------------------------------------------------

@dataclass(frozen=True)
class Device:
    """Un perfil de hardware del catalogo de `avdmanager list device`.

    Los tres `run_emulator_N.py` traian tres ids escritos a mano (`pixel_4`,
    `pixel_8`, `resizable`). El SDK publica el catalogo completo — un centenar
    de telefonos, tablets, relojes y televisores — asi que elegir dispositivo
    deja de ser una constante del codigo y pasa a ser un eje del panel.
    """
    id: str
    name: str = ''
    oem: str = ''
    tag: str = ''

    @property
    def label(self) -> str:
        partes = [self.name or self.id]
        if self.oem and self.oem.lower() != 'generic':
            partes.append(self.oem)
        return '  |  '.join(partes)

    @property
    def order(self) -> tuple:
        """Telefonos y tablets primero; TV, reloj, auto y demas, despues.

        El catalogo viene ordenado por id, y asi la lista abre en
        "AI Glasses" — un dispositivo que casi nadie emula. Lo que se elige el
        99% de las veces es un telefono.
        """
        familia = f'{self.tag} {self.id}'.lower()
        for marca in ('tv', 'wear', 'automotive', 'desktop', 'glasses', 'xr'):
            if marca in familia:
                return (4, self.name or self.id)
        for rango, marcas in enumerate((('pixel',),
                                        ('phone', 'nexus'),
                                        ('tablet', 'foldable', 'resizable'))):
            if any(m in familia for m in marcas):
                return (rango, self.name or self.id)
        return (3, self.name or self.id)


@dataclass(frozen=True)
class Image:
    """Una system image: la maquina virtual que el AVD va a correr.

    `package` es el id que entiende sdkmanager
    (`system-images;android-36;google_apis;x86_64`); el resto son sus tres
    partes ya separadas, que es como se lee al elegir.
    """
    package: str
    api: str = ''
    variant: str = ''
    abi: str = ''

    @property
    def label(self) -> str:
        if not self.api:
            return self.package
        return f'Android {self.api}  |  {VARIANTS.get(self.variant, self.variant)}  |  {self.abi}'

    @property
    def order(self) -> tuple:
        """Lo que se elige casi siempre, primero.

        API nueva antes que vieja; dentro de una API, las variantes de telefono
        antes que las de TV o reloj; y dentro de una variante, la arquitectura
        de la maquina antes que la emulada. Sin esto, un catalogo ordenado
        alfabeticamente abre en "Android TV | arm64", que no quiere casi nadie.
        """
        try:
            api = int(self.api)
        except ValueError:
            api = 0
        return (-api, _VARIANT_RANK.get(self.variant, 9), _ABI_RANK.get(self.abi, 9),
                self.variant, self.abi)


@dataclass(frozen=True)
class AvdSpec:
    """Lo que hace falta para crear un AVD: un dispositivo y una maquina.

    Reemplaza al viejo `Preset`, que ataba las dos cosas en una constante. Ahora
    se eligen por separado porque se instalan por separado: la imagen se baja
    una vez y sirve para todos los AVD que la usen.
    """
    name: str
    device: str
    image: str


# Nombre legible de cada variante de system image. Lo que no este listado se
# muestra tal cual: el catalogo del SDK gana variantes con cada version, y una
# etiqueta cruda es mejor que esconder la opcion.
VARIANTS = {
    'default': 'Android puro',
    'google_apis': 'Google APIs',
    'google_apis_playstore': 'Google APIs + Play Store',
    'android-tv': 'Android TV',
    'google-tv': 'Google TV',
    'android-wear': 'Wear OS',
    'android-automotive': 'Automotive',
    'aosp_atd': 'AOSP ATD (liviana)',
    'google_atd': 'Google ATD (liviana)',
}

# Orden de preferencia dentro de una misma API. Lo que no este listado va al
# final, en orden alfabetico: son las variantes de nicho (TV, reloj, auto).
_VARIANT_RANK = {'google_apis_playstore': 0, 'google_apis': 1, 'default': 2,
                 'google_atd': 3, 'aosp_atd': 4}
_ABI_RANK = {'x86_64': 0, 'arm64-v8a': 1, 'x86': 2}

DEFAULT_FLAGS = ['-no-boot-anim', '-netdelay', 'none', '-netspeed', 'full']

# Rango de puertos que acepta el emulador: pares, de 5554 a 5584. El impar
# siguiente lo usa adb para hablarle, por eso se salta de dos en dos.
PORT_RANGE = range(5554, 5586, 2)

_DEVICE_CACHE = 'android-devices'
_IMAGE_CACHE = 'android-images'


def device_catalog(sdk: Sdk, *, refresh: bool = False) -> list[Device]:
    """Todos los perfiles de dispositivo que ofrece el SDK.

    Cacheado en disco (`core/cache.py`): la consulta tarda varios segundos y el
    catalogo cambia cuando se actualiza el SDK, no durante una sesion.
    """
    crudos = cache.cached(_DEVICE_CACHE, lambda: _read_device_catalog(sdk), refresh=refresh)
    return sorted((Device(**d) for d in crudos), key=lambda d: d.order)


def _read_device_catalog(sdk: Sdk) -> list[dict]:
    salida = capture([sdk.tool('avdmanager'), 'list', 'device'], timeout=120, check=False)
    dispositivos: list[dict] = []
    actual: dict | None = None
    for linea in salida.splitlines():
        limpia = linea.strip()
        if limpia.startswith('id:'):
            # `id: 9 or "pixel_4"` — el id util es el entrecomillado, no el
            # numero: el numero cambia de posicion con cada version del SDK.
            if actual:
                dispositivos.append(actual)
            partes = limpia.split('"')
            actual = {'id': partes[1] if len(partes) > 1 else limpia.split(':', 1)[1].strip()}
        elif actual is not None and ':' in limpia:
            clave, _, valor = limpia.partition(':')
            campo = clave.strip().lower()
            if campo in ('name', 'oem', 'tag'):
                actual[campo] = valor.strip()
    if actual:
        dispositivos.append(actual)
    return dispositivos


def image_catalog(sdk: Sdk, *, refresh: bool = False) -> list[Image]:
    """Todas las system images publicadas, esten instaladas o no."""
    paquetes = cache.cached(_IMAGE_CACHE, lambda: _read_image_catalog(sdk), refresh=refresh)
    return sorted((parse_image(p) for p in paquetes), key=lambda i: i.order)


def _read_image_catalog(sdk: Sdk) -> list[str]:
    salida = capture([sdk.tool('sdkmanager'), '--list'], timeout=600, check=False)
    vistos: list[str] = []
    for linea in salida.splitlines():
        paquete = linea.split('|')[0].strip()
        if paquete.startswith('system-images;') and paquete not in vistos:
            vistos.append(paquete)
    return vistos


def parse_image(package: str) -> Image:
    """`system-images;android-36;google_apis;x86_64` -> sus tres partes."""
    partes = package.split(';')
    if len(partes) < 4:
        return Image(package)
    return Image(package, partes[1].replace('android-', ''), partes[2], partes[3])


def forget_catalogs() -> None:
    """Invalida los dos catalogos. La llama quien acaba de tocar el SDK."""
    cache.forget(_DEVICE_CACHE)
    cache.forget(_IMAGE_CACHE)


def suggest_avd_name(device: str, image: str) -> str:
    """Nombre por defecto de un AVD nuevo: dispositivo + API.

    `avdmanager` solo acepta letras, numeros, guion, punto y guion bajo.
    """
    api = parse_image(image).api
    crudo = f'{device}_api{api}' if api else device
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in crudo)


# --- inventario ------------------------------------------------------------

def list_avds(sdk: Sdk) -> list[str]:
    salida = capture([sdk.emulator, '-list-avds'], timeout=60, check=False)
    return [line.strip() for line in salida.splitlines() if line.strip() and ' ' not in line.strip()]


def list_images(sdk: Sdk) -> list[str]:
    """System images instaladas, segun el propio sdkmanager.

    Sin cache, a diferencia del catalogo: esto cambia cada vez que alguien
    instala o desinstala una, y una lista vieja aca haria que "Crear AVD"
    ofrezca una imagen que ya no esta.
    """
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


def running(sdk: Sdk) -> dict[str, str]:
    """Serial -> nombre del AVD, para cada emulador vivo.

    El serial solo dice el puerto; para saber *que* AVD es hay que
    preguntarselo a la consola del propio emulador. Es lo que permite avisar
    que un AVD ya esta corriendo antes de lanzarlo por segunda vez.
    """
    vivos: dict[str, str] = {}
    for serial in list_devices(sdk):
        salida = capture([sdk.adb, '-s', serial, 'emu', 'avd', 'name'],
                         timeout=15, check=False)
        nombre = next((l.strip() for l in salida.splitlines()
                       if l.strip() and l.strip() != 'OK'), '')
        vivos[serial] = nombre
    return vivos


def free_port(sdk: Sdk) -> int:
    """Un puerto de emulador libre.

    Se elige aca y se le pasa con `-port` en vez de dejar que lo elija el
    emulador: asi el serial (`emulator-5554`) se conoce ANTES de arrancar, y
    con el se puede apagar limpio al cerrar la pestana y decirle a la app movil
    contra que dispositivo correr. Sin esto habria que adivinar cual de los
    emuladores vivos es el que lanzo esta pestana.
    """
    ocupados = {s.rsplit('-', 1)[-1] for s in list_devices(sdk)}
    for port in PORT_RANGE:
        if str(port) not in ocupados and ports.is_free(port, host='127.0.0.1'):
            return port
    raise TaskError('No quedan puertos de emulador libres (5554-5584).')


# --- ciclo de vida ---------------------------------------------------------

def ensure_image(ctx, sdk: Sdk, image: str) -> None:
    if image in list_images(sdk):
        ctx.ok(f'System image ya instalada: {image}')
        return
    ctx.info(f'Instalando system image: {image}')
    ctx.run([sdk.tool('sdkmanager'), image])


def ensure_avd(ctx, sdk: Sdk, spec: AvdSpec) -> str:
    """Crea el AVD si falta y le deja el teclado de hardware activo.

    Sin `hw.keyboard=yes` el emulador ignora el teclado real y hay que tipear
    en la pantalla tactil, que es lo que el script original venia parcheando.
    """
    if spec.name in list_avds(sdk):
        ctx.info(f'El AVD "{spec.name}" ya existe.')
    else:
        if spec.image not in list_images(sdk):
            raise TaskError(
                f'La maquina {spec.image} no esta instalada. '
                'Instalala primero con "Instalar maquina".'
            )
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


def start(ctx, sdk: Sdk, avd_name: str, *, port: int, flags: list[str] | None = None,
          read_only: bool = False, wipe: bool = False) -> int:
    """Arranca el emulador en un puerto fijo y sigue su salida mientras viva.

    `read_only` es lo que permite levantar un AVD que ya esta corriendo: el
    emulador toma un lock sobre la carpeta del AVD, y sin este flag el segundo
    arranque muere con "another emulator instance is running". La segunda copia
    no escribe cambios en el disco del AVD, que es exactamente lo que se quiere
    cuando se abren dos para probar algo entre ellos.
    """
    argv = [sdk.emulator, '-avd', avd_name, '-port', str(port), *(flags or DEFAULT_FLAGS)]
    if read_only:
        argv.append('-read-only')
    if wipe:
        argv.append('-wipe-data')
    return ctx.run(argv, check=False)


def wait_for_boot(ctx, sdk: Sdk, *, timeout: float = 180.0, serial: str = '') -> str:
    """Espera a que un emulador termine de arrancar y devuelve su serial.

    Con `serial` espera a ESE y no al primero que aparezca: con dos emuladores
    vivos, "el primero" es una loteria.
    """
    limite = time.time() + timeout
    while time.time() < limite:
        ctx.raise_if_cancelled()
        for encontrado in ([serial] if serial else list_devices(sdk)):
            listo = capture([sdk.adb, '-s', encontrado, 'shell', 'getprop', 'sys.boot_completed'],
                            timeout=15, check=False)
            if listo.strip() == '1':
                return encontrado
        time.sleep(2)
    raise TaskError(f'Ningun emulador termino de arrancar en {timeout:.0f}s.')


def stop(ctx, sdk: Sdk, serial: str) -> None:
    """Apaga el emulador por adb: matar el proceso que lo lanzo no alcanza."""
    ctx.run([sdk.adb, '-s', serial, 'emu', 'kill'], check=False)
    ctx.ok(f'Emulador {serial} detenido.')


def stop_quiet(sdk: Sdk, serial: str) -> None:
    """Le pide al emulador que se apague, sin log y sin esperar.

    Es la version que se puede llamar desde el gancho de cancelacion
    (`TaskContext.on_cancel`): ahi la consola de la pestana quiza ya no exista
    y nadie puede quedarse esperando. `adb emu kill` vuelve enseguida; el
    emulador tarda un par de segundos en cerrarse solo, y en ese rato guarda su
    estado — que es justo lo que se pierde si en cambio se mata el proceso.
    """
    try:
        capture([sdk.adb, '-s', serial, 'emu', 'kill'], timeout=15, check=False)
    except TaskError:
        pass


def remove_avd(ctx, sdk: Sdk, name: str) -> None:
    ctx.run([sdk.tool('avdmanager'), 'delete', 'avd', '--name', name], check=False)


def remove_image(ctx, sdk: Sdk, image: str) -> None:
    ctx.run([sdk.tool('sdkmanager'), '--uninstall', image], check=False)
