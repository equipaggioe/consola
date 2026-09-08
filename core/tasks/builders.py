from __future__ import annotations
import platform
import re
from collections.abc import Sequence
from pathlib import Path

from .. import files, ssh, targets, toolchain, versioning, vps
from ..errors import TaskError
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


def upload_artifact(ctx, local: Path, remote_rel: str = '', *, chmod: str = '') -> str:
    """Sube un artefacto al VPS respetando su ruta relativa dentro del repo.

    Boton propio: re-subir un APK ya compilado despues de un corte de red no
    deberia obligar a recompilarlo.

    `chmod` es para lo que del otro lado se ejecuta: `scp` no conserva el bit de
    ejecucion, asi que un binario subido sin esto llega inservible. Los demas
    artefactos (un APK, una carpeta de SPA) se sirven, no se ejecutan, y no lo
    necesitan.
    """
    if not local.exists():
        raise TaskError(f'No existe el artefacto: {local}')
    rel = remote_rel or local.relative_to(ctx.root).as_posix()
    remote = ssh.resolve_remote(ctx.config)
    destino = ssh.upload(ctx, remote, local, vps.remote_path(ctx.config, rel), chmod=chmod)
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
    salida = _spa_output(spa)
    ctx.ok(f'Build de {spa.name}: {salida} ({files.human_size(files.size_of(salida))})')
    return salida


def _spa_output(spa: targets.Target) -> Path:
    """La carpeta que dejo el build: `dist/` en Vite pelado, `build/` en los
    adaptadores de SvelteKit. Se mira el disco y no `vite.config.*` porque la
    salida puede venir declarada desde un plugin.

    Es el homologo de `_last_apk`: sirve para leer lo recien compilado y
    tambien para encontrar lo que ya estaba, cuando se sube sin recompilar.
    """
    for candidata in ('dist', 'build'):
        salida = spa.path / candidata
        if salida.is_dir():
            return salida
    raise TaskError(f'{spa.name} no tiene carpeta dist/ ni build/.')


def _publish_spa(ctx, salida: Path, manifest: Path) -> None:
    """Sube la carpeta del build junto con su `package.json`.

    Homologo de `_publish` en el APK: van los dos o no va ninguno. La carpeta
    compilada no lleva su version adentro, y si el `package.json` del VPS
    queda con el numero viejo, todo lo que lo lea (health check, la propia
    SPA) va a anunciar una version que ya no es la que esta servida.
    """
    upload_artifact(ctx, salida)
    upload_artifact(ctx, manifest)


# --- pasos de binario ------------------------------------------------------

# Entrypoints que se prueban cuando el campo queda vacio, en orden. `src/main.py`
# va primero porque es el que ya usa el launcher de la terminal
# (`core/tasks/launchers.py::open_terminal`): el ejecutable que se descarga es la
# misma app que se lanza en desarrollo, y preguntar la ruta seria pedir que
# confirmen lo que la carpeta ya contesta.
_ENTRYPOINTS = ('src/main.py', 'main.py', 'app/main.py')

# Un entrypoint llamado asi no nombra al programa, nombra al archivo de arranque:
# `src/main.py` daria un ejecutable "main". En ese caso el nombre sale de la
# carpeta de la app, que es como se llama el proyecto.
_NOMBRES_GENERICOS = ('main', '__main__', 'app', 'cli', 'run')


