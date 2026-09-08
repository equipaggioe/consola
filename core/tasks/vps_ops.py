from __future__ import annotations

from .. import github, ssh, vps
from ..errors import TaskError
from ..registry import registry

"""
Grupo VPS - ops.

`clean_vps.py` ya tenia sus seis pasos declarados como un diccionario `STEPS`,
pero eran funciones internas del archivo: no habia forma de correr solo una.
Aca las seis son atomicas de verdad — `remove_systemd_service` sirve suelta
cuando se renombra un servicio, `remove_deployed_repo` cuando se cambia de rama
de despliegue — y `clean_vps` sigue siendo el boton que las corre todas, porque
"dejar el VPS como recien formateado" casi siempre se pide entero.
"""

PACKAGES_TO_REMOVE = ('postgresql', 'postgresql-contrib', 'postgis',
                      'postgresql-postgis-scripts', 'caddy', 'coturn')


def _remote(ctx) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


# --- diagnostico -----------------------------------------------------------

def health_check(ctx) -> dict[str, str]:
    """Resumen de salud del VPS: servicio, disco, memoria, carga y errores recientes."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    resumen = vps.health(remote, servicio)
    resumen['carga'] = ssh.capture(remote, "uptime | sed 's/.*load average: //'", check=False)
    resumen['errores'] = ssh.capture(
        remote, f'sudo -n journalctl -u {ssh.quote(servicio)} -p err -n 10 --no-pager', check=False)

    for clave, valor in resumen.items():
        ctx.info(f'{clave}: {valor or "(sin datos)"}')
    return resumen


def run_command(ctx, command: str = '') -> int:
    """Un comando cualquiera en el VPS, con la salida en vivo."""
    if not command.strip():
        raise TaskError('No hay ningun comando para correr.')
    return ssh.run(ctx, _remote(ctx), command, check=False)


def run_setup_scripts(ctx, scope: str = 'remoto', *, bootstrap: bool = True,
                      rebuild: bool = False) -> None:
    """Corre las capacidades de preparacion contra el ambito elegido.

    `SETUP_SCRIPTS` era una lista de rutas a `.py` en el `.env`. Ya no hace
    falta: los pasos son capacidades del catalogo y el ambito es un eje.
    """
    from . import database as db_tasks

    if bootstrap:
        ctx.step('bootstrap')
        db_tasks.bootstrap_db(ctx.child('bootstrap_db'), scope)
    if rebuild:
        ctx.step('rebuild')
        db_tasks.rebuild_db(ctx.child('rebuild_db'), scope)


# --- revocacion ------------------------------------------------------------

def revoke_ssh_key(ctx, *, remote_side: bool = True, local_side: bool = True) -> None:
    """Saca la llave del `authorized_keys` del VPS y borra el par local.

    Muestra la huella exacta que va a sacar antes de tocar nada: revocar la
    llave equivocada deja el servidor inalcanzable.
    """
    key_name = ctx.config.require('VPS_KEY_NAME')
    privada = ssh.identity_path(key_name)
    if not privada.is_file():
        raise TaskError(f'No existe la llave local: {privada}')
    publica = ssh.public_key(privada)

    ctx.warn(f'Se va a revocar: {publica[:60]}...')
    if not ctx.confirm(f'Escribe {key_name} para revocar la llave.', danger=True, expect=key_name):
        ctx.warn('Cancelado: no se revoco nada.')
        return

    if remote_side:
        remote = _remote(ctx)
        ssh.run(ctx, remote, (
            'auth=~/.ssh/authorized_keys; '
            f'grep -vxF -- {ssh.quote(publica)} "$auth" > "$auth.tmp" && mv "$auth.tmp" "$auth"'
        ), check=False)
        ctx.ok('Llave sacada del VPS.')

    if local_side:
        from .. import files
        files.remove(privada)
        files.remove(ssh.public_key_path(privada))
        ctx.ok(f'Par de llaves local borrado: {privada}')


def remove_remote_key_files(ctx) -> None:
    """Borra la llave SSH que el VPS usa contra GitHub."""
    ssh.run(ctx, _remote(ctx), 'rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub', check=False)
    ctx.ok('Llave de GitHub borrada del VPS.')


def revoke_github_key(ctx) -> bool:
    """Borra la llave del VPS de la cuenta de GitHub, por titulo."""
    token = ctx.config.require('GITHUB_TOKEN')
    ctx.guard(token)
    return github.revoke_key(ctx, token, title=ctx.config.require('GITHUB_KEY_TITLE'))


def revoke_github_ssh(ctx, *, remote_files: bool = True, github_side: bool = True) -> None:
    """Compuesta: borrar la llave del VPS y darla de baja en GitHub."""
    if remote_files:
        ctx.step('remote_files')
        remove_remote_key_files(ctx)
    if github_side:
        ctx.step('github_side')
        revoke_github_key(ctx)


# --- limpieza del VPS ------------------------------------------------------

def remove_systemd_service(ctx) -> bool:
    """Para, deshabilita y borra la unidad del servicio. Detecta antes de actuar."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    if vps.service_state(remote, servicio) == 'missing':
        ctx.info(f'No hay servicio {servicio} para borrar.')
        return False

    vps.systemctl(ctx, remote, 'stop', servicio, check=False)
    vps.systemctl(ctx, remote, 'disable', servicio, check=False)
    ssh.run(ctx, remote, f'sudo -n rm -f {ssh.quote(vps.unit_path(servicio))} && '
                         'sudo -n systemctl daemon-reload')
    ctx.ok(f'Servicio {servicio} eliminado.')
    return True


