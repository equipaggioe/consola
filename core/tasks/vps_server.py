from __future__ import annotations
from .. import canone, vps
from ..errors import TaskError
from ..registry import registry
from .vps_setup import access

"""
Grupo VPS - server.

Los dos botones que operan los servicios que ya estan en el VPS: mandarles una
accion de systemd y leerles el journal. No escriben nada en la maquina. Los dos
piden root: `sudo` pide la contraseña de la cuenta (`vps_setup.Access`).
"""


def systemd_action(ctx, action: str = 'status', service: str = vps.MAIN_SERVICE) -> int:
    """Una accion de systemd sobre uno de los servicios del VPS.

    `service` no parte el boton: start/stop/restart/status son los mismos nueve
    valores para cada unidad, y lo unico que cambia es su nombre. Un boton
    "Reiniciar coturn" al lado de este seria la misma funcion con una constante
    distinta (ADR-0023).
    """
    entrada = access(ctx)
    servicio = vps.resolve_service(canone.origin(ctx.root)[1], service)
    if vps.service_state(entrada.remote, servicio) == 'missing' and action not in ('daemon-reload',):
        raise TaskError(f'El servicio {servicio} no existe todavia en el VPS.')
    return entrada.run(ctx, vps.systemctl_command(action, servicio),
                       check=action not in ('status', 'is-active', 'is-enabled'))


def view_logs(ctx, lines: int = 200, follow: bool = True, since: str = '',
              priority: str = '', grep: str = '', service: str = vps.MAIN_SERVICE) -> int:
    """Sigue el journal del servicio con los filtros pedidos.

    Es capacidad hermana de `systemd_action`, no un valor suyo: los filtros no
    tienen sentido para start/stop (ADR-0023). El eje `service` es el mismo de
    alla: cuando coturn o Caddy no arrancan, lo que hay que leer es su journal.
    """
    servicio = vps.resolve_service(canone.origin(ctx.root)[1], service)
    comando = vps.journal_command(servicio, lines=lines, follow=follow,
                                  since=since, priority=priority, grep=grep)
    return access(ctx).run(ctx, comando, check=False)


def bind_all() -> None:
    registry.bind('systemd_action', systemd_action)
    registry.bind('view_logs', view_logs)
