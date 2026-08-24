from __future__ import annotations
from pathlib import Path

from .. import files, ssh, vps
from ..errors import TaskError
from ..registry import registry

"""
Grupo VPS - server.

`update_remote.py` eran 607 lineas en un solo archivo: clonar o actualizar el
repo, crear el venv, instalar dependencias, subir el `.env` y los certificados,
generar la migracion y reiniciar el servicio. Todo o nada: para recopiar un
certificado habia que rehacer el `git pull`, el venv y el `pip install`.

Aca cada paso es una atomica con boton propio y `update_remote` es la compuesta
que los encadena, saltando el reinicio con un aviso si el servicio todavia no
existe en vez de fallar.
"""

SECRET_FILES = ('cert.pem', 'key.pem', 'firebase-service-account.json')


def _remote(ctx) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


def _server_rel(ctx) -> str:
    return ctx.config.get('SERVER_DIR', 'server')


def _venv_path(ctx) -> str:
    return vps.remote_path(ctx.config, _server_rel(ctx), '.venv')


# --- codigo en el VPS ------------------------------------------------------

def clone_repository(ctx) -> str:
    """Clona el repo en el VPS si todavia no esta. Idempotente."""
    remote = _remote(ctx)
    destino = vps.deploy_root(ctx.config)
    if ssh.path_exists(remote, f'{destino}/.git'):
        ctx.ok(f'El repo ya esta clonado en {destino}.')
        return destino

    url = ctx.config.require('GIT_REPO_URL')
    ssh.ensure_dir(remote, destino.rsplit('/', 1)[0])
    ssh.run(ctx, remote, f'git clone {ssh.quote(url)} {ssh.quote(destino)}')
    ctx.ok(f'Repo clonado en {destino}.')
    return destino


def sync_repository(ctx, discard_changes: bool = False) -> str:
    """Actualiza el repo del VPS. Si hay cambios sin commitear, pregunta.

    El script original resolvia esto solo con constantes en la cabecera; aca la
    decision se toma cuando aparece el problema, con el detalle a la vista.
    """
    remote = _remote(ctx)
    destino = clone_repository(ctx)
    sucio = ssh.capture(remote, f'cd {ssh.quote(destino)} && git status --porcelain', check=False)

    if sucio:
        ctx.warn(f'El repo del VPS tiene cambios sin commitear:\n{sucio}')
        if not discard_changes and not ctx.confirm(
                'Descartar esos cambios y actualizar igual?', danger=True):
            raise TaskError('Actualizacion cancelada: el VPS tiene cambios sin commitear.')
        ssh.run(ctx, remote, f'cd {ssh.quote(destino)} && git reset --hard && git clean -fd')

    ssh.run(ctx, remote, f'cd {ssh.quote(destino)} && git fetch --all && '
                         'git reset --hard "@{u}"')
    revision = ssh.capture(remote, f'cd {ssh.quote(destino)} && git rev-parse --short HEAD')
    ctx.ok(f'Repo actualizado en {revision}.')
    return revision


def ensure_remote_venv(ctx) -> str:
    """Crea el virtualenv del servidor en el VPS si falta."""
    remote = _remote(ctx)
    venv = _venv_path(ctx)
    if ssh.path_exists(remote, f'{venv}/bin/python'):
        ctx.ok('El venv del VPS ya existe.')
        return venv
    ssh.run(ctx, remote, f'python3 -m venv {ssh.quote(venv)}')
    ctx.ok(f'venv creado: {venv}')
    return venv


def install_remote_deps(ctx) -> None:
    """`pip install -r requirements.txt` dentro del venv del VPS."""
    remote = _remote(ctx)
    venv = _venv_path(ctx)
    requisitos = vps.remote_path(ctx.config, _server_rel(ctx), 'requirements.txt')
    if not ssh.path_exists(remote, requisitos):
        raise TaskError(f'No existe {requisitos} en el VPS.')
    ssh.run(ctx, remote, f'{ssh.quote(venv + "/bin/pip")} install -q -r {ssh.quote(requisitos)}')
    ctx.ok('Dependencias del VPS instaladas.')


def upload_secret_files(ctx) -> list[str]:
    """Sube los archivos que nunca viajan por git: `.env`, certificados, credenciales.

    Es el paso que mas se pide suelto — "solo recopiar los certificados" — y por
    eso tiene boton propio en vez de vivir dentro de la actualizacion completa.
    """
    remote = _remote(ctx)
    server = _server_rel(ctx)
    subidos: list[str] = []

    for rel in (f'{server}/.env', *(f'{server}/certs/{n}' for n in SECRET_FILES[:2]),
                f'{server}/{SECRET_FILES[2]}'):
        local = ctx.path(rel)
        if not local.is_file():
            ctx.info(f'No existe localmente, se saltea: {rel}')
            continue
        subidos.append(ssh.upload(ctx, remote, local, vps.remote_path(ctx.config, rel),
                                  chmod='600'))

    if not subidos:
        ctx.warn('No se subio ningun archivo: no se encontro ninguno de la lista.')
    else:
        ctx.ok(f'{len(subidos)} archivo(s) subidos.')
    return subidos


