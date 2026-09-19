from __future__ import annotations
import threading
from pathlib import Path

from . import emulators
from .. import database as db
from .. import ports, session, ssh, targets, toolchain
from ..errors import TaskError
from ..registry import registry
from ..toolchain import venv_python

"""
Grupo Launchers.

Los launchers eran cuatro scripts que se pasaban datos por el `.env`: el backend
escribia `SERVER_PORT` a disco y el terminal y las SPA lo leian despues. Aca ese
puerto es estado de sesion en memoria (`core/session.py`), lo publica quien
arranca el backend y lo leen los que arrancan despues.

Lo que un launcher entrega no es su log: es un **endpoint**, una URL. Por eso
todos llaman a `ctx.serve()` apenas conocen su puerto, antes de arrancar el
proceso. De ahi salen la barra de la pestana, el navegador embebido y la senal
que espera el launcher siguiente (docs/launchers.md).

Ninguna de las funciones `resolve_*` de este modulo es una atomica con boton:
son la plomeria de las que si lo son, igual que `_download` o `_extract` dentro
de `install_android_tools` (docs/atomicas.md 0). `serve_backend` es UNA atomica
hecha de cinco funciones.
"""

SERVER_PORT = 'SERVER_PORT'
BACKEND = 'backend'          # clave del endpoint del backend en `core/session`

# Cuanto espera un launcher dependiente a que el backend conteste. Generoso
# porque el caso que importa es el arranque conjunto (docs/launchers.md 2.5):
# uvicorn con --reload y una base remota por tunel tarda sus buenos segundos.
BACKEND_WAIT = 90.0


# --- atomicas --------------------------------------------------------------

def resolve_server_port(ctx, preferred: int = 8000, search: bool = True) -> int:
    """Elige el puerto del backend y lo publica para las tareas que vengan despues.

    No es un boton: nadie pide "elige un puerto y nada mas". Es plomeria de
    `serve_backend`, que si lo es (docs/launchers.md 1).
    """
    puerto = ports.resolve_port(preferred, search=search, label='puerto del backend')
    session.publish(ctx.project.name, SERVER_PORT, puerto)
    ctx.info(f'Puerto del backend: {puerto}')
    return puerto


def backend_url(ctx, *, wait: float = 0.0, required: bool = True) -> str:
    """La URL del backend de esta corrida, para los launchers que la necesitan.

    Con `wait`, espera a que el backend conteste de verdad en vez de mirar solo
    si alguien publico un puerto. Es lo que hace que "Entorno de desarrollo"
    funcione sin depender del orden en que arrancaron las pestanas: la SPA se
    queda esperando el endpoint del backend, no un `sleep` (docs/launchers.md 2.5).

    Con `required=False` devuelve cadena vacia si no hay backend, en vez de
    fallar: para la SPA eso no es un error, es arrancar con su propia config.
    """
    endpoint = ctx.endpoint(BACKEND, wait=wait)
    if endpoint is not None:
        if endpoint.state == session.DOWN and required:
            raise TaskError(f'El backend no llego a responder en {endpoint.url}.')
        return endpoint.url
    if not required:
        return ''
    raise TaskError('El backend todavia no arranco en esta sesion: '
                    'levantalo primero, o usa "Entorno de desarrollo".')


def resolve_tls(ctx, server: Path) -> tuple[Path, Path] | None:
    """Los certificados del backend, si estan. Sin ellos arranca en texto plano.

    Se buscan en `certs/` de la carpeta del servidor, como hacia el script
    original: `CERT_FILE_PATH` y `KEY_FILE_PATH` son las rutas del servicio en
    el VPS, no las de esta maquina.
    """
    cert = server / 'certs' / 'cert.pem'
    key = server / 'certs' / 'key.pem'
    if cert.is_file() and key.is_file():
        return cert, key
    ctx.warn('TLS deshabilitado: faltan los certificados.')
    return None


# --- launchers -------------------------------------------------------------

