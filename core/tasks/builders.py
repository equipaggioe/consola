from __future__ import annotations
import platform
from pathlib import Path

from .. import files, ssh, targets, toolchain, versioning, vps
from ..errors import TaskError
from ..process import resolve_executable
from ..registry import registry

"""
Grupo Builders.

Los tres builders eran el mismo esqueleto repetido tres veces: subir la version
del manifiesto, correr la herramienta que compila, y opcionalmente subir el
artefacto al VPS. Cada uno traia su propia copia del bump (uno para
`pubspec.yaml`, otro para `package.json`, otro para `pyproject.toml`) y su
propia copia del scp.

Aca el bump es una sola atomica que sirve para los tres manifiestos, la subida
es otra, y lo unico propio de cada builder es el paso de compilacion.
"""


def _target(ctx, kind: str, name: str = '') -> targets.Target:
    return targets.find(ctx.root, kind, name) if name else targets.only(ctx.root, kind)


# --- atomicas transversales ------------------------------------------------

def bump_version(ctx, directory: str = '', mode: str = 'patch') -> tuple[str, str]:
    """Sube la version del manifiesto del subproyecto. Sirve para los tres tipos.

    Tiene boton propio porque incrementar la version sin compilar todavia es una
    operacion real: se hace al cerrar un cambio, antes de decidir si se publica.
    """
    carpeta = ctx.path(directory) if directory else ctx.root
    manifiesto = versioning.find_manifest(carpeta)
    anterior = versioning.read_version(manifiesto)
    nueva = versioning.bump(anterior, mode)
    versioning.write_version(manifiesto, nueva)
    ctx.ok(f'{manifiesto.name}: {anterior} -> {nueva}')
    return anterior, nueva


def upload_artifact(ctx, local: Path, remote_rel: str = '') -> str:
    """Sube un artefacto al VPS respetando su ruta relativa dentro del repo.

    Boton propio: re-subir un APK ya compilado despues de un corte de red no
    deberia obligar a recompilarlo.
    """
    if not local.exists():
        raise TaskError(f'No existe el artefacto: {local}')
    rel = remote_rel or local.relative_to(ctx.root).as_posix()
    remote = ssh.resolve_remote(ctx.config)
    destino = ssh.upload(ctx, remote, local, vps.remote_path(ctx.config, rel))
    ctx.ok(f'Subido: {destino}')
    return destino


# --- pasos de Flutter / Flet -----------------------------------------------

def fetch_dependencies(ctx, directory: str = '') -> None:
    """`flutter pub get`. Se separa porque a veces solo hace falta esto: tras un
    cambio de rama, resolver dependencias sin compilar nada."""
    app = _target(ctx, targets.FLUTTER_APP, directory)
    ctx.run([*toolchain.flutter_cmd(), 'pub', 'get'], cwd=app.path)


def compile_apk(ctx, directory: str = '') -> Path:
    """Compila el APK de release. Es el unico paso que cambia entre Flutter y Flet.

    La URL de la API se inyecta por `--dart-define` desde la configuracion: es
    la misma fuente que usa el launcher de debug, para que release y debug no
    apunten a servidores distintos por descuido.
    """
    app = _target(ctx, targets.FLUTTER_APP, directory)
    kind = toolchain.detect_app_kind(app.path)
    api = ctx.config.get('API_URL')

    if kind == toolchain.FLUTTER:
        ctx.run([*toolchain.flutter_cmd(), 'build', 'apk', '--release',
                 f'--dart-define=API_BASE_URL={api}'], cwd=app.path)
        apk = app.path / 'build' / 'app' / 'outputs' / 'flutter-apk' / 'app-release.apk'
    else:
        ctx.run([*toolchain.flet_cmd(), 'build', 'apk'], cwd=app.path,
                env={'API_BASE_URL': api} if api else None)
        apk = _find_flet_apk(app.path)

    if not apk.is_file():
        raise TaskError(f'El build termino pero no aparecio el APK en {apk}.')
    ctx.ok(f'APK: {apk} ({files.human_size(files.size_of(apk))})')
    return apk


def _find_flet_apk(app_dir: Path) -> Path:
    encontrados = sorted((app_dir / 'build').rglob('*.apk'))
    if not encontrados:
        raise TaskError(f'No se encontro ningun .apk bajo {app_dir / "build"}.')
    return encontrados[-1]


# --- pasos de Vite ---------------------------------------------------------

def install_node_modules(ctx, directory: str = '') -> None:
    """`npm install`, no `npm ci`: `ci` borra `node_modules` entero y vuelve a
    compilar los binarios nativos, lo que multiplica el tiempo de build."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.npm_cmd(), 'install'], cwd=spa.path)


def compile_spa(ctx, directory: str = '') -> Path:
    """`npm run build`. Devuelve la carpeta de salida que declara Vite."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.npm_cmd(), 'run', 'build'], cwd=spa.path)

    for candidata in ('dist', 'build'):
        salida = spa.path / candidata
        if salida.is_dir():
            ctx.ok(f'Build de {spa.name}: {salida}')
            return salida
    raise TaskError(f'El build de {spa.name} no dejo carpeta dist/ ni build/.')


# --- pasos de binario ------------------------------------------------------

