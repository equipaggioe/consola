"""VPS group: server.

The two buttons that operate the services already on the VPS: send them
a systemd action and read their journal. They write nothing on the
machine. Both need root: `sudo` asks for the account's password
(`vps_setup.Access`).
"""

from __future__ import annotations

from app.core import canone, vps
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.registry import registry
from app.core.tasks.vps_setup import access


def systemd_action(
    ctx: TaskContext, action: str = "status", service: str = vps.MAIN_SERVICE
) -> int:
    """Run a systemd action on one of the VPS services.

    `service` does not split the button: start, stop, restart and status
    are the same values for each unit, and only its name changes. A
    «Restart coturn» button next to this one would be the same function
    with another constant (ADR-0023).
    """
    if service == vps.RECEIVER_SERVICE and action in vps.STARTING_ACTIONS:
        raise TaskError("El respaldo lo pide la receptora: no se arranca desde aquí.")
    entry = access(ctx)
    unit = vps.resolve_service(canone.origin(ctx.root)[1], service)
    if vps.service_state(entry.remote, unit) == "missing" and action not in ("daemon-reload",):
        raise TaskError(f"El servicio {unit} no existe todavia en el VPS.")
    return entry.run(
        ctx,
        vps.systemctl_command(action, unit),
        check=action not in ("status", "is-active", "is-enabled"),
    )


def view_logs(
    ctx: TaskContext,
    lines: int = 200,
    follow: bool = True,
    since: str = "",
    priority: str = "",
    grep: str = "",
    service: str = vps.MAIN_SERVICE,
) -> int:
    """Follow the service's journal with the requested filters.

    It is a sibling capability of `systemd_action`, not a value of it:
    filters make no sense for start or stop (ADR-0023). The `service`
    axis is the same: when coturn, Caddy or a piece in Java do not
    start, their journal is what has to be read.
    """
    unit = vps.resolve_service(canone.origin(ctx.root)[1], service)
    command = vps.journal_command(
        unit, lines=lines, follow=follow, since=since, priority=priority, grep=grep
    )
    return access(ctx).run(ctx, command, check=False)


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("systemd_action", systemd_action)
    registry.bind("view_logs", view_logs)
