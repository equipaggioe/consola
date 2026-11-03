from __future__ import annotations

import json

from app.core import canone, ssh, vps
from app.core.errors import TaskError
from app.core.registry import registry
from app.core.tasks.vps_setup import access

"""
Grupo VPS - ops: diagnostico, un comando suelto y quitar la llave de esta
maquina. Ninguno escribe la configuracion del VPS.
"""


def _remote(ctx) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


# --- diagnostico -----------------------------------------------------------

# Lo que responde un servidor sano (fastapi.md de canone, «Salud»).
HEALTHY = '204'
HEALTH_TOKEN = 'HEALTH_TOKEN'


def health_check(ctx) -> dict[str, str]:
    """Resumen de salud del VPS, los errores recientes del servidor y `GET /api/health`.

    `access` corta si no se entra: lo demas ya sabe que hay maquina. Falla al
    final, y no en cuanto la API no contesta, porque el resumen y los errores son
    justo lo que hace falta leer para saber por que.
    """
    entrada = access(ctx)
    servicio = vps.resolve_service(canone.origin(ctx.root)[1])
    resumen = vps.health(entrada.remote, servicio)
    for clave, valor in resumen.items():
        ctx.info(f'{clave}: {valor or "(sin datos)"}')
    entrada.run(ctx, vps.journal_command(servicio, lines=10, priority='err'))
    if resumen['api'] != HEALTHY:
        raise TaskError(f'GET /api/health respondió {resumen["api"] or "nada"}, no {HEALTHY}.')
    return resumen


def view_events(ctx) -> dict[str, str]:
    """`GET /api/health/events`: los ultimos eventos, el ultimo respaldo y el disco.

    Solo los muestra: canone deja a quien consulta decidir cuando avisar.
    """
    token = ctx.config.require(HEALTH_TOKEN)
    ctx.guard(token)
    estado, cuerpo = vps.server_get(_remote(ctx), '/api/health/events', token)
    if estado != '200':
        raise TaskError(f'GET /api/health/events respondió {estado or "nada"}.')
    resumen = canone.events_summary(json.loads(cuerpo))
    for clave, valor in resumen.items():
        ctx.info(f'{clave}: {valor}')
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
        clave = ssh.quote(publica)
        try:
            # The first grep fails if the key is not there; the second, if it is the last one.
            ssh.run(ctx, _remote(ctx), (
                'auth=~/.ssh/authorized_keys; '
                f'grep -qxF -- {clave} "$auth" && '
                f'grep -vxF -- {clave} "$auth" > "$auth.tmp" && mv "$auth.tmp" "$auth"'
            ))
        except TaskError as exc:
            raise TaskError('No se sacó la llave del VPS: no se pudo entrar, no está en '
                            'authorized_keys o es la última. La llave local sigue ahí.') from exc
        ctx.ok('Llave sacada del VPS.')

    if local_side:
        from app.core import files
        files.remove(privada)
        files.remove(ssh.public_key_path(privada))
        ctx.ok(f'Par de llaves local borrado: {privada}')


def bind_all() -> None:
    registry.bind('health_check', health_check)
    registry.bind('view_events', view_events)
    registry.bind('run_command', run_command)
    registry.bind('revoke_ssh', revoke_ssh_key)