def restart_service(ctx) -> str:
    """Reinicia el servicio del proyecto. Avisa y sigue si todavia no existe."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    estado = vps.service_state(remote, servicio)
    if estado == 'missing':
        ctx.warn(f'El servicio {servicio} todavia no existe: corre "Instalar servicio" primero.')
        return estado
    vps.systemctl(ctx, remote, 'restart', servicio)
    ctx.ok(f'Servicio {servicio} reiniciado.')
    return vps.service_state(remote, servicio)


# --- systemd ---------------------------------------------------------------

def write_systemd_unit(ctx, host: str = '0.0.0.0', port: int = 443) -> str:
    """Escribe el archivo `.service` en el VPS y recarga systemd. No lo arranca."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    server = _server_rel(ctx)
    python = f'{_venv_path(ctx)}/bin/python'
    app = ctx.config.get('UVICORN_APP', 'app.main:app')

    cert = vps.remote_path(ctx.config, ctx.config.get('CERT_FILE_PATH', f'{server}/certs/cert.pem'))
    key = vps.remote_path(ctx.config, ctx.config.get('KEY_FILE_PATH', f'{server}/certs/key.pem'))
    tls = f' --ssl-certfile {cert} --ssl-keyfile {key}' if ssh.path_exists(remote, cert) else ''

    unidad = vps.render_unit(
        description=f'Servidor de {servicio}',
        user=remote.user,
        working_dir=vps.remote_path(ctx.config, server),
        exec_start=f'{python} -m uvicorn {app} --host {host} --port {port}{tls}',
    )
    return vps.write_unit(ctx, remote, servicio, unidad)


def systemd_action(ctx, action: str = 'status') -> int:
    """Una accion de systemd sobre el servicio del proyecto."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    if vps.service_state(remote, servicio) == 'missing' and action not in ('daemon-reload',):
        raise TaskError(f'El servicio {servicio} no existe todavia en el VPS.')
    return vps.systemctl(ctx, remote, action, servicio, check=action not in ('status', 'is-active', 'is-enabled'))


def view_logs(ctx, lines: int = 200, follow: bool = True, since: str = '',
              priority: str = '', grep: str = '') -> int:
    """Sigue el journal del servicio con los filtros pedidos.

    Es capacidad hermana de `systemd_action`, no un valor suyo: los filtros no
    tienen sentido para start/stop (PLAN.md 1).
    """
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    comando = vps.journal_command(servicio, lines=lines, follow=follow,
                                  since=since, priority=priority, grep=grep)
    return ssh.run(ctx, remote, comando, check=False)


# --- compuestas ------------------------------------------------------------

def install_systemd(ctx, host: str = '0.0.0.0', port: int = 443, *,
                    write: bool = True, enable: bool = True, start: bool = True) -> None:
    """Compuesta: escribir la unidad y reusar `systemd_action` para habilitarla.

    No reimplementa `enable` ni `start`: llama a la misma atomica que ya tiene
    su propio boton (PLAN.md 7, caso 7).
    """
    if write:
        ctx.step('Unidad systemd')
        write_systemd_unit(ctx, host, port)
    if enable:
        ctx.step('Habilitar al arranque')
        systemd_action(ctx, 'enable')
    if start:
        ctx.step('Arrancar')
        systemd_action(ctx, 'restart')
    ctx.note(f'Servicio {vps.service_name(ctx.config)} instalado.')


def update_remote(
    ctx,
    *,
    pull: bool = True,
    venv: bool = True,
    deps: bool = True,
    upload: bool = True,
    migrate: bool = True,
    restart: bool = True,
) -> None:
    """Compuesta: actualizar codigo -> venv -> dependencias -> secretos -> migrar -> reiniciar.

    `venv` y `deps` son condicionales a proposito: si el repo no cambio, volver
    a instalar dependencias es tiempo perdido, pero a veces se pide igual tras
    tocar `requirements.txt` a mano.
    """
    from . import database as db_tasks

    if pull:
        ctx.step('Codigo')
        sync_repository(ctx)
    if venv:
        ctx.step('Entorno virtual')
        ensure_remote_venv(ctx)
    if deps:
        ctx.step('Dependencias')
        install_remote_deps(ctx)
    if upload:
        ctx.step('Archivos que no viajan por git')
        upload_secret_files(ctx)
    if migrate:
        ctx.step('Migraciones')
        db_tasks.migrate_db(ctx, scope='remoto', message='auto')
    if restart:
        ctx.step('Servicio')
        restart_service(ctx)
    ctx.note('Actualizacion del remoto completada.')


def bind_all() -> None:
    registry.bind('systemd_action', systemd_action)
    registry.bind('view_logs', view_logs)
    registry.bind('install_systemd', install_systemd)
    registry.bind('update_remote', update_remote)