def serve_backend(
    ctx,
    target: str = '',
    scope: str = db.LOCAL,
    host: str = '0.0.0.0',
    preferred_port: int = 8000,
    reload: bool = True,
) -> None:
    """Arranca uvicorn con la base del ambito elegido.

    El tunel, si el ambito es remoto, vive lo que vive el servidor: se cierra
    solo cuando se detiene la pestana.
    """
    server = targets.pick(ctx.root, (targets.FASTAPI,), target).path
    interprete = venv_python(server / '.venv')
    puerto = resolve_server_port(ctx, preferred_port)
    app = targets.asgi_app(server)

    argv = [str(interprete), '-m', 'uvicorn', app, '--host', host, '--port', str(puerto)]
    if reload:
        argv.append('--reload')
    tls = resolve_tls(ctx, server)
    if tls:
        argv.extend(['--ssl-certfile', str(tls[0]), '--ssl-keyfile', str(tls[1])])

    # La URL que se anuncia no es la de escucha: `0.0.0.0` es donde escucha,
    # `localhost` es por donde se entra. Un navegador apuntado a `0.0.0.0` no
    # llega a ningun lado.
    esquema = 'https' if tls else 'http'
    with db.connect(ctx, scope) as conn:
        ctx.info(f'Backend {app} escuchando en {host}:{puerto}')
        ctx.serve(f'{esquema}://localhost:{puerto}', key=BACKEND, label='Backend')
        try:
            ctx.run(argv, cwd=server, env={'DATABASE_URL': conn.url}, check=False)
        finally:
            session.forget(ctx.project.name, SERVER_PORT)


def serve_spa(ctx, target: str = '', preferred_port: int = 5173,
              wait_backend: float = BACKEND_WAIT) -> None:
    """Arranca `npm run dev` de una SPA, apuntandola al backend de esta sesion.

    Corre UNA sola SPA. Marcar varias en el panel no la hace iterar: cada una es
    un proceso vivo con su puerto y su consola, asi que la interfaz abre una
    pestana por cada una y llama aca una vez por pestana (docs/launchers.md 2.1).
    """
    spa = targets.pick(ctx.root, (targets.SPA_VITE,), target)
    puerto = ports.resolve_port(preferred_port, label=f'puerto de {spa.name}')

    # Sin backend no es un error: la SPA arranca con lo que tenga en su .env.
    # Con backend arrancando en otra pestana, se lo espera — el orden en que se
    # apretaron los botones no deberia decidir si la SPA sabe adonde pegarle.
    api = backend_url(ctx, wait=wait_backend, required=False)
    if api:
        ctx.info(f'Backend detectado: {api}')
    else:
        ctx.warn('El backend no esta corriendo: la SPA va a usar su propia configuracion.')

    ctx.serve(f'http://localhost:{puerto}', key=f'spa:{spa.name}', label=spa.name)
    ctx.run([*toolchain.npm_cmd(), 'run', 'dev', '--', '--port', str(puerto)],
            cwd=spa.path, env={'VITE_SERVER_URL': api} if api else None, check=False)


def run_mobile(ctx, target: str = '', device: str = '') -> None:
    """Corre la app movil en el emulador activo, con el framework que detecte.

    Si no hay emulador vivo lo dice y no intenta arrancar contra el escritorio:
    ese era el modo mas facil de perder diez minutos con `flutter run`.
    """
    app = targets.pick(ctx.root, targets.MOBILE_APP, target)
    kind = toolchain.detect_app_kind(app.path)

    # Orden de preferencia: lo que se pidio a mano, el emulador que arranco la
    # pestana "Emulador" de esta sesion, y recien despues el primero que
    # conteste. Con dos emuladores vivos, "el primero" es una loteria.
    serial = (device
              or session.read(session.MACHINE, emulators.EMULATOR_SERIAL, '')
              or toolchain.pick_emulator(toolchain.devices(ctx, app.path)))
    if not serial:
        raise TaskError('No hay ningun emulador Android corriendo. Arranca uno primero.')

    api = ctx.config.get('API_URL') or backend_url(ctx, wait=BACKEND_WAIT)
    ctx.info(f'{kind} en {serial} contra {api}')

    if kind == toolchain.FLUTTER:
        argv = [*toolchain.flutter_cmd(), 'run', '-d', serial, f'--dart-define=API_BASE_URL={api}']
        ctx.run(argv, cwd=app.path, check=False)
    else:
        ctx.run([*toolchain.flet_cmd(), 'run', '--android'], cwd=app.path,
                env={'API_BASE_URL': api}, check=False)


