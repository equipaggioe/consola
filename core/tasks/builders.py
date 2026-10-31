from __future__ import annotations
import json
import platform
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from .. import files, icons, ssh, targets, toolchain, versioning, vps
from . import raster
from ..errors import TaskError
from ..host import HOST
from ..registry import registry

"""
Grupo Compilar.

Los tres builders eran el mismo esqueleto repetido tres veces: subir la version
del manifiesto, correr la herramienta que compila, y opcionalmente subir el
artefacto al VPS. Cada uno traia su propia copia del bump (uno para
`pubspec.yaml`, otro para `package.json`, otro para `pyproject.toml`) y su
propia copia del scp.

Aca el bump es una sola atomica que sirve para los tres manifiestos, la subida
es otra, y lo unico propio de cada builder es el paso de compilacion. Solo el
ejecutable sigue subiendo la version y publicando en el VPS: la app movil y las
SPA compilan y nada mas (ADR-0059).
"""


def _target(ctx, kind: str, name: str = '') -> targets.Target:
    return targets.pick(ctx.root, (kind,), name)


def _mobile(ctx, name: str = '') -> targets.Target:
    """La app movil del repo, sea Flutter o Flet.

    Los dos tipos se buscan juntos porque el framework no es una eleccion de
    quien aprieta el boton: es una propiedad de la carpeta, y `compile_flutter` la
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

def compile_flutter(ctx, directory: str = '', platform_id: str = 'apk') -> Path:
    """Compila la app para una plataforma. Es el unico paso que cambia entre
    Flutter y Flet, y entre una plataforma y otra.

    La URL de la API se inyecta por `--dart-define` desde la configuracion: es
    la misma fuente que usa el launcher de debug, para que release y debug no
    apunten a servidores distintos por descuido. Flet no tiene `--dart-define`
    propio: se lo pasa a su `flutter build` de abajo con `--flutter-build-args`.

    En web la app va en la raiz de su host, que es el default de Flutter: cada
    pieza tiene el suyo (ADR-0065).

    Offline no hay: el service worker que genera Flutter se des-registra solo
    (su `--pwa-strategy` esta deprecado y ya no cachea nada), asi que la app es
    instalable por su `manifest.json` pero solo funciona en linea.
    """
    app = _mobile(ctx, directory)
    kind = toolchain.detect_app_kind(app.path)
    destino = toolchain.BUILD_PLATFORMS[platform_id]
    api = ctx.config.require('API_URL')
    define = f'--dart-define=API_BASE_URL={api}'

    if kind == toolchain.FLUTTER:
        ctx.run([*toolchain.flutter_cmd(), 'build', destino.flutter, '--release', define],
                cwd=app.path)
    else:
        # La variable de entorno queda para el codigo Python que la lea al empaquetar.
        ctx.run([*toolchain.flet_cmd(), 'build', destino.flet,
                 f'--flutter-build-args={define}'],
                cwd=app.path, env={'API_BASE_URL': api})

    patron = destino.output(kind)
    salida = _newest(app.path, patron)
    if salida is None:
        raise TaskError(f'El build {destino.label} termino pero no aparecio nada en {patron}.')
    salida = _deliver(ctx, app.path, platform_id, salida)
    ctx.ok(f'{destino.label}: {salida} ({files.human_size(files.size_of(salida))})')
    return salida


def _newest(base: Path, patron: str) -> Path | None:
    encontrados = list(base.glob(patron))
    return max(encontrados, key=lambda p: p.stat().st_mtime, default=None)


def _out_dir(ctx, app_dir: Path, platform_id: str) -> Path | None:
    """La carpeta de `config.env` donde tiene que quedar el build, si hay una.

    Vacia, el build se queda donde lo deja el framework. Es relativa a la
    carpeta de la app, igual que las rutas por defecto que muestra el campo.
    """
    valor = ctx.config.get(toolchain.out_key(platform_id))
    return app_dir / valor if valor else None


def _deliver(ctx, app_dir: Path, platform_id: str, salida: Path) -> Path:
    """Copia el build a la carpeta configurada, si hay una.

    Se copia y no se le pide al framework que compile ahi: Flutter solo acepta
    `--output` en web, y asi las siete plataformas funcionan igual en los dos
    frameworks. Un APK o un IPA quedan *dentro* de la carpeta; un build web o de
    escritorio, que ya es una carpeta, pasa a *ser* ella.
    """
    carpeta = _out_dir(ctx, app_dir, platform_id)
    if carpeta is None:
        return salida
    destino = carpeta / salida.name if toolchain.BUILD_PLATFORMS[platform_id].suffix else carpeta
    files.copy(salida, destino)
    return destino


# --- manifiesto de release -------------------------------------------------
#
# Que version esta publicada es un hecho del artefacto, no configuracion del
# servidor. Tenerlo como variable de entorno del backend obligaba a editar un
# `.env`, subirlo y reiniciar el servicio para anunciar un build — tres pasos
# que no tienen nada que ver con compilar, y que se saltean solos en cuanto
# alguien publica sin acordarse. Aca lo escribe quien construye, que es el unico
# que sabe la version en el momento exacto en que deja de ser una intencion.
#
# Es la convencion de siempre para actualizaciones: el appcast de Sparkle, el
# `latest.yml` de electron-updater, el `latest.json` de Tauri. Flutter mismo ya
# emite `build/web/version.json`, que es esto para una sola plataforma.
#
# No es una fuente de verdad nueva: se deriva del manifiesto del subproyecto
# (`pubspec.yaml`, `package.json`, `pyproject.toml`) en el momento de publicar,
# asi que no hay nada que mantener sincronizado a mano.

RELEASES_DIR = 'releases'


def _release_manifest(ctx, app: str, platform_id: str, artifact: Path, manifest: Path) -> Path:
    """Escribe `releases/<app>/<plataforma>.json` describiendo lo que se publica.

    El `sha256` va solo cuando el artefacto es un archivo: un build web es un
    arbol, y un hash por archivo no es lo que nadie va a verificar. Sin el, el
    resto del manifiesto sigue sirviendo.
    """
    version = versioning.read_version(manifest)
    datos = {'app': app, 'platform': platform_id, 'version': version.split('+', 1)[0]}
    if '+' in version:
        datos['build'] = int(version.split('+', 1)[1])
    datos['artifact'] = artifact.name
    if artifact.is_file():
        datos['sha256'] = files.digest(artifact)
    datos['published_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    destino = ctx.root / RELEASES_DIR / app / f'{platform_id}.json'
    files.write_text(destino, json.dumps(datos, indent=2, ensure_ascii=False) + '\n')
    ctx.ok(f'Release {app}/{platform_id}: {datos["version"]}')
    return destino


def _publish_release(ctx, app: str, platform_id: str, artifact: Path, manifest: Path) -> None:
    """Escribe el manifiesto de release y lo sube junto al artefacto."""
    upload_artifact(ctx, _release_manifest(ctx, app, platform_id, artifact, manifest))


# --- pasos de Vite ---------------------------------------------------------

def install_node_modules(ctx, directory: str = '') -> None:
    """`npm install`, no `npm ci`: `ci` borra `node_modules` entero y vuelve a
    compilar los binarios nativos, lo que multiplica el tiempo de build."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.npm_cmd(), 'install'], cwd=spa.path)