def remove_deployed_repo(ctx) -> bool:
    """Borra la copia del repo en el VPS."""
    remote = _remote(ctx)
    destino = vps.deploy_root(ctx.config)
    if not ssh.path_exists(remote, destino):
        ctx.info(f'No hay nada en {destino}.')
        return False
    ssh.run(ctx, remote, f'rm -rf {ssh.quote(destino)}')
    ctx.ok(f'Repo borrado del VPS: {destino}')
    return True


def uninstall_packages(ctx, packages: list[str] | None = None) -> list[str]:
    """Desinstala los paquetes que instalo el aprovisionamiento."""
    remote = _remote(ctx)
    objetivo = list(packages or PACKAGES_TO_REMOVE)
    presentes = [p for p in objetivo if ssh.succeeds(remote, f'dpkg -s {ssh.quote(p)}')]
    if not presentes:
        ctx.info('No hay paquetes de la lista instalados.')
        return []

    ctx.warn(f'Se van a desinstalar: {", ".join(presentes)}')
    lista = ' '.join(ssh.quote(p) for p in presentes)
    ssh.run(ctx, remote, f'sudo -n DEBIAN_FRONTEND=noninteractive apt-get purge -y {lista}')
    ssh.run(ctx, remote, 'sudo -n apt-get autoremove -y', check=False)
    return presentes


def remove_vps_user(ctx) -> bool:
    """Borra el usuario de despliegue y su home. Se corre como root."""
    from .vps_setup import _root_run

    user = ctx.config.get('VPS_USER')
    _root_run(ctx, (
        f'if id -u {ssh.quote(user)} >/dev/null 2>&1; then '
        f'  pkill -u {ssh.quote(user)} || true; '
        f'  userdel -r {ssh.quote(user)} && echo "[OK] Usuario eliminado."; '
        'else echo "[INFO] El usuario no existe."; fi; '
        f'rm -f /etc/sudoers.d/consola-{user}'
    ), check=False)
    return True


def clean_vps(
    ctx,
    *,
    service: bool = True,
    database: bool = True,
    repo: bool = True,
    github_key: bool = True,
    packages: bool = True,
    user: bool = True,
) -> None:
    """Compuesta destructiva: dejar el VPS como recien formateado.

    Los seis pasos son casillas del formulario, no botones sueltos del rail:
    esta operacion casi siempre se pide entera (PLAN.md 7, caso 7).
    """
    from . import database as db_tasks

    host = ctx.config.require('VPS_IP')
    if not ctx.confirm(f'Escribe {host} para BORRAR todo lo instalado en ese servidor.',
                       danger=True, expect=host):
        ctx.warn('Cancelado: no se toco el VPS.')
        return

    if service:
        ctx.step('service')
        remove_systemd_service(ctx)
    if database:
        ctx.step('database')
        db_tasks.teardown_db(ctx.child('teardown_db'), scope='remoto')
    if repo:
        ctx.step('repo')
        remove_deployed_repo(ctx)
    if github_key:
        ctx.step('github_key')
        revoke_github_ssh(ctx)
    if packages:
        ctx.step('packages')
        uninstall_packages(ctx)
    if user:
        ctx.step('user')
        remove_vps_user(ctx)
    ctx.note(f'Limpieza completa del VPS {host}.')


def bind_all() -> None:
    registry.bind('health_check', health_check)
    registry.bind('run_command', run_command)
    registry.bind('run_setup_scripts', run_setup_scripts)
    registry.bind('revoke_ssh', revoke_ssh_key)
    registry.bind('revoke_github_ssh', revoke_github_ssh)
    registry.bind('clean_vps', clean_vps)