def resolve_entrypoint(ctx, entrypoint: str = '') -> Path:
    """El archivo Python que PyInstaller va a empaquetar.

    Escrito a mano gana siempre — el script original aceptaba cualquier ruta del
    repo (`server/main.py`, `tools/cli.py`) y eso se conserva. Vacio se deduce:
    el unico `python-app` del repo y su `src/main.py`, y si el repo no tiene
    ninguno, un `main.py` en la raiz (el caso de una app de un solo arranque,
    como la propia Consola).

    No hay eje `app` con la lista de apps descubiertas, a diferencia de los otros
    dos builders: un eje descubierto vacio bloquea el boton en ambar, y un repo
    que se empaqueta desde su raiz no tiene ningun `python-app` que descubrir —
    quedaria sin poder compilarse su propio ejecutable.
    """
    if entrypoint:
        fuente = ctx.path(entrypoint)
        if not fuente.is_file():
            raise TaskError(f'No existe el punto de entrada: {fuente}')
        return fuente

    apps = targets.by_kind(ctx.root, targets.PYTHON_APP)
    if len(apps) > 1:
        elegir = ', '.join(a.name for a in apps)
        raise TaskError(f'Hay mas de una app Python en {ctx.root.name}: {elegir}. '
                        'Escribe el punto de entrada de la que quieras empaquetar.')

    base = apps[0].path if apps else ctx.root
    for candidato in _ENTRYPOINTS:
        fuente = base / candidato
        if fuente.is_file():
            return fuente
    raise TaskError(f'No se encontro un punto de entrada en {base.name} '
                    f'({", ".join(_ENTRYPOINTS)}). Escribe cual es.')


def _binary_app(root: Path, fuente: Path) -> Path:
    """La carpeta de la app a la que pertenece el entrypoint.

    Es donde vive el manifiesto que se versiona y donde PyInstaller deja
    `dist/` y `build/`. Se busca subiendo desde el entrypoint hasta encontrar un
    manifiesto: el script original se quedaba con `entrypoint.parent`, que para
    `src/main.py` es `src/` y terminaba creando ahi un `pyproject.toml` paralelo
    al de la app, con su propia version que nadie mas leia.
    """
    carpeta = fuente.parent
    while carpeta != carpeta.parent:
        if any((carpeta / nombre).is_file() for nombre in versioning.MANIFEST_NAMES):
            return carpeta
        if carpeta == root:
            break
        carpeta = carpeta.parent
    return root


def _ensure_manifest(ctx, app_dir: Path) -> Path:
    """El manifiesto de version de la app; se crea en 0.0.0 si no hay ninguno.

    Es el `_ensure_pyproject` del script original, y esta por la misma razon:
    un script suelto que se empieza a distribuir no tiene por que traer un
    `pyproject.toml` escrito de antemano, y sin manifiesto no hay version que
    subir ni que publicar al lado del binario.
    """
    try:
        return versioning.find_manifest(app_dir)
    except TaskError:
        pass
    nombre = re.sub(r'[^0-9A-Za-z._-]+', '-', app_dir.name).strip('-').lower() or 'python-app'
    manifiesto = app_dir / 'pyproject.toml'
    files.write_text(manifiesto, f'[project]\nname = "{nombre}"\nversion = "0.0.0"\n')
    ctx.warn(f'{app_dir.name} no tenia manifiesto: se creo {manifiesto.name} en 0.0.0.')
    return manifiesto


def _binary_label(app_dir: Path, fuente: Path, name: str) -> str:
    """Nombre del ejecutable, con la etiqueta de la plataforma que lo produjo.

    PyInstaller no compila cruzado: el binario sirve para el sistema donde corre
    Consola, y sin la etiqueta el de Windows y el de Linux se pisan en la misma
    ruta del VPS. El nombre no lleva la version a proposito — la URL de descarga
    se mantiene estable y quien quiere saber que version es lee el manifiesto
    que se publica al lado.
    """
    base = name.strip()
    if not base:
        base = app_dir.name if fuente.stem in _NOMBRES_GENERICOS else fuente.stem
    return f'{base}-{platform.system().lower()}-{platform.machine().lower()}'


def _binary_output(app_dir: Path, etiqueta: str, onefile: bool) -> Path:
    """Donde queda lo que deja PyInstaller: un archivo con `--onefile`, una
    carpeta sin el. Sirve para leer lo recien compilado y para encontrar lo que
    ya estaba, igual que `_last_apk` y `_spa_output`."""
    sufijo = '.exe' if platform.system() == 'Windows' and onefile else ''
    return app_dir / 'dist' / f'{etiqueta}{sufijo}'