def compile_spa(ctx, directory: str = '') -> Path:
    """`npm run build`. La SPA va en la raiz de su host, asi que Consola no le
    deja nada adentro: el build es el del repo tal cual (ADR-0065)."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.npm_cmd(), 'run', 'build'], cwd=spa.path)
    salida = _spa_output(spa)
    ctx.ok(f'Build de {spa.name}: {salida} ({files.human_size(files.size_of(salida))})')
    return salida


def _spa_output(spa: targets.Target) -> Path:
    """La carpeta que dejo el build: `dist/` en Vite pelado, `build/` en los
    adaptadores de SvelteKit. Se mira el disco y no `vite.config.*` porque la
    salida puede venir declarada desde un plugin.

    """
    for candidata in ('dist', 'build'):
        salida = spa.path / candidata
        if salida.is_dir():
            return salida
    raise TaskError(f'{spa.name} no tiene carpeta dist/ ni build/.')


# El esqueleto lo pone `sv create`, que es el generador oficial de Svelte: trae
# TypeScript, runes forzadas y el adaptador estatico instalado. UnoCSS no es un
# add-on oficial de `sv`, asi que lo que falta para dejarla lista para Consola
# se escribe encima: el plugin y el `ssr = false` de una SPA estatica.
# Son archivos que Consola acaba de generar, no codigo del repo que se parchea.
_SPA_NAME = re.compile(r'[a-z0-9][a-z0-9._-]*')

_SPA_FILES = {
    'vite.config.ts': """\
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import UnoCSS from 'unocss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		UnoCSS(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => (filename.split(/[/\\\\]/).includes('node_modules') ? undefined : true)
			},
			// SPA estatica: el HTML se sirve tal cual y el enrutamiento es del cliente.
			adapter: adapter({ fallback: 'index.html' })
		})
	]
});
""",
    'uno.config.ts': """\
