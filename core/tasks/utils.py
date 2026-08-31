from __future__ import annotations
import getpass
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from .. import android, files, userenv
from ..catalog import ANDROID_DIR_DEFAULT, API_LEVEL_DEFAULT, BUILD_TOOLS_DEFAULT, FLUTTER_DIR_DEFAULT
from ..context import Level
from ..errors import TaskError
from ..process import as_argv, feed, format_argv, which_any
from ..registry import registry

"""
Grupo Utils.

Lo transversal: limpiar artefactos, actualizar el DNS, sincronizar los archivos
comunes entre repos e instalar los SDK. Todos los destructivos de este grupo
comparten el mismo patron: primero la lista exacta de lo que va a pasar, y recien
despues el borrado (PLAN.md 7, caso 5).
"""

# Familias de artefactos livianos: se recorren y se listan archivo por
# archivo. Cada clave es lo que entiende `find_artifacts(families=...)`;
# `ui/task_adapters.py` traduce las etiquetas del panel a estas claves.
FAMILIES: dict[str, dict[str, tuple[str, ...]]] = {
    'python': {'dirs': ('__pycache__',), 'suffixes': ('.pyc', '.pyo')},
    'gradle': {'dirs': ('.gradle', '.kotlin', '.cxx')},
    'flutter': {'files': ('.flutter-plugins', '.flutter-plugins-dependencies', '.packages')},
    'crash': {'files': ('CMakeOutput.log',), 'prefixes': ('hs_err_pid', 'replay_pid')},
}

# Carpetas pesadas: no se listan por dentro, se listan como una unidad y se
# borran enteras. Apagadas por defecto (PLAN.md 7, caso 5: lo caro se pide
# explicito). Varios nombres por clave porque node_modules no cambia, pero
# "venv" y "build" si.
HEAVY_DIRS: dict[str, tuple[str, ...]] = {
    'node_modules': ('node_modules',),
    'venv': ('.venv', 'venv'),
    'build': ('build', 'dist'),
    'dart_tool': ('.dart_tool',),
}

# Nunca se entra a estas, sin importar que se haya pedido: no son artefactos,
# son el propio control de versiones y la config de Consola.
ALWAYS_SKIP_DIRS = {'.git', '.consola'}

COMMON_PATHS = ('server/alembic/env.py', 'server/alembic/script.py.mako',
                'server/app/models/base.py', 'server/app/schemas/base.py',
                'server/alembic.ini', '.gitignore')

CF_API = 'https://api.cloudflare.com/client/v4'
IP_SERVICES = ('https://api.ipify.org', 'https://ifconfig.me/ip')


# --- limpieza --------------------------------------------------------------

def find_artifacts(ctx, families: list[str] | None = None,
                   heavy: list[str] | None = None) -> list[Path]:
    """Lista los artefactos borrables del repo, sin tocar nada.

    Atomica de solo lectura: es el simulacro que alimenta al boton destructivo,
    y sirve sola para saber cuanto espacio hay para recuperar.

    `families` filtra que tipos de cache liviana se listan (por defecto,
    todas: `FAMILIES`). `heavy` son carpetas pesadas (`node_modules`, `.venv`,
    `build`/`dist`, `.dart_tool`) que se listan enteras, no por dentro; por
    defecto ninguna, para no ofrecer un borrado caro sin que se pida.
    """
    active_families = set(FAMILIES) if families is None else set(families)
    active_heavy_dirnames = {name for key in (heavy or ()) for name in HEAVY_DIRS.get(key, ())}
    # Lo pesado que no se pidio sigue sin recorrerse: entrar a node_modules
    # o .venv solo para no listar nada de adentro seria trabajo tirado.
    skip_unrequested = {name for names in HEAVY_DIRS.values() for name in names} - active_heavy_dirnames

    encontrados: list[Path] = []
    for actual, subdirs, archivos in os.walk(ctx.root):
        base = Path(actual)
        keep_subdirs = []
        for nombre in subdirs:
            if nombre in ALWAYS_SKIP_DIRS or nombre in skip_unrequested:
                continue
            if nombre in active_heavy_dirnames:
                encontrados.append(base / nombre)
                continue  # se borra entera: no hace falta bajar a mirarla
            if (('gradle' in active_families and nombre in FAMILIES['gradle']['dirs'])
                    or ('python' in active_families and nombre in FAMILIES['python']['dirs'])):
                encontrados.append(base / nombre)
                continue
            keep_subdirs.append(nombre)
        subdirs[:] = keep_subdirs

        for nombre in archivos:
            if ('flutter' in active_families and nombre in FAMILIES['flutter']['files']):
                encontrados.append(base / nombre)
            elif ('crash' in active_families
                  and (nombre in FAMILIES['crash']['files']
                       or nombre.startswith(FAMILIES['crash']['prefixes']))):
                encontrados.append(base / nombre)
            elif ('python' in active_families and nombre.endswith(FAMILIES['python']['suffixes'])):
                encontrados.append(base / nombre)
    return encontrados


