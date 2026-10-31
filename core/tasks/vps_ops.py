from __future__ import annotations

from .. import ssh, vps
from ..errors import TaskError
from ..registry import registry

"""
Grupo VPS - ops: diagnostico, un comando suelto y quitar la llave de esta
maquina. Ninguno escribe la configuracion del VPS.
"""


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


def bind_all() -> None:
    registry.bind('health_check', health_check)
    registry.bind('run_command', run_command)
    registry.bind('revoke_ssh', revoke_ssh_key)