import { defineConfig, presetWind3 } from 'unocss';

// presetUno (el que usan las demas SPA del monorepo) esta deprecado y es un
// alias de este: mismo motor, nombre vigente. presetWind4 es la migracion a
// Tailwind 4 que ningun otro repo hizo todavia, y divergiria de las demas.
export default defineConfig({
	presets: [presetWind3()]
});
""",
    'src/routes/+layout.ts': """\
export const ssr = false;
""",
    'src/routes/+layout.svelte': """\
<script lang="ts">
	import '@unocss/reset/tailwind.css';
	import 'virtual:uno.css';
	import favicon from '$lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
""",
    'src/routes/+page.svelte': """\
<main class="min-h-screen grid place-items-center">
	<h1 class="text-2xl font-semibold">{NAME}</h1>
</main>
""",
}


def create_spa(ctx) -> Path:
    """Crea en el repo una SPA en blanco: SvelteKit + TypeScript + runes + UnoCSS.

    Queda lista para los otros botones de Vite: `serve_vite` y `build_vite` la
    descubren por su `vite.config.ts`.

    El nombre de la carpeta se pregunta aca y no llega como parametro: es el
    unico dato de la corrida y es distinto en cada una, asi que no tiene donde
    guardarse (`core/catalog.py`, al registrar `create_spa`).
    """
    nombre = ctx.ask('¿Cómo se va a llamar la carpeta de la SPA?').strip()
    if not nombre:
        raise TaskError('Cancelado: no se eligio un nombre de carpeta.')
    if not _SPA_NAME.fullmatch(nombre):
        raise TaskError('El nombre de la carpeta va en minusculas, sin espacios '
                        '(letras, numeros, ".", "_" o "-").')
    destino = ctx.path(nombre)
    if destino.exists():
        raise TaskError(f'Ya existe {destino}.')
    npm = toolchain.npm_cmd()

    ctx.run([*npm, 'exec', '--yes', '--', 'sv@latest', 'create', nombre,
             '--template', 'minimal', '--types', 'ts',
             '--add', 'sveltekit-adapter=adapter:static', '--install', 'npm'],
            cwd=ctx.root)
    ctx.run([*npm, 'install', '--save-dev', 'unocss', '@unocss/reset'], cwd=destino)

    for rel, contenido in _SPA_FILES.items():
        (destino / rel).write_text(contenido.replace('{NAME}', nombre),
                                   encoding='utf-8', newline='\n')

    ctx.ok(f'SPA creada en {destino}')
    ctx.note(f'Nueva SPA {nombre}')
    return destino


# --- pasos de binario ------------------------------------------------------

# Entrypoints que se prueban cuando el campo queda vacio, en orden. `src/main.py`
# va primero porque es el que ya prefiere el launcher App Python
# (`core/targets.py::python_entrypoint`): el ejecutable que se descarga es la
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
    return f'{base}-{HOST.system.lower()}-{platform.machine().lower()}'


def _binary_output(app_dir: Path, etiqueta: str, onefile: bool) -> Path:
    """Donde queda lo que deja PyInstaller: un archivo con `--onefile`, una
    carpeta sin el. Sirve para leer lo recien compilado y para encontrar lo que
    ya estaba."""
    sufijo = HOST.executable_suffix if onefile else ''
    return app_dir / 'dist' / f'{etiqueta}{sufijo}'


def compile_binary(ctx, entrypoint: str = '', name: str = '', *, onefile: bool = True,
                   windowed: bool = False) -> Path:
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
    (app_dir / 'build').mkdir(parents=True, exist_ok=True)
    if ctx.config.get('BRAND_ICON'):
        # El icono del ejecutable es el logo del repo, como el de sus otras
        # apps (ADR-0056). Va a `build/`, que es derivado: lo cubre 'Limpiar
        # artefactos' y no aparece como cambio del repo.
        logo = icons.brand_file(ctx.root, ctx.config.get('BRAND_ICON'), 'BRAND_ICON')
        ico = app_dir / 'build' / 'icon.ico'
        ico.write_bytes(raster.svg_to_ico(logo))
        argv += ['--icon', str(ico)]
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


def _publish_binary(ctx, app: str, artifact: Path, manifest: Path, checksum: Path | None) -> None:
    """Sube el binario con su manifiesto (y su checksum, si se genero).

    Van juntos o no va ninguno. El ejecutable no dice de que version es, y del lado del VPS el manifiesto es lo
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
    _publish_release(ctx, app, HOST.system.lower(), artifact, manifest)