def clean_artifacts(ctx, apply: bool = False, families: list[str] | None = None,
                    heavy: list[str] | None = None) -> list[Path]:
    """Borra los artefactos listados. En simulacro solo los muestra."""
    encontrados = find_artifacts(ctx, families, heavy)
    if not encontrados:
        ctx.ok('No hay artefactos para limpiar.')
        return []

    total = sum(files.size_of(p) for p in encontrados)
    for ruta in encontrados[:40]:
        ctx.info(f'  {ruta.relative_to(ctx.root)}')
    if len(encontrados) > 40:
        ctx.info(f'  ... y {len(encontrados) - 40} mas')
    ctx.warn(f'{len(encontrados)} elemento(s), {files.human_size(total)}.')

    if not apply:
        ctx.info('Simulacro: no se borro nada.')
        return encontrados

    for ruta in encontrados:
        files.remove(ruta)
    ctx.ok(f'Liberados {files.human_size(total)}.')
    return encontrados


# --- sincronizacion entre repos --------------------------------------------

def compare_common_files(ctx, targets: list[str], paths: list[str] | None = None) -> list[tuple]:
    """Compara los archivos compartidos del repo actual contra los otros repos.

    Devuelve `(destino, ruta, estado)` con estado NEW / DIFF / SAME. Es lo que
    se muestra antes de habilitar Aplicar; `verify_projects.py` no era mas que
    esto, y por eso deja de ser una capacidad aparte (PLAN.md 1).
    """
    rutas = list(paths or COMMON_PATHS)
    resultado: list[tuple] = []
    for destino in targets:
        raiz = Path(destino)
        if not raiz.is_dir():
            ctx.warn(f'No existe el repo destino: {destino}')
            continue
        for rel in rutas:
            origen = ctx.path(rel)
            if not origen.exists():
                continue
            resultado.append((raiz, rel, files.compare(origen, raiz / rel)))
    return resultado


def sync_common_files(ctx, targets: list[str] | None = None,
                      paths: list[str] | None = None, apply: bool = False) -> list[tuple]:
    """Copia los archivos compartidos a los otros repos gestionados.

    Ya no incluye `scripts/`: esa carpeta deja de existir cuando Consola es la
    herramienta, y era la unica razon original de este script (PLAN.md 1).
    """
    if not targets:
        raise TaskError('No hay repos destino seleccionados.')

    diferencias = [fila for fila in compare_common_files(ctx, targets, paths) if fila[2] != 'SAME']
    if not diferencias:
        ctx.ok('Todos los repos destino ya estan al dia.')
        return []

    for raiz, rel, estado in diferencias:
        ctx.info(f'  [{estado}] {raiz.name}/{rel}')

    if not apply:
        ctx.info('Simulacro: no se copio nada.')
        return diferencias

    if not ctx.confirm(f'Sobrescribir {len(diferencias)} archivo(s) en {len(targets)} repo(s)?',
                       danger=True):
        ctx.warn('Cancelado: no se copio nada.')
        return []

    for raiz, rel, _ in diferencias:
        files.copy(ctx.path(rel), raiz / rel)
        ctx.ok(f'{raiz.name}/{rel}')
    return diferencias


# --- DNS -------------------------------------------------------------------

def detect_public_ip(ctx) -> str:
    """La IP publica de esta maquina, preguntandole a un servicio externo."""
    for servicio in IP_SERVICES:
        try:
            with urllib.request.urlopen(servicio, timeout=10) as respuesta:
                ip = respuesta.read().decode('utf-8').strip()
            if ip:
                ctx.info(f'IP publica detectada: {ip}')
                return ip
        except OSError:
            continue
    raise TaskError('No se pudo detectar la IP publica.')