def compile_binary(ctx, entrypoint: str = '', name: str = '', *, onefile: bool = True,
                   windowed: bool = False, icon: str = '') -> Path:
    """Empaqueta un ejecutable con PyInstaller.

    Corre con la carpeta de la app como directorio de trabajo, no con la raiz
    del repo: asi `dist/` y `build/` quedan al lado del manifiesto que se acaba
    de versionar, que es lo que hacia el script original.

    `--specpath build` manda el `.spec` generado adentro de `build/`. Es un
    archivo derivado, y en la raiz de la app aparecia como cambio sin commitear
    despues de cada compilacion; en `build/` ya lo cubre 'Limpiar artefactos'.

    No se pasa `--clean`: borra la cache de PyInstaller y vuelve a analizar
    todas las dependencias en cada corrida. Es la misma economia por la que
    `install_node_modules` usa `npm install` y no `npm ci` — la cache existe
    justo para el build repetido, y para el limpio de verdad esta el boton de
    limpiar artefactos.
    """
    fuente = resolve_entrypoint(ctx, entrypoint)
    app_dir = _binary_app(ctx.root, fuente)
    etiqueta = _binary_label(app_dir, fuente, name)
    pyinstaller = toolchain.pyinstaller_cmd(app_dir, ctx.config.get('PYINSTALLER_BIN'))

    argv = [*pyinstaller, '--noconfirm', '--name', etiqueta,
            '--specpath', 'build', *(['--onefile'] if onefile else [])]
    if windowed:
        # Sin consola: en Windows una app de ventana abre ademas una cmd negra
        # detras si se empaqueta sin esto.
        argv.append('--windowed')
    if icon:
        ruta_icono = ctx.path(icon)
        if not ruta_icono.is_file():
            raise TaskError(f'No existe el icono: {ruta_icono}')
        argv += ['--icon', str(ruta_icono)]
    (app_dir / 'build').mkdir(parents=True, exist_ok=True)
    ctx.run([*argv, str(fuente)], cwd=app_dir)

    artefacto = _binary_output(app_dir, etiqueta, onefile)
    if not artefacto.exists():
        raise TaskError(f'PyInstaller no dejo el binario esperado en {artefacto}.')
    ctx.ok(f'Binario: {artefacto} ({files.human_size(files.size_of(artefacto))})')
    return artefacto


def checksum_artifact(ctx, artifact: Path) -> Path:
    """Escribe el SHA-256 del artefacto al lado, en formato `sha256sum`.

    Un ejecutable que se descarga no se puede mirar por dentro: el hash es lo
    unico que deja comprobar que lo bajado es lo que se publico. Se guarda como
    `<binario>.sha256` para que `sha256sum -c` lo verifique sin editarlo.
    """
    if artifact.is_dir():
        # Con `--onefile` desactivado no hay un archivo que firmar sino un arbol
        # entero; un hash por archivo no es lo que nadie va a verificar a mano.
        raise TaskError('El checksum solo aplica al empaquetado en un archivo.')
    huella = files.digest(artifact)
    destino = artifact.with_name(f'{artifact.name}.sha256')
    files.write_text(destino, f'{huella}  {artifact.name}\n')
    ctx.ok(f'SHA-256: {huella}')
    return destino


def _maybe_checksum(ctx, artifact: Path) -> Path | None:
    """El checksum del paso marcado, salteado con un aviso si no aplica.

    El empaquetado en carpeta no tiene un archivo que firmar, y ahi el paso no
    es un error: es una combinacion que no significa nada. Fallar despues de
    empaquetar —lo unico caro del flujo— seria tirar el build por una casilla.
    """
    if artifact.is_dir():
        ctx.warn('Checksum omitido: el empaquetado en carpeta no es un archivo que firmar.')
        return None
    return checksum_artifact(ctx, artifact)