def run_python_app(ctx, target: str = '', auto_login: bool = False,
                   wait_backend: float = BACKEND_WAIT) -> None:
    """Arranca una app Python del repo y la relanza al cambiar sus fuentes.

    Corre UNA app: marcar varias abre una pestana por cada una, igual que las
    SPA (docs/launchers.md 2.1). Son dos niveles de proceso: el vigilante y su
    hijo. Detener la pestana mata los dos, de abajo hacia arriba (PLAN.md 7,
    caso 6).
    """
    app = targets.pick(ctx.root, targets.DESKTOP_APP, target)
    entrada = targets.python_entrypoint(app.path)
    if entrada is None:
        raise TaskError(f'{app.name} no tiene punto de entrada '
                        f'({", ".join(targets.PYTHON_ENTRYPOINTS)}).')
    fuente = entrada.parent
    interprete = toolchain.app_python(app.path, ctx.root)

    # Con backend se le pasa su URL; sin el, la app arranca igual con su propia
    # configuracion, como la SPA. Que le haga falta o no es asunto de la app.
    entorno = {}
    api = backend_url(ctx, wait=wait_backend, required=False)
    if api:
        entorno['SERVER_URL'] = api
        ctx.info(f'Backend detectado: {api}')
    if auto_login:
        entorno['TERMINAL_DEV_AUTO_LOGIN'] = 'true'

    while not ctx.cancelled:
        ctx.info(f'Lanzando {app.name}...')
        # El vigilante corre al lado del proceso y lo mata apenas cambia un
        # fuente: `ctx.run` vuelve y la vuelta siguiente lo relanza. Si el
        # proceso termina solo, sin cambios, la tarea termina con el.
        cambio, fin = threading.Event(), threading.Event()
        vigia = threading.Thread(target=_watch, args=(ctx, fuente, cambio, fin), daemon=True)
        vigia.start()
        try:
            codigo = ctx.run([*interprete, entrada.name], cwd=fuente, env=entorno or None,
                             check=False, echo=False)
        finally:
            fin.set()
            vigia.join()
        if ctx.cancelled:
            return
        if not cambio.is_set():
            ctx.info(f'{app.name} termino con codigo {codigo}.')
            return
        ctx.info('Cambios detectados: reiniciando.')


# Cada cuanto se miran los fuentes. El script original usaba 0.35 s; medio
# segundo no se nota al guardar y recorre la mitad de veces.
WATCH_INTERVAL = 0.5
# Lo que el script original vigilaba: codigo y hojas de estilo de Qt.
_WATCHED = {'.py', '.qss'}


def _watch(ctx, root: Path, cambio: threading.Event, fin: threading.Event) -> None:
    firma = _snapshot(root)
    while not fin.wait(WATCH_INTERVAL):
        try:
            actual = _snapshot(root)
        except OSError:
            continue   # un archivo borrado a mitad del recorrido: se mira en la vuelta siguiente
        if actual != firma:
            cambio.set()
            ctx.kill_children()
            return


def _snapshot(root: Path) -> dict[str, float]:
    # Sin el venv ni los artefactos: una app en la raiz del repo tendria que
    # recorrerlos enteros en cada vuelta.
    return {str(p): p.stat().st_mtime for p in root.rglob('*')
            if p.suffix in _WATCHED and p.is_file()
            and not any(parte in targets.IGNORED or parte.startswith('.')
                        for parte in p.relative_to(root).parts[:-1])}


def open_ssh_session(ctx) -> None:
    """Abre la sesion SSH en una terminal externa: necesita TTY real (PLAN.md 7.1)."""
    remote = ssh.resolve_remote(ctx.config)
    ctx.detach(ssh.terminal_argv(remote))
    ctx.ok(f'Sesion SSH abierta en una terminal externa: {remote.target}')


def bind_all() -> None:
    registry.bind('backend', serve_backend)
    registry.bind('serve_vite', serve_spa)
    registry.bind('run_mobile', run_mobile)
    registry.bind('run_python', run_python_app)
    registry.bind('ssh_login', open_ssh_session)
