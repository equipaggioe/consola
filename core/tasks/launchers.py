from __future__ import annotations
from pathlib import Path

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

Cada launcher se parte en dos: preparar el entorno (una atomica que se puede
mirar sola) y arrancar el proceso.
"""

SERVER_PORT = 'SERVER_PORT'


def _server_root(ctx) -> Path:
    root = ctx.root / ctx.config.get('SERVER_DIR', 'server')
    if not root.is_dir():
        raise TaskError(f'No existe la carpeta del servidor: {root}')
    return root


# --- atomicas --------------------------------------------------------------

def resolve_server_port(ctx, preferred: int = 8000, search: bool = True) -> int:
    """Elige el puerto del backend y lo publica para las tareas que vengan despues.

    Boton propio poco frecuente, pero atomica muy usada: cualquier launcher que
    necesite hablarle al backend pregunta por este valor en vez de adivinarlo.
    """
    puerto = ports.resolve_port(preferred, search=search, label='puerto del backend')
    session.publish(ctx.project.name, SERVER_PORT, puerto)
    ctx.info(f'Puerto del backend: {puerto}')
    return puerto


def backend_url(ctx, scheme: str = 'http') -> str:
    """La URL del backend de esta corrida, para los launchers que la necesitan."""
    puerto = session.read(ctx.project.name, SERVER_PORT)
    if puerto is None:
        raise TaskError('El backend todavia no arranco en esta sesion: no hay puerto publicado.')
    return f'{scheme}://localhost:{puerto}'


def resolve_tls(ctx) -> tuple[Path, Path] | None:
    """Los certificados del backend, si estan. Sin ellos arranca en texto plano."""
    cert = ctx.path(ctx.config.get('CERT_FILE_PATH', 'server/certs/cert.pem'))
    key = ctx.path(ctx.config.get('KEY_FILE_PATH', 'server/certs/key.pem'))
    if cert.is_file() and key.is_file():
        return cert, key
    ctx.warn('TLS deshabilitado: faltan los certificados.')
    return None


# --- launchers -------------------------------------------------------------

def serve_backend(
    ctx,
    scope: str = db.LOCAL,
    host: str = '0.0.0.0',
    preferred_port: int = 8000,
    reload: bool = True,
) -> None:
    """Arranca uvicorn con la base del ambito elegido.

    El tunel, si el ambito es remoto, vive lo que vive el servidor: se cierra
    solo cuando se detiene la pestana.
    """
    server = _server_root(ctx)
    interprete = venv_python(server / '.venv')
    puerto = resolve_server_port(ctx, preferred_port)
    app = ctx.config.get('UVICORN_APP', 'app.main:app')

    argv = [str(interprete), '-m', 'uvicorn', app, '--host', host, '--port', str(puerto)]
    if reload:
        argv.append('--reload')
    tls = resolve_tls(ctx)
    if tls:
        argv.extend(['--ssl-certfile', str(tls[0]), '--ssl-keyfile', str(tls[1])])

    with db.connect(ctx, scope) as conn:
        ctx.info(f'Backend en {"https" if tls else "http"}://{host}:{puerto} ({app})')
        try:
            ctx.run(argv, cwd=server, env={'DATABASE_URL': conn.url}, check=False)
        finally:
            session.forget(ctx.project.name, SERVER_PORT)


def serve_spa(ctx, target: str = '', preferred_port: int = 5173) -> None:
    """Arranca `npm run dev` de una SPA, apuntandola al backend de esta sesion."""
    spa = targets.find(ctx.root, targets.SPA_VITE, target) if target \
        else targets.only(ctx.root, targets.SPA_VITE)
    puerto = ports.resolve_port(preferred_port, label=f'puerto de {spa.name}')

    entorno = {'VITE_SERVER_URL': backend_url(ctx)} if session.read(ctx.project.name, SERVER_PORT) \
        else {}
    if not entorno:
        ctx.warn('El backend no esta corriendo: la SPA va a usar su propia configuracion.')

    ctx.info(f'{spa.name} en http://localhost:{puerto}')
    ctx.run([*toolchain.npm_cmd(), 'run', 'dev', '--', '--port', str(puerto)],
            cwd=spa.path, env=entorno or None, check=False)


def run_mobile(ctx, target: str = '', device: str = '') -> None:
    """Corre la app movil en el emulador activo, con el framework que detecte.

    Si no hay emulador vivo lo dice y no intenta arrancar contra el escritorio:
    ese era el modo mas facil de perder diez minutos con `flutter run`.
    """
    app = targets.find(ctx.root, targets.FLUTTER_APP, target) if target \
        else targets.only(ctx.root, targets.FLUTTER_APP)
    kind = toolchain.detect_app_kind(app.path)

    serial = device or toolchain.pick_emulator(toolchain.devices(ctx, app.path))
    if not serial:
        raise TaskError('No hay ningun emulador Android corriendo. Arranca uno primero.')

    api = ctx.config.get('API_URL') or backend_url(ctx)
    ctx.info(f'{kind} en {serial} contra {api}')

    if kind == toolchain.FLUTTER:
        argv = [*toolchain.flutter_cmd(), 'run', '-d', serial, f'--dart-define=API_BASE_URL={api}']
        ctx.run(argv, cwd=app.path, check=False)
    else:
        ctx.run([*toolchain.flet_cmd(), 'run', '--android'], cwd=app.path,
                env={'API_BASE_URL': api}, check=False)


def open_terminal(ctx, directory: str = 'terminal', auto_login: bool = False) -> None:
    """Arranca la app de terminal con recarga automatica al cambiar sus fuentes.

    Son dos niveles de proceso: el vigilante y su hijo. Detener la pestana mata
    los dos, de abajo hacia arriba (PLAN.md 7, caso 6).
    """
    fuente = ctx.path(directory, 'src')
    entrada = fuente / 'main.py'
    if not entrada.is_file():
        raise TaskError(f'No existe el entrypoint de la terminal: {entrada}')

    interprete = venv_python(ctx.path(directory, '.venv'))
    entorno = {'SERVER_URL': backend_url(ctx)}
    if auto_login:
        entorno['TERMINAL_DEV_AUTO_LOGIN'] = 'true'

    firma = _snapshot(fuente)
    while not ctx.cancelled:
        ctx.info('Lanzando la terminal...')
        codigo = ctx.run([str(interprete), 'main.py'], cwd=fuente, env=entorno,
                         check=False, echo=False)
        if ctx.cancelled:
            return
        nueva = _snapshot(fuente)
        if nueva == firma:
            ctx.info(f'La terminal termino con codigo {codigo}.')
            return
        firma = nueva
        ctx.info('Cambios detectados: reiniciando.')


def _snapshot(root: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in root.rglob('*.py') if p.is_file()}


def open_ssh_session(ctx) -> None:
    """Abre la sesion SSH en una terminal externa: necesita TTY real (PLAN.md 7.1)."""
    remote = ssh.resolve_remote(ctx.config)
    ctx.detach(ssh.terminal_argv(remote))
    ctx.ok(f'Sesion SSH abierta en una terminal externa: {remote.target}')


def bind_all() -> None:
    registry.bind('backend', serve_backend)
    registry.bind('serve_vite', serve_spa)
    registry.bind('run_mobile', run_mobile)
    registry.bind('terminal', open_terminal)
    registry.bind('ssh_login', open_ssh_session)