def _publish_binary(ctx, artifact: Path, manifest: Path, checksum: Path | None) -> None:
    """Sube el binario con su manifiesto (y su checksum, si se genero).

    Homologo de `_publish` y `_publish_spa`: van juntos o no va ninguno. El
    ejecutable no dice de que version es, y del lado del VPS el manifiesto es lo
    unico que lo identifica. El script original subia los dos solo en su rama
    `BUILD_BINARY=false`; en la normal dejaba el manifiesto remoto viejo.

    El binario se sube con permiso de ejecucion: `scp` no lo conserva, y del
    otro lado quedaba un ejecutable que no se podia ejecutar.
    """
    # `chmod -R` para el empaquetado en carpeta: ahi el ejecutable es un archivo
    # de adentro, y el bit del directorio no le sirve de nada.
    upload_artifact(ctx, artifact, chmod='-R 755' if artifact.is_dir() else '755')
    upload_artifact(ctx, manifest)
    if checksum is not None:
        upload_artifact(ctx, checksum)


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
    que no se comparte es el `+build` de `bump_mode` (subir el build number),
    que necesita el `+N` de `pubspec.yaml` y falla con ese mensaje en un
    `pyproject.toml` de Flet.

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
        ctx.step('upload')
        _publish(ctx, apk, manifiesto)
        ctx.note(f'Re-subida APK {app.name} {versioning.read_version(manifiesto)}')
        return apk

    with files.reversible(manifiesto):
        if bump:
            ctx.step('bump')
            bump_version(ctx, app.name, bump_mode)
        ctx.step('build')
        apk = compile_apk(ctx, app.name)

    if upload:
        ctx.step('upload')
        _publish(ctx, apk, manifiesto)

    ctx.note(f'Build APK {app.name} {versioning.read_version(manifiesto)}')
    return apk


def build_vite(
    ctx,
    directories: Sequence[str] = (),
    bump_mode: str = 'patch',
    *,
    bump: bool = True,
    build: bool = True,
    upload: bool = False,
) -> list[Path]:
    """Compuesta: por cada SPA elegida, npm install -> bump -> build -> subida.

    Mismo esqueleto que `build_apk`, con la unica diferencia que declara el
    catalogo: su eje es `many`. Un repo tiene una app movil pero suele tener
    tres SPA (`panel`, `backoffice`, `landing`), y compilarlas es una tarea que
    termina — asi que las marcadas se recorren en un bucle aca dentro, N builds
    en fila en un solo log, y no una pestana por cada una como hace el launcher
    de dev servers (docs/launchers.md 2.1).

    La lista vacia significa "la unica SPA que haya", igual que el `directory`
    vacio de `build_apk`: en un repo con una sola, el eje ni se dibuja.

    Cada SPA se compila y se sube entera antes de pasar a la siguiente, y su
    bump es reversible por separado: si la tercera revienta, las dos que ya se
    publicaron conservan la version con la que salieron.
    """
    elegidas = [_target(ctx, targets.SPA_VITE, nombre) for nombre in (directories or [''])]
    salidas: list[Path] = []
    for indice, spa in enumerate(elegidas, start=1):
        ctx.raise_if_cancelled()
        if len(elegidas) > 1:
            ctx.step(f'{spa.name} ({indice} de {len(elegidas)})')
        salidas.append(_build_spa(ctx, spa, bump_mode, bump=bump, build=build, upload=upload))
    return salidas


def _build_spa(
    ctx,
    spa: targets.Target,
    bump_mode: str,
    *,
    bump: bool,
    build: bool,
    upload: bool,
) -> Path:
    """Una SPA. Es el cuerpo de `build_apk` con `npm` en vez de `flutter`.

    Sin `build` no se compila nada: se sube la carpeta que ya esta en disco.
    Es el modo que el script original activaba con `BUILD_SPA=false`, y la
    razon es la misma que en el APK — retomar un scp cortado no deberia costar
    otro `npm install` y otro build.

    A diferencia del APK, aca si hay paso de dependencias: `npm run build` no
    instala nada, y el bump acaba de tocar `package.json` sin agregar ninguna.

    Se sube la carpeta del build Y el `package.json` recien bumpeado, igual
    que `_publish` sube el APK con su manifiesto. El script original solo
    subia el manifiesto en su rama `BUILD_SPA=false`; que el build normal lo
    dejara sin actualizar del lado del VPS era un descuido, no una decision:
    la carpeta compilada no dice de que version es.
    """
    manifiesto = versioning.find_manifest(spa.path)

    if not build:
        if not upload:
            raise TaskError('Sin compilar y sin subir no queda nada por hacer.')
        if bump:
            ctx.warn('Bump ignorado: la carpeta que hay en disco se compilo con la '
                     'version que ya tiene el manifiesto, y subirla cambiada la '
                     'anunciaria como otra cosa.')
        salida = _spa_output(spa)
        ctx.step('upload')
        _publish_spa(ctx, salida, manifiesto)
        ctx.note(f'Re-subida SPA {spa.name} {versioning.read_version(manifiesto)}')
        return salida

    with files.reversible(manifiesto):
        ctx.step('Dependencias')
        install_node_modules(ctx, spa.name)
        if bump:
            ctx.step('bump')
            bump_version(ctx, spa.name, bump_mode)
        ctx.step('build')
        salida = compile_spa(ctx, spa.name)

    if upload:
        ctx.step('upload')
        _publish_spa(ctx, salida, manifiesto)

    ctx.note(f'Build Vite {spa.name} {versioning.read_version(manifiesto)}')
    return salida


