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
    return targets.pick(ctx.root, (kind,), name)


def _mobile(ctx, name: str = '') -> targets.Target:
    """La app movil del repo, sea Flutter o Flet.

    Los dos tipos se buscan juntos porque el framework no es una eleccion de
    quien aprieta el boton: es una propiedad de la carpeta, y `compile_apk` la
    lee sola. Pedir "Flutter o Flet" seria pedir que confirme lo que el repo ya
    contesta — y en un repo solo-Flet, exigir `flutter-app` fallaba antes de
    llegar siquiera a la bifurcacion que ya existia.
    """
    return targets.pick(ctx.root, targets.MOBILE_APP, name)


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

def compile_apk(ctx, directory: str = '') -> Path:
    """Compila el APK de release. Es el unico paso que cambia entre Flutter y Flet.

    La URL de la API se inyecta por `--dart-define` desde la configuracion: es
    la misma fuente que usa el launcher de debug, para que release y debug no
    apunten a servidores distintos por descuido.
    """
    app = _mobile(ctx, directory)
    kind = toolchain.detect_app_kind(app.path)
    api = ctx.config.require('API_URL')

    if kind == toolchain.FLUTTER:
        ctx.run([*toolchain.flutter_cmd(), 'build', 'apk', '--release',
                 f'--dart-define=API_BASE_URL={api}'], cwd=app.path)
        apk = _release_apk(app.path)
    else:
        # `flet build` delega en el mismo `flutter build` de abajo, asi que el
        # `--dart-define` llega igual; la variable de entorno queda ademas para
        # el codigo Python que la lea al empaquetar. Sin verificar contra un
        # repo Flet real: es el unico paso de este flujo que sigue a ciegas.
        ctx.run([*toolchain.flet_cmd(), 'build', 'apk',
                 f'--dart-define=API_BASE_URL={api}'], cwd=app.path,
                env={'API_BASE_URL': api})
        apk = _find_flet_apk(app.path)

    if not apk.is_file():
        raise TaskError(f'El build termino pero no aparecio el APK en {apk}.')
    ctx.ok(f'APK: {apk} ({files.human_size(files.size_of(apk))})')
    return apk


def _release_apk(app_dir: Path) -> Path:
    return app_dir / 'build' / 'app' / 'outputs' / 'flutter-apk' / 'app-release.apk'


def _find_flet_apk(app_dir: Path) -> Path:
    encontrados = sorted((app_dir / 'build').rglob('*.apk'))
    if not encontrados:
        raise TaskError(f'No se encontro ningun .apk bajo {app_dir / "build"}.')
    return encontrados[-1]


def _last_apk(app_dir: Path) -> Path:
    """El APK que ya esta en disco, sin volver a compilarlo.

    No mira el framework: si esta la salida de Flutter la usa, y si no busca la
    de Flet. Lo que importa aca es que exista un binario, no quien lo genero.
    """
    release = _release_apk(app_dir)
    return release if release.is_file() else _find_flet_apk(app_dir)


def _publish(ctx, apk: Path, manifest: Path) -> None:
    """Sube el APK junto con su manifiesto de version.

    Van los dos o no va ninguno: el APK no dice de que version es, y del lado
    del VPS el manifiesto es lo unico que lo identifica. Subir solo el binario
    deja al servidor anunciando la version anterior.
    """
    upload_artifact(ctx, apk)
    upload_artifact(ctx, manifest)


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
    """Compuesta: bump -> compilar -> subir APK + manifiesto.

    Un solo boton para Flutter y para Flet. `directory` nombra *cual* app del
    repo, no con que esta escrita: el framework sale de la carpeta. Lo unico
    que no se comparte es `bump_mode='build_only'`, que necesita el `+N` de
    `pubspec.yaml` y falla con ese mensaje en un `pyproject.toml`.

    Sin `build` no se compila nada: se sube el APK que ya esta en disco. Es el
    modo que el script original activaba con `BUILD_APK=false`, y el motivo de
    que 'Compilar APK' sea un paso desmarcable y no una casilla fija.

    No hay paso de `pub get`: `flutter build apk` resuelve dependencias solo, y
    el bump acaba de tocar `pubspec.yaml`, asi que las re-resuelve siempre.
    (`build_vite` si conserva el suyo, porque `npm run build` no instala nada.)

    Si el build falla, la version vuelve a lo que era: el repo no queda marcado
    con un numero que nunca se publico.
    """
    app = _mobile(ctx, directory)
    manifiesto = versioning.find_manifest(app.path)

    if not build:
        if not upload:
            raise TaskError('Sin compilar y sin subir no queda nada por hacer.')
        if bump:
            ctx.warn('Bump ignorado: el APK que hay en disco se compilo con la '
                     'version que ya tiene el manifiesto, y subirla cambiada lo '
                     'anunciaria como otra cosa.')
        apk = _last_apk(app.path)
        ctx.step('Subida al VPS')
        _publish(ctx, apk, manifiesto)
        ctx.note(f'Re-subida APK {app.name} {versioning.read_version(manifiesto)}')
        return apk

    with files.reversible(manifiesto):
        if bump:
            ctx.step('Version')
            bump_version(ctx, app.name, bump_mode)
        ctx.step('Compilacion')
        apk = compile_apk(ctx, app.name)

    if upload:
        ctx.step('Subida al VPS')
        _publish(ctx, apk, manifiesto)

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
