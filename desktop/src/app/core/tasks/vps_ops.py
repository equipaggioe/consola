"""VPS group: ops.

Diagnostics, a loose command and removing this machine's key. None of
them writes the VPS configuration.
"""

from __future__ import annotations

import json

from app.core import canone, ssh, vps
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.registry import registry
from app.core.tasks.vps_setup import access


def _remote(ctx: TaskContext) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


# --- diagnostics ---

# What a healthy server answers (fastapi.md of canone, «Salud»).
HEALTHY = "204"
HEALTH_TOKEN = "HEALTH_TOKEN"


def health_check(ctx: TaskContext) -> dict[str, str]:
    """Show VPS health, recent server errors and `GET /api/health`.

    `access` stops if it cannot get in: the rest already knows there is
    a machine. It fails at the end, not as soon as the API does not
    answer, because the summary and the errors are what has to be read
    to know why.
    """
    entry = access(ctx)
    service = vps.resolve_service(canone.origin(ctx.root)[1])
    summary = vps.health(entry.remote, service)
    for key, value in summary.items():
        ctx.info(f"{key}: {value or '(sin datos)'}")
    entry.run(ctx, vps.journal_command(service, lines=10, priority="err"))
    if summary["api"] != HEALTHY:
        raise TaskError(f"GET /api/health respondió {summary['api'] or 'nada'}, no {HEALTHY}.")
    return summary


def view_events(ctx: TaskContext) -> dict[str, str]:
    """Show `GET /api/health/events`: events, last backup and disk.

    It only shows them: canone lets whoever asks decide when to alert.
    """
    token = ctx.config.require(HEALTH_TOKEN)
    ctx.guard(token)
    state, body = vps.server_get(_remote(ctx), "/api/health/events", token)
    if state != "200":
        raise TaskError(f"GET /api/health/events respondió {state or 'nada'}.")
    summary = canone.events_summary(json.loads(body))
    for key, value in summary.items():
        ctx.info(f"{key}: {value}")
    return summary


def run_command(ctx: TaskContext, command: str = "") -> int:
    """Run any command on the VPS, with live output."""
    if not command.strip():
        raise TaskError("No hay ningun comando para correr.")
    return ssh.run(ctx, _remote(ctx), command, check=False)


# --- revocation ---


def revoke_ssh_key(ctx: TaskContext, *, remote_side: bool = True, local_side: bool = True) -> None:
    """Remove the key from the VPS and delete the local pair.

    It shows the exact fingerprint it will remove before touching
    anything: revoking the wrong key leaves the server unreachable.
    """
    key_name = ctx.config.require("VPS_KEY_NAME")
    private = ssh.identity_path(key_name)
    if not private.is_file():
        raise TaskError(f"No existe la llave local: {private}")
    publishes = ssh.public_key(private)

    ctx.warn(f"Se va a revocar: {publishes[:60]}...")
    if remote_side:
        key = ssh.quote(publishes)
        try:
            # The first grep fails if the key is not there; the second,
            # if it is the last one.
            ssh.run(
                ctx,
                _remote(ctx),
                (
                    "auth=~/.ssh/authorized_keys; "
                    f'grep -qxF -- {key} "$auth" && '
                    f'grep -vxF -- {key} "$auth" > "$auth.tmp" && mv "$auth.tmp" "$auth"'
                ),
            )
        except TaskError as exc:
            raise TaskError(
                "No se sacó la llave del VPS: no se pudo entrar, no está en "
                "authorized_keys o es la última. La llave local sigue ahí."
            ) from exc
        ctx.ok("Llave sacada del VPS.")

    if local_side:
        from app.core import files

        files.remove(private)
        files.remove(ssh.public_key_path(private))
        ctx.ok(f"Par de llaves local borrado: {private}")


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("health_check", health_check)
    registry.bind("view_events", view_events)
    registry.bind("run_command", run_command)
    registry.bind("revoke_ssh", revoke_ssh_key)
