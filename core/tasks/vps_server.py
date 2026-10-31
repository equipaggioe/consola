from __future__ import annotations
from .. import ssh, vps
from ..errors import TaskError
from ..registry import registry

"""
Grupo VPS - server.

Los dos botones que operan los servicios que ya estan en el VPS: mandarles una
accion de systemd y leerles el journal. No escriben nada en la maquina.
"""

def _remote(ctx) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


def systemd_action(ctx, action: str = 'status', service: str = 'proyecto') -> int:
    """Una accion de systemd sobre uno de los servicios del VPS.

    `service` no parte el boton en tres: start/stop/restart/status son los
    mismos nueve valores para el servicio del proyecto, para coturn y para
    Caddy, y lo unico que cambia es el nombre de la unidad. Un boton "Reiniciar
    coturn" al lado de este seria la misma funcion con una constante distinta
    (ADR-0023).
    """
    remote = _remote(ctx)
    servicio = vps.resolve_service(ctx.config, service)
    if vps.service_state(remote, servicio) == 'missing' and action not in ('daemon-reload',):
        raise TaskError(f'El servicio {servicio} no existe todavia en el VPS.')
    return vps.systemctl(ctx, remote, action, servicio, check=action not in ('status', 'is-active', 'is-enabled'))


def view_logs(ctx, lines: int = 200, follow: bool = True, since: str = '',
              priority: str = '', grep: str = '', service: str = 'proyecto') -> int:
    """Sigue el journal del servicio con los filtros pedidos.

    Es capacidad hermana de `systemd_action`, no un valor suyo: los filtros no
    tienen sentido para start/stop (ADR-0023). El eje `service` es el mismo de
    alla: cuando coturn o Caddy no arrancan, lo que hay que leer es su journal.
    """
    remote = _remote(ctx)
    servicio = vps.resolve_service(ctx.config, service)
    comando = vps.journal_command(servicio, lines=lines, follow=follow,
                                  since=since, priority=priority, grep=grep)
    return ssh.run(ctx, remote, comando, check=False)


def bind_all() -> None:
    registry.bind('systemd_action', systemd_action)
    registry.bind('view_logs', view_logs)