# --- compuestas ------------------------------------------------------------

def build_flutter(
    ctx,
    directory: str = '',
    platforms: Sequence[str] = ('apk',),
) -> list[Path]:
    """Compila la app para cada plataforma marcada.

    Es el `build_flutter.py` de posta, sin el bump ni la subida al VPS: la
    version sale del tag y el APK no se publica en el VPS (ADR-0059). Un solo
    boton para Flutter y para Flet: `directory` nombra *cual* app del repo, no
    con que esta escrita, y el framework sale de la carpeta.

    No hay paso de `pub get`: `flutter build` resuelve dependencias solo.
    """
    app = _mobile(ctx, directory)
    nombres = ', '.join(toolchain.BUILD_PLATFORMS[p].label for p in platforms)
    salidas: list[Path] = []
    for plataforma in platforms:
        ctx.raise_if_cancelled()
        salidas.append(compile_flutter(ctx, app.name, plataforma))
    ctx.note(f'Build {app.name} ({nombres})')
    return salidas


def build_vite(ctx, directories: Sequence[str] = ()) -> list[Path]:
    """Por cada SPA elegida: npm install y build.

    Su eje es `many`: un repo tiene una app movil pero suele tener tres SPA
    (`panel`, `backoffice`, `landing`), y compilarlas es una tarea que termina
    — asi que las marcadas se recorren en un bucle aca dentro, N builds en fila
    en un solo log, y no una pestana por cada una como hace el launcher de dev
    servers (ADR-0010).

    La lista vacia significa "la unica SPA que haya", igual que el `directory`
    vacio de `build_flutter`: en un repo con una sola, el eje ni se dibuja.
    """
    elegidas = [_target(ctx, targets.SPA_VITE, nombre) for nombre in (directories or [''])]
    salidas: list[Path] = []
    for indice, spa in enumerate(elegidas, start=1):
        ctx.raise_if_cancelled()
        if len(elegidas) > 1:
            ctx.step(f'{spa.name} ({indice} de {len(elegidas)})')
        install_node_modules(ctx, spa.name)
        salidas.append(compile_spa(ctx, spa.name))
        ctx.note(f'Build Vite {spa.name}')
    return salidas


def build_binary(
    ctx,
    entrypoint: str = '',
    name: str = '',
    bump_mode: str = 'patch',
    *,
    onefile: bool = True,
    windowed: bool = False,
    bump: bool = True,
    build: bool = True,
    checksum: bool = True,
    upload: bool = False,
) -> Path | None:
    """Compuesta: bump del manifiesto -> PyInstaller -> checksum -> subida.

    Mismo esqueleto que `build_flutter` y `build_vite`, y por fin con el mismo modo
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
        _publish_binary(ctx, app_dir.name, artefacto, manifiesto, firma)
        ctx.note(f'Re-subida binario {artefacto.name} {versioning.read_version(manifiesto)}')
        return artefacto

    with files.reversible(manifiesto):
        if bump:
            ctx.step('bump')
            bump_version(ctx, rel, bump_mode)
        ctx.step('build')
        artefacto = compile_binary(ctx, str(fuente), name, onefile=onefile,
                                   windowed=windowed)

    firma = None
    if checksum:
        ctx.step('checksum')
        firma = _maybe_checksum(ctx, artefacto)

    if upload:
        ctx.step('upload')
        _publish_binary(ctx, app_dir.name, artefacto, manifiesto, firma)

    ctx.note(f'Build binario {artefacto.name} {versioning.read_version(manifiesto)}')
    return artefacto


def bind_all() -> None:
    registry.bind('build_flutter', build_flutter)
    registry.bind('build_vite', build_vite)
    registry.bind('create_spa', create_spa)
    registry.bind('build_binary', build_binary)
    registry.bind('bump_version', bump_version)
    registry.bind('upload_to_vps', upload_artifact)