def compile_binary(ctx, entrypoint: str = '', name: str = '', onefile: bool = True) -> Path:
    """Empaqueta un ejecutable con PyInstaller.

    PyInstaller no compila para otro sistema operativo: el binario que sale es
    para el sistema donde corre Consola, y por eso el nombre lleva la etiqueta.
    """
    if not entrypoint:
        raise TaskError('Falta el archivo de entrada del binario.')
    fuente = ctx.path(entrypoint)
    if not fuente.is_file():
        raise TaskError(f'No existe el punto de entrada: {fuente}')

    app_name = name or fuente.stem
    etiqueta = f'{app_name}-{platform.system().lower()}-{platform.machine().lower()}'
    pyinstaller = resolve_executable(['pyinstaller', 'pyinstaller.exe'], label='PyInstaller')

    ctx.run([*pyinstaller, *(['--onefile'] if onefile else []), '--noconfirm',
             '--name', etiqueta, str(fuente)], cwd=ctx.root)

    sufijo = '.exe' if platform.system() == 'Windows' else ''
    artefacto = ctx.root / 'dist' / f'{etiqueta}{sufijo}'
    if not artefacto.exists():
        raise TaskError(f'PyInstaller no dejo el binario esperado en {artefacto}.')
    ctx.ok(f'Binario: {artefacto} ({files.human_size(files.size_of(artefacto))})')
    return artefacto


# --- promocion -------------------------------------------------------------

def promote_app(ctx, source: str = 'app_web_ultima', target: str = 'app_web_estable') -> None:
    """Copia la version recien publicada sobre la estable. Destructivo: pisa
    la carpeta anterior entera, asi que muestra el cambio antes de aplicar."""
    origen, destino = ctx.path(source), ctx.path(target)
    if not origen.is_dir():
        raise TaskError(f'No existe la carpeta de origen: {origen}')

    estado = files.compare(origen, destino)
    if estado == 'SAME':
        ctx.ok('La version estable ya es identica a la ultima. No hay nada que promover.')
        return

    ctx.warn(f'{destino} va a ser reemplazada por {origen} ({estado}).')
    if not ctx.confirm(f'Escribe {destino.name} para promover.', danger=True, expect=destino.name):
        ctx.warn('Cancelado: no se promovio nada.')
        return

    files.remove(destino)
    files.copy(origen, destino)
    ctx.ok(f'Promovido: {origen.name} -> {destino.name}')
    ctx.note(f'Promocion de app: {origen.name} -> {destino.name}')


# --- compuestas ------------------------------------------------------------

def build_apk(
    ctx,
    directory: str = '',
    bump_mode: str = 'patch',
    *,
    bump: bool = True,
    build: bool = True,
    upload: bool = False,
) -> Path | None:
    """Compuesta: bump -> pub get -> build -> subida opcional.

    Si el build falla, la version vuelve a lo que era: el repo no queda marcado
    con un numero que nunca se publico.
    """
    app = _target(ctx, targets.FLUTTER_APP, directory)
    manifiesto = versioning.find_manifest(app.path)

    with files.reversible(manifiesto):
        if bump:
            ctx.step('Version')
            bump_version(ctx, app.name, bump_mode)
        if not build:
            return None
        ctx.step('Dependencias')
        fetch_dependencies(ctx, app.name)
        ctx.step('Compilacion')
        apk = compile_apk(ctx, app.name)

    if upload:
        ctx.step('Subida al VPS')
        upload_artifact(ctx, apk)

    ctx.note(f'Build APK {app.name} {versioning.read_version(manifiesto)}')
    return apk


def build_vite(
    ctx,
    directory: str = '',
    bump_mode: str = 'patch',
    *,
    bump: bool = True,
    build: bool = True,
    upload: bool = False,
) -> Path | None:
    """Compuesta: npm install -> bump -> npm run build -> subida opcional."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    manifiesto = versioning.find_manifest(spa.path)

    with files.reversible(manifiesto):
        ctx.step('Dependencias')
        install_node_modules(ctx, spa.name)
        if bump:
            ctx.step('Version')
            bump_version(ctx, spa.name, bump_mode)
        if not build:
            return None
        ctx.step('Compilacion')
        salida = compile_spa(ctx, spa.name)

    if upload:
        ctx.step('Subida al VPS')
        upload_artifact(ctx, salida)

    ctx.note(f'Build Vite {spa.name} {versioning.read_version(manifiesto)}')
    return salida


def build_binary(
    ctx,
    entrypoint: str = '',
    name: str = '',
    bump_mode: str = 'patch',
    *,
    bump: bool = True,
    build: bool = True,
    upload: bool = False,
) -> Path | None:
    """Compuesta: bump de `pyproject.toml` -> PyInstaller -> subida opcional."""
    manifiesto = versioning.find_manifest(ctx.root)

    with files.reversible(manifiesto):
        if bump:
            ctx.step('Version')
            bump_version(ctx, '', bump_mode)
        if not build:
            return None
        ctx.step('Empaquetado')
        artefacto = compile_binary(ctx, entrypoint, name)

    if upload:
        ctx.step('Subida al VPS')
        upload_artifact(ctx, artefacto)

    ctx.note(f'Build binario {artefacto.name}')
    return artefacto


def bind_all() -> None:
    registry.bind('build_apk', build_apk)
    registry.bind('build_vite', build_vite)
    registry.bind('build_binary', build_binary)
    registry.bind('promote_app', promote_app)
    registry.bind('bump_version', bump_version)
    registry.bind('upload_to_vps', upload_artifact)