def build_binary(
    ctx,
    entrypoint: str = '',
    name: str = '',
    bump_mode: str = 'patch',
    *,
    onefile: bool = True,
    windowed: bool = False,
    icon: str = '',
    bump: bool = True,
    build: bool = True,
    checksum: bool = True,
    upload: bool = False,
) -> Path | None:
    """Compuesta: bump del manifiesto -> PyInstaller -> checksum -> subida.

    Mismo esqueleto que `build_apk` y `build_vite`, y por fin con el mismo modo
    re-subida: sin `build` no se compila nada y se sube el ejecutable que ya
    esta en `dist/`. Es el `BUILD_BINARY=false` del script original — que era
    justamente el modo que existia para retomar un `scp` cortado sin pagar otro
    empaquetado entero — y por eso 'Compilar binario' dejo de ser un paso fijo.

    Si el build falla, la version vuelve a lo que era: el repo no queda marcado
    con un numero que nunca se publico.
    """
    fuente = resolve_entrypoint(ctx, entrypoint)
    app_dir = _binary_app(ctx.root, fuente)
    manifiesto = _ensure_manifest(ctx, app_dir)
    rel = '' if app_dir == ctx.root else app_dir.relative_to(ctx.root).as_posix()

    if not build:
        if not upload:
            raise TaskError('Sin compilar y sin subir no queda nada por hacer.')
        if bump:
            ctx.warn('Bump ignorado: el binario que hay en disco se empaqueto con la '
                     'version que ya tiene el manifiesto, y subirla cambiada lo '
                     'anunciaria como otra cosa.')
        artefacto = _binary_output(app_dir, _binary_label(app_dir, fuente, name), onefile)
        if not artefacto.exists():
            raise TaskError(f'No hay ningun binario compilado en {artefacto}.')
        firma = _maybe_checksum(ctx, artefacto) if checksum else None
        ctx.step('upload')
        _publish_binary(ctx, artefacto, manifiesto, firma)
        ctx.note(f'Re-subida binario {artefacto.name} {versioning.read_version(manifiesto)}')
        return artefacto

    with files.reversible(manifiesto):
        if bump:
            ctx.step('bump')
            bump_version(ctx, rel, bump_mode)
        ctx.step('build')
        artefacto = compile_binary(ctx, str(fuente), name, onefile=onefile,
                                   windowed=windowed, icon=icon)

    firma = None
    if checksum:
        ctx.step('checksum')
        firma = _maybe_checksum(ctx, artefacto)

    if upload:
        ctx.step('upload')
        _publish_binary(ctx, artefacto, manifiesto, firma)

    ctx.note(f'Build binario {artefacto.name} {versioning.read_version(manifiesto)}')
    return artefacto


def bind_all() -> None:
    registry.bind('build_apk', build_apk)
    registry.bind('build_vite', build_vite)
    registry.bind('build_binary', build_binary)
    registry.bind('promote_app', promote_app)
    registry.bind('bump_version', bump_version)
    registry.bind('upload_to_vps', upload_artifact)
