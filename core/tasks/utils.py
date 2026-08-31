from __future__ import annotations
import json
import os
import urllib.request
import zipfile
from pathlib import Path

from .. import files
from ..errors import TaskError
from ..process import capture, which_any
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


# --- SDKs ------------------------------------------------------------------

def _download(ctx, url: str, destination: Path) -> Path:
    ctx.info(f'Descargando {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, destination)
    except OSError as exc:
        raise TaskError(f'Fallo la descarga: {exc}') from exc
    ctx.ok(f'Descargado: {files.human_size(files.size_of(destination))}')
    return destination


def _extract(ctx, archive: Path, target: Path) -> Path:
    ctx.info(f'Extrayendo en {target}')
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target)
    return target


def install_android_sdk(ctx, url: str = '', sdk_root: str = '') -> Path:
    """Instala las command-line tools del SDK de Android y acepta las licencias.

    No adivina la URL: las de Google cambian con cada version y una constante
    vieja hace que el script falle sin decir por que. Se pide explicita.
    """
    if not url:
        raise TaskError(
            'Falta la URL del paquete cmdline-tools. Copiala de '
            'https://developer.android.com/studio#command-line-tools-only'
        )
    raiz = Path(sdk_root) if sdk_root else Path.home() / 'Android' / 'Sdk'
    zip_path = raiz / 'cmdline-tools.zip'

    _download(ctx, url, zip_path)
    _extract(ctx, zip_path, raiz / 'cmdline-tools')
    files.remove(zip_path)

    ctx.ok(f'SDK instalado en {raiz}')
    ctx.warn(f'Define ANDROID_SDK_ROOT={raiz} para que Consola lo encuentre.')
    return raiz


def install_flutter_sdk(ctx, url: str = '', install_dir: str = '') -> Path:
    """Descarga y descomprime el SDK de Flutter."""
    if not url:
        raise TaskError(
            'Falta la URL del SDK de Flutter. Copiala de '
            'https://docs.flutter.dev/get-started/install'
        )
    destino = Path(install_dir) if install_dir else Path.home() / 'flutter-sdk'
    zip_path = destino / 'flutter.zip'

    _download(ctx, url, zip_path)
    _extract(ctx, zip_path, destino)
    files.remove(zip_path)

    binario = which_any(['flutter', 'flutter.bat'])
    if binario:
        ctx.info(capture([binario, '--version'], timeout=180, check=False))
    ctx.ok(f'Flutter instalado en {destino}')
    ctx.warn(f'Agrega {destino / "flutter" / "bin"} al PATH.')
    return destino


def bind_all() -> None:
    registry.bind('clean_artifacts', clean_artifacts)
    registry.bind('update_cloudflare', update_cloudflare)
    registry.bind('sync_common_files', sync_common_files)
    registry.bind('install_android_sdk', install_android_sdk)
    registry.bind('install_flutter_sdk', install_flutter_sdk)