def _cloudflare(ctx, method: str, path: str, body: dict | None = None) -> dict:
    token = ctx.config.require('CF_API_TOKEN')
    ctx.guard(token)
    datos = json.dumps(body).encode('utf-8') if body is not None else None
    peticion = urllib.request.Request(
        f'{CF_API}{path}', data=datos, method=method,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as respuesta:
            payload = json.loads(respuesta.read())
    except OSError as exc:
        raise TaskError(f'No se pudo hablar con Cloudflare: {exc}') from exc

    if not payload.get('success'):
        raise TaskError(f'Cloudflare rechazo la peticion: {payload.get("errors")}')
    return payload


def update_cloudflare(ctx, ip_mode: str = 'vps', custom_ip: str = '',
                      ttl: int = 1, proxied: bool = True) -> str:
    """Apunta el registro DNS a la IP elegida: detectada, la del VPS, o una fija."""
    if ip_mode == 'detect':
        ip = detect_public_ip(ctx)
    elif ip_mode == 'static':
        ip = custom_ip or ctx.config.require('VPS_IP')
    else:
        ip = ctx.config.require('VPS_IP')

    dominio = ctx.config.require('CF_DOMAIN_NAME')
    registro = ctx.config.require('CF_RECORD_NAME')

    zonas = _cloudflare(ctx, 'GET', f'/zones?name={dominio}')['result']
    if not zonas:
        raise TaskError(f'Cloudflare no conoce el dominio {dominio}.')
    zona = zonas[0]['id']

    registros = _cloudflare(ctx, 'GET', f'/zones/{zona}/dns_records?type=A&name={registro}')['result']
    if not registros:
        raise TaskError(f'No existe el registro A para {registro}.')

    actual = registros[0]
    if actual['content'] == ip:
        ctx.ok(f'{registro} ya apunta a {ip}. No hay nada que cambiar.')
        return ip

    _cloudflare(ctx, 'PUT', f'/zones/{zona}/dns_records/{actual["id"]}',
                {'type': 'A', 'name': registro, 'content': ip,
                 'ttl': ttl, 'proxied': proxied})
    ctx.ok(f'{registro}: {actual["content"]} -> {ip}')
    ctx.note(f'DNS {registro} apuntado a {ip}.')
    return ip


# --- SDKs: plomeria comun --------------------------------------------------

ANDROID_STUDIO_URL = 'https://developer.android.com/studio#command-line-tools-only'
ANDROID_REPO_URL = 'https://dl.google.com/android/repository/'
FLUTTER_RELEASES_URL = 'https://storage.googleapis.com/flutter_infra_release/releases/'
FLUTTER_RELEASES_JSON = {
    'windows': 'releases_windows.json',
    'linux': 'releases_linux.json',
    'mac': 'releases_macos.json',
}


def _os_key() -> str:
    if os.name == 'nt':
        return 'windows'
    return 'mac' if sys.platform == 'darwin' else 'linux'


def _script(name: str) -> str:
    """El nombre real del lanzador: los del SDK son `.bat` en Windows."""
    return f'{name}.bat' if os.name == 'nt' else name


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode('utf-8', errors='replace')
    except OSError as exc:
        raise TaskError(f'No se pudo consultar {url}: {exc}') from exc


def _download(ctx, url: str, destination: Path) -> Path:
    """Descarga informando el avance y atendiendo a Detener.

    El `urlretrieve` a secas de los scripts dejaba la interfaz muda durante los
    cientos de megas del SDK y no habia forma de frenarlo a mitad de camino.
    """
    ctx.info(f'Descargando {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)

    def avance(bloques: int, tamano: int, total: int) -> None:
        ctx.raise_if_cancelled()
        if total > 0:
            hecho = min(bloques * tamano, total)
            ctx.progress(hecho, total, f'{files.human_size(hecho)} de {files.human_size(total)}')

    try:
        urllib.request.urlretrieve(url, destination, avance)
    except OSError as exc:
        raise TaskError(f'Fallo la descarga: {exc}') from exc

    ctx.ok(f'Descargado: {files.human_size(files.size_of(destination))}')
    return destination


def _verify(ctx, archive: Path, expected: str, algorithm: str) -> None:
    """Comprueba la huella publicada. Un SDK a medio bajar falla mas tarde y peor."""
    actual = files.digest(archive, algorithm)
    if actual.lower() != expected.lower():
        raise TaskError(
            f'{algorithm.upper()} no coincide: el archivo llego incompleto o alterado.\n'
            f'  esperado: {expected}\n  obtenido: {actual}'
        )
    ctx.ok(f'{algorithm.upper()} verificado.')


# --- SDK de Android --------------------------------------------------------

ANDROID_COMPONENTS = ('platform-tools', 'emulator', 'build-tools', 'platform')

ANDROID_STEPS = ('install_android_tools', 'install_android_packages',
                 'install_android_hypervisor')


def _android_root(install_dir: str = '') -> Path:
    return Path(install_dir or ANDROID_DIR_DEFAULT).expanduser()


def _is_android_path(entry: str) -> bool:
    """Si una entrada del PATH pertenece a una instalacion anterior del SDK."""
    ruta = entry.strip().strip('"').replace('\\', '/').rstrip('/').lower()
    return ruta.endswith(('/platform-tools', '/emulator', '/cmdline-tools/latest/bin'))


def _ensure_java(ctx) -> None:
    if which_any(['java', 'java.exe']):
        return
    raise TaskError(
        'No se encontro Java en el PATH y sdkmanager no corre sin el. '
        'Instala un JDK 17 o superior (en Debian/Ubuntu: apt install openjdk-17-jdk).'
    )


def _resolve_cmdline_tools(ctx, os_key: str) -> tuple[str, str]:
    """URL y SHA-1 de las cmdline-tools, leidos de la pagina oficial.

    No se guarda la URL como constante a proposito: Google le cambia el numero
    de build a cada version y una constante vieja falla con un 404 que no
    explica nada.
    """
    html = _fetch_text(ANDROID_STUDIO_URL)
    patron = rf'commandlinetools-{"win" if os_key == "windows" else os_key}-\d+_latest\.zip'

    nombres = list(dict.fromkeys(re.findall(patron, html)))
    if len(nombres) != 1:
        raise TaskError(
            'No se pudo identificar el zip de cmdline-tools en la pagina de Android Studio '
            f'({len(nombres)} coincidencias para {os_key}). Puede que Google haya cambiado la pagina.'
        )

    nombre = nombres[0]
    huella = re.search(re.escape(nombre) + r'[\s\S]{0,300}?([0-9a-f]{40})', html, re.IGNORECASE)
    if not huella:
        raise TaskError(f'La pagina de Android Studio no publica el SHA-1 de {nombre}.')

    ctx.info(f'Version publicada: {nombre}')
    return ANDROID_REPO_URL + nombre, huella.group(1).lower()


def _extract_cmdline_tools(ctx, archive: Path, latest: Path) -> None:
    ctx.info(f'Descomprimiendo en {latest}')
    files.extract_zip(archive, latest)

    # El zip trae todo colgando de `cmdline-tools/`, pero sdkmanager deduce el
    # sdk_root desde su propia ruta y exige quedar en `cmdline-tools/latest/bin`.
    interior = latest / 'cmdline-tools'
    if interior.is_dir():
        for item in interior.iterdir():
            item.rename(latest / item.name)
        interior.rmdir()


def install_android_tools(ctx, install_dir: str = '') -> Path:
    """Deja las command-line tools del SDK de Android instaladas y en el entorno.

    Atomica: resuelve la version publicada, la verifica, la descomprime y
    escribe ANDROID_SDK_ROOT / ANDROID_HOME / ANDROID_AVD_HOME y el PATH del
    usuario. No instala paquetes: de eso se ocupa `install_android_packages`,
    que se corre solo cada vez que hace falta otra API o otro build-tools.
    """
    os_key = _os_key()
    if os_key not in ('windows', 'linux'):
        raise TaskError(f'Google no publica cmdline-tools para este sistema: {os_key}.')
    _ensure_java(ctx)

    root = _android_root(install_dir)
    latest = root / 'cmdline-tools' / 'latest'
    sdkmanager = latest / 'bin' / _script('sdkmanager')

    if sdkmanager.is_file():
        ctx.ok(f'Las cmdline-tools ya estaban en {latest}.')
    else:
        url, sha1 = _resolve_cmdline_tools(ctx, os_key)
        with tempfile.TemporaryDirectory(prefix='consola_cmdline_tools_') as temporal:
            archive = _download(ctx, url, Path(temporal) / 'cmdline-tools.zip')
            _verify(ctx, archive, sha1, 'sha1')
            _extract_cmdline_tools(ctx, archive, latest)
        if not sdkmanager.is_file():
            raise TaskError(f'No aparecio sdkmanager despues de descomprimir: {sdkmanager}')
        ctx.ok(f'cmdline-tools instaladas en {latest}.')

    avd = root / 'avd'
    avd.mkdir(parents=True, exist_ok=True)
    userenv.configure(
        ctx,
        variables={'ANDROID_SDK_ROOT': str(root), 'ANDROID_HOME': str(root),
                   'ANDROID_AVD_HOME': str(avd)},
        path_add=[root / 'platform-tools', root / 'emulator', latest / 'bin'],
        path_drop=_is_android_path,
    )
    return root


def _sdkmanager(ctx) -> tuple[list[str], Path]:
    """El sdkmanager instalado y la raiz del SDK a la que pertenece.

    Se resuelve por `core/android.py`, que ya explica que hacer cuando falta;
    asi la dependencia entre las dos atomicas no las acopla: si todavia no se
    instalaron las herramientas, el error lo dice con esas palabras.
    """
    sdk = android.resolve_sdk()
    ruta = sdk.tool('sdkmanager')
    root = sdk.root or Path(ruta).resolve().parents[3]
    return as_argv(ruta), root


def _accept_licenses(ctx, sdkmanager: list[str], root: Path) -> None:
    ctx.info('Aceptando las licencias del SDK...')
    argv = [*sdkmanager, f'--sdk_root={root}', '--licenses']
    ctx.log(format_argv(argv), Level.CMD)
    salida = feed(argv, stdin_text='y\n' * 200, timeout=300)
    for linea in salida.splitlines():
        if linea.strip():
            ctx.info(linea.strip())
    ctx.ok('Licencias aceptadas.')


def _installed_packages(ctx, sdkmanager: list[str], root: Path) -> set[str]:
    salida = ctx.capture([*sdkmanager, f'--sdk_root={root}', '--list_installed'],
                         timeout=300, check=False)
    return {linea.split('|', 1)[0].strip() for linea in salida.splitlines() if '|' in linea}


def install_android_packages(ctx, components: list[str] | None = None,
                             api_level: str = '', build_tools: str = '') -> list[str]:
    """Instala en el SDK ya presente los paquetes que falten.

    Es atomica aparte de la instalacion de las herramientas porque es la que se
    repite: cuando sale una API nueva o un repo pide otro build-tools se agrega
    ese paquete sin volver a bajar el SDK entero ni tocar el PATH. En los
    scripts esto obligaba a editar dos constantes y correr todo de nuevo.
    """
    elegidos = list(ANDROID_COMPONENTS if components is None else components)
    if not elegidos:
        raise TaskError('No se eligio ningun componente para instalar.')

    api = (api_level or API_LEVEL_DEFAULT).strip()
    tools = (build_tools or BUILD_TOOLS_DEFAULT).strip()
    paquetes = []
    for nombre in elegidos:
        if nombre == 'build-tools':
            paquetes.append(f'build-tools;{tools}')
        elif nombre == 'platform':
            paquetes.append(f'platforms;android-{api}')
        else:
            paquetes.append(nombre)

    sdkmanager, root = _sdkmanager(ctx)
    _accept_licenses(ctx, sdkmanager, root)

    instalados = _installed_packages(ctx, sdkmanager, root)
    faltan = [p for p in paquetes if p not in instalados]
    if not faltan:
        ctx.ok(f'Los {len(paquetes)} paquete(s) pedidos ya estaban instalados.')
        return []

    for paquete in faltan:
        ctx.info(f'  falta: {paquete}')
    ctx.run([*sdkmanager, f'--sdk_root={root}', *faltan])
    ctx.ok(f'{len(faltan)} paquete(s) instalados.')
    return faltan


def install_android_hypervisor(ctx) -> bool:
    """Deja lista la aceleracion por hardware del emulador.

    Va aparte por dos razones. Es lo unico de toda la instalacion que necesita
    permisos elevados (en Windows es un driver de kernel; en Linux, pertenecer
    al grupo kvm), asi que separandolo las otras dos atomicas no piden ninguno.
    Y es lo que se rompe solo: una actualizacion del sistema deja el emulador
    lentisimo sin que el resto del SDK haya cambiado.
    """
    if os.name != 'nt':
        return _check_kvm(ctx)

    try:
        ctx.capture(['sc', 'query', 'gvm'], timeout=30)
        ctx.ok('El Hypervisor Driver ya esta instalado (servicio gvm).')
        return True
    except TaskError:
        pass

    sdkmanager, root = _sdkmanager(ctx)
    ctx.info('Descargando el Google Android Emulator Hypervisor Driver...')
    ctx.run([*sdkmanager, f'--sdk_root={root}',
             'extras;google;Android_Emulator_Hypervisor_Driver'])

    instalador = root / 'extras' / 'google' / 'Android_Emulator_Hypervisor_Driver' / 'silent_install.bat'
    if not instalador.is_file():
        raise TaskError(f'No aparecio el instalador del driver: {instalador}')

    ctx.warn('El driver necesita permisos de administrador: acepta el aviso de Windows.')
    _run_elevated(ctx, instalador)
    return True


def _check_kvm(ctx) -> bool:
    """En Linux la aceleracion no se instala: se verifica y, si falta, se explica.

    Meter la mano con sudo desde una interfaz grafica seria peor que decir el
    comando exacto: el cambio de grupo ademas no surte efecto hasta reingresar.
    """
    dispositivo = Path('/dev/kvm')
    if not dispositivo.exists():
        raise TaskError(
            'No existe /dev/kvm: sin el, el emulador corre por software y es inusable.\n'
            'Revisa que la virtualizacion (VT-x o AMD-V) este activa en la BIOS y que el '
            'modulo kvm_intel o kvm_amd este cargado.'
        )
    if os.access(dispositivo, os.R_OK | os.W_OK):
        ctx.ok('/dev/kvm accesible: la aceleracion por hardware esta disponible.')
        return True

    usuario = os.environ.get('USER') or getpass.getuser()
    ctx.warn('/dev/kvm existe pero este usuario no tiene permiso para usarlo.')
    ctx.warn(f'Corre:  sudo usermod -aG kvm {usuario}')
    ctx.warn('Y vuelve a iniciar sesion para que el grupo tome efecto.')
    return False


def _run_elevated(ctx, program: Path) -> None:
    """Lanza un programa pidiendo elevacion: un solo aviso de UAC.

    Es preferible a exigir que Consola entera corra como administrador, que es
    lo que hacia falta con los scripts: todo lo demas escribe en HKCU y no
    necesita permisos.
    """
    import ctypes
    ctx.log(str(program), Level.CMD)
    codigo = ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', str(program), None, str(program.parent), 1)
    if codigo <= 32:
        raise TaskError(
            f'No se pudo lanzar el instalador con permisos de administrador (codigo {codigo}). '
            'Si rechazaste el aviso de Windows, vuelve a intentarlo.'
        )
    ctx.info('El instalador quedo corriendo en una ventana aparte; espera a que termine.')


def install_android_sdk(ctx, install_dir: str = '', components: list[str] | None = None,
                        api_level: str = '', build_tools: str = '',
                        steps: list[str] | None = None) -> Path:
    """Instalacion completa del SDK de Android, de punta a punta.

    Compuesta: encadena las tres atomicas en el unico orden que funciona, y
    cada una sigue estando disponible sola desde su propio boton.
    """
    activos = set(ANDROID_STEPS if steps is None else steps)
    root = _android_root(install_dir)

    if 'install_android_tools' in activos:
        ctx.step('Herramientas de linea de comandos')
        root = install_android_tools(ctx.child('install_android_tools'), install_dir)

    if 'install_android_packages' in activos:
        ctx.step('Paquetes del SDK')
        install_android_packages(ctx.child('install_android_packages'),
                                 components, api_level, build_tools)

    if 'install_android_hypervisor' in activos:
        ctx.step('Aceleracion del emulador')
        install_android_hypervisor(ctx.child('install_android_hypervisor'))

    ctx.ok(f'SDK de Android listo en {root}.')
    return root


# --- SDK de Flutter --------------------------------------------------------

def _is_flutter_path(entry: str) -> bool:
    """Si una entrada del PATH es el `bin` de una instalacion anterior de Flutter.

    Mira el directorio padre y no solo el nombre exacto, para reconocer tambien
    las instalaciones en un directorio propio (`~/sdk/flutter-stable/bin`).
    """
    partes = entry.strip().strip('"').replace('\\', '/').rstrip('/').lower().split('/')
    return len(partes) >= 2 and partes[-1] == 'bin' and 'flutter' in partes[-2]


def _ensure_git(ctx) -> None:
    if which_any(['git', 'git.exe']):
        return
    raise TaskError('No se encontro Git en el PATH, y Flutter lo necesita para actualizarse.')


def _resolve_flutter_stable(ctx, os_key: str) -> tuple[str, str]:
    """URL y SHA-256 del canal stable, desde el indice oficial de releases."""
    nombre = FLUTTER_RELEASES_JSON.get(os_key)
    if not nombre:
        raise TaskError(f'Flutter no publica releases para este sistema: {os_key}.')

    try:
        datos = json.loads(_fetch_text(FLUTTER_RELEASES_URL + nombre))
    except ValueError as exc:
        raise TaskError('El indice de releases de Flutter no vino en JSON valido.') from exc

    marca = ((datos.get('current_release') or {}).get('stable') or '').strip()
    release = next((r for r in (datos.get('releases') or [])
                    if (r.get('hash') or '').strip() == marca), None)
    if not release:
        raise TaskError('El indice de Flutter no identifica el release del canal stable.')

    archivo = (release.get('archive') or '').strip()
    huella = (release.get('sha256') or '').strip().lower()
    if not archivo or not huella:
        raise TaskError('El release stable de Flutter no publica archivo o SHA-256.')

    ctx.info(f'Version publicada: {release.get("version") or marca}')
    return FLUTTER_RELEASES_URL + archivo, huella


def _extract_flutter(ctx, archive: Path, home: Path) -> None:
    """Descomprime el SDK, que trae su propia carpeta `flutter/` en la raiz."""
    destino = home.parent
    ctx.info(f'Descomprimiendo en {home}')
    destino.mkdir(parents=True, exist_ok=True)
    files.extract(archive, destino)

    extraido = destino / 'flutter'
    if extraido != home:
        if home.exists():
            raise TaskError(f'Ya existe {home}: muevelo o elige otro directorio.')
        extraido.rename(home)


def install_flutter_sdk(ctx, install_dir: str = '') -> Path:
    """Instala el SDK de Flutter del canal stable y lo deja en el entorno.

    Sigue siendo una sola atomica, a diferencia de Android: Flutter no tiene
    paquetes sueltos que se agreguen despues, se actualiza entero con
    `flutter upgrade`.
    """
    os_key = _os_key()
    _ensure_git(ctx)

    home = Path(install_dir or FLUTTER_DIR_DEFAULT).expanduser()
    flutter = home / 'bin' / _script('flutter')

    if flutter.is_file():
        ctx.ok(f'Flutter ya estaba instalado en {home}.')
    else:
        url, sha256 = _resolve_flutter_stable(ctx, os_key)
        with tempfile.TemporaryDirectory(prefix='consola_flutter_') as temporal:
            archive = _download(ctx, url, Path(temporal) / Path(url).name)
            _verify(ctx, archive, sha256, 'sha256')
            _extract_flutter(ctx, archive, home)
        if not flutter.is_file():
            raise TaskError(f'No aparecio flutter despues de descomprimir: {flutter}')
        ctx.ok(f'Flutter instalado en {home}.')

    userenv.configure(ctx, variables={'FLUTTER_HOME': str(home)},
                      path_add=[home / 'bin'], path_drop=_is_flutter_path)

    ctx.info('Verificando la instalacion...')
    ctx.run([*as_argv(str(flutter)), '--version'], check=False)
    ctx.info('flutter doctor: los avisos que siguen no son errores de la instalacion.')
    ctx.run([*as_argv(str(flutter)), 'doctor'], check=False)
    return home


def bind_all() -> None:
    registry.bind('clean_artifacts', clean_artifacts)
    registry.bind('update_cloudflare', update_cloudflare)
    registry.bind('sync_common_files', sync_common_files)
    registry.bind('install_android_tools', install_android_tools)
    registry.bind('install_android_packages', install_android_packages)
    registry.bind('install_android_hypervisor', install_android_hypervisor)
    registry.bind('install_android_sdk', install_android_sdk)
    registry.bind('install_flutter_sdk', install_flutter_sdk)
