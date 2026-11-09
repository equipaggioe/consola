"""VPS group, setup: leave a VPS ready with canone's programs.

ADR-0059.

The machine reaches `install.py` with its packages, uv and as much swap
as memory (despliegue.md of canone, «Máquina»). canone's `packages.py`
and `uv.py` install the first two; the swap is left to whoever prepares
the machine, which is Consola. Then `install.py` installs the
app, creates the admin account and allows entry only by key, and
`credentials.py` encrypts the credentials.

The first time root enters with the `VPS_KEY_NAME` key, set when
creating the VPS. After `install.py` root no longer enters, and
everything goes through the `VPS_USER` account with `sudo`, which asks
for its password.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import canone, session, ssh
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.registry import registry

# Where canone's programs are uploaded. Deleted at the end.
REMOTE_DIR = "/tmp/consola-canone"
SUDO_KEY = "SUDO_PASSWORD"


@dataclass(frozen=True)
class Access:
    """How to enter the VPS: root, or the admin account with sudo."""

    remote: ssh.Remote
    password: str = ""

    @property
    def is_root(self) -> bool:
        """Return whether it entered as root."""
        return not self.password

    def command(self, command: str) -> str:
        """Return `command` as root.

        As is if root, with `sudo -S` if not.
        """
        if self.is_root:
            return command
        return f"sudo -S -p '' bash -c {ssh.quote(command)}"

    def stdin(self, text: str = "") -> str | None:
        """Return the command's input: the sudo password first."""
        if self.is_root:
            return text or None
        return f"{self.password}\n{text}"

    def run(self, ctx: TaskContext, command: str, *, text: str = "", check: bool = True) -> int:
        """Run a command as root on the VPS."""
        return ssh.run(
            ctx, self.remote, self.command(command), check=check, stdin_text=self.stdin(text)
        )


def _sudo_password(ctx: TaskContext) -> str:
    """Return `SUDO_PASSWORD`, or the one asked once per session.

    It lives only in memory, and goes to `core/session.py` directly and
    not through `ctx.publish`, which would forget it when the run ends.
    """
    written = ctx.config.get(SUDO_KEY) or session.read(ctx.project_name, SUDO_KEY)
    if not written:
        user = ctx.config.require("VPS_USER")
        written = ctx.ask(f"Contraseña de {user} (la de sudo)", secret=True)
        if not written:
            raise TaskError("Sin la contraseña de sudo no se puede administrar el VPS.")
        session.publish(ctx.project_name, SUDO_KEY, written)
    ctx.guard(written)
    return written


def access(ctx: TaskContext) -> Access:
    """Enter through the admin account if it exists, or through root.

    Root enters only before `install.py`, which then leaves it out.
    Without either there is no way forward.
    """
    admin = ssh.resolve_remote(ctx.config)
    if ssh.reachable(admin):
        return Access(admin, _sudo_password(ctx))
    root = admin.as_user(ctx.config.get("ROOT_USER"))
    if ssh.reachable(root):
        ctx.info(f"{admin.target} todavía no entra: se usa {root.target}.")
        return Access(root)
    raise TaskError(
        f"No se entra al VPS ni como {admin.target} ni como {root.target} "
        f"con la llave {ctx.config.get('VPS_KEY_NAME')}."
    )


def admin(ctx: TaskContext) -> Access:
    """Enter through the admin account: what `install.py` leaves.

    canone's programs run from it with `sudo`, and root no longer
    enters.
    """
    entry = access(ctx)
    if entry.is_root:
        raise TaskError(
            "La cuenta que administra todavía no existe: corre «Configurar VPS» "
            "con «Instalar infraestructura» primero."
        )
    return entry


def _upload(ctx: TaskContext, entry: Access) -> str:
    """Upload canone's `plantilla/infra/` and return the temp folder."""
    infra = canone.infra_dir(ctx.config)
    entry.run(ctx, f"rm -rf {REMOTE_DIR}")
    return ssh.upload(ctx, entry.remote, infra, f"{REMOTE_DIR}/{infra.name}")


def _cleanup(ctx: TaskContext, entry: Access) -> None:
    entry.run(ctx, f"rm -rf {REMOTE_DIR}", check=False)


# --- atomic ---


def refresh_known_host(ctx: TaskContext) -> str:
    """Forget the VPS's old fingerprint.

    After reinstalling the server its fingerprint changes, and all
    connections fail with a «host key verification» error that does not
    say how to fix it. The first connection of any other atomic
    capability records the new one.
    """
    host = ctx.config.require("VPS_IP")
    ssh.forget_host(ctx, host)
    return host


def install_software(ctx: TaskContext) -> list[str]:
    """Run canone's `packages.py`, and then `uv.py`.

    The packages come from canone, not from here: `packages.py` gets the
    options of `install.py` that add one, from `config.env`
    (`canone.package_args`, ADR-0131 of canone). It runs with the
    machine's `python3`: an image without it gets it from apt first.
    `uv.py` installs the uv version canone fixes (ADR-0110 of canone):
    it runs again when canone changes it.
    """
    entry = access(ctx)
    packages = canone.packages(ctx.config)
    ctx.info(f"Paquetes de canone para este repo: {', '.join(packages)}")
    destination = _upload(ctx, entry)
    options = " ".join(ssh.quote(a) for a in canone.package_args(ctx.config))
    try:
        entry.run(
            ctx,
            "command -v python3 >/dev/null || { apt-get update -qq && "
            "DEBIAN_FRONTEND=noninteractive apt-get install -y python3; }",
        )
        entry.run(ctx, f"python3 {destination}/packages.py {options}".rstrip())
        entry.run(ctx, f"python3 {destination}/uv.py")
    finally:
        _cleanup(ctx, entry)
    ctx.ok(f"Paquetes y uv listos: {', '.join(packages)}")
    return packages


# Create `/swapfile` with what is missing to have as much swap as
# memory, which `install.py` asks for. If a `/swapfile` that falls short
# exists, it remakes it.
_SWAP = r"""set -e
mem=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
swap=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
[ "$swap" -ge "$mem" ] && { echo "[OK] Ya hay tanto swap como memoria."; exit 0; }
if swapon --show=NAME --noheadings | grep -qx /swapfile; then swapoff /swapfile; fi
rm -f /swapfile
swap=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
falta=$(( (mem - swap) / 1024 + 1 ))
fallocate -l "${falta}M" /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo "[OK] Swap de ${falta} MiB en /swapfile."
"""


def create_swap(ctx: TaskContext) -> None:
    """Leave as much swap as memory: `install.py` fails without it."""
    access(ctx).run(ctx, _SWAP)


def install_infra(ctx: TaskContext) -> None:
    """Upload canone's `plantilla/infra/` and run `install.py`.

    The first time it runs as root, and `install.py` asks twice for the
    new account's password: it is written into an `ssh -tt` only as each
    question appears, because written earlier the remote terminal echoes
    it in the log (`ctx.converse`). Later it runs with `sudo` from that
    account, and keys it already has are not added again.
    """
    owner, app = canone.origin(ctx.root)
    key = ssh.public_key(
        ssh.ensure_local_keypair(ctx, ctx.config.require("VPS_KEY_NAME"), comment=app)
    )
    outside = ctx.config.require("OFFLINE_KEY").strip()
    if outside.split()[:2] == key.split()[:2]:
        raise TaskError(
            "OFFLINE_KEY es la misma llave que VPS_KEY_NAME: hace falta otra, "
            "guardada fuera de esta máquina."
        )
    arguments = canone.install_args(ctx.root, ctx.config, app, owner, (key, outside))
    entry = access(ctx)
    destination = _upload(ctx, entry)
    command = " ".join(ssh.quote(a) for a in ("python3", f"{destination}/install.py", *arguments))
    try:
        if entry.is_root:
            password = _sudo_password(ctx)
            ctx.converse(
                entry.remote.argv(command, tty=True, extra=["-t"]),
                [("Password of", password), ("Again", password)],
            )
        else:
            entry.run(ctx, command)
    finally:
        # `install.py` leaves root without entry: the remaining account
        # cleans up.
        _cleanup(ctx, access(ctx))
    ctx.ok(f"{app} instalado en {entry.remote.host}.")


def load_credentials(ctx: TaskContext) -> None:
    """Pass the `config.env` credentials to `credentials.py`, by stdin.

    One `field=value` line per `Settings` field, plus `restic_password`
    and, in a private repo, `github_token` (ADR-0063). It stops before
    sending if one is missing or if `config.env` has a key in no source.
    `install.py` does not install `credentials.py`, so it uploads each
    time.
    """
    _, app = canone.origin(ctx.root)
    lines = canone.credential_lines(ctx.root, ctx.config)
    for line in lines.splitlines():
        ctx.guard(line.partition("=")[2])
    entry = admin(ctx)
    destination = _upload(ctx, entry)
    try:
        entry.run(ctx, f"python3 {destination}/credentials.py {ssh.quote(app)}", text=lines)
    finally:
        _cleanup(ctx, entry)
    ctx.ok(f"{len(lines.splitlines())} credenciales cargadas.")


# --- composite ---


def bootstrap_vps(
    ctx: TaskContext,
    *,
    known_host: bool = False,
    software: bool = True,
    swap: bool = True,
    infra: bool = True,
    credentials: bool = True,
    deploy: bool = True,
) -> None:
    """Run packages and uv, swap, `install.py`, credentials, release.

    Each step detects what is there, so the composite can run again:
    that is what adding an installable or going private needs, since
    they ask to reinstall (ADR-0106 of canone). The deployment does not:
    `deploy.py` does not install a version already on the VPS.
    """
    # Circular: `vps_release` enters the VPS with `access`, from this
    # module.
    from app.core.tasks.vps_release import deploy_latest

    if known_host:
        ctx.step("known_host")
        refresh_known_host(ctx)
    if software:
        ctx.step("software")
        install_software(ctx)
    if swap:
        ctx.step("swap")
        create_swap(ctx)
    if infra:
        ctx.step("infra")
        install_infra(ctx)
    if credentials:
        ctx.step("credentials")
        load_credentials(ctx)
    if deploy:
        ctx.step("deploy")
        deploy_latest(ctx)
    ctx.note(f"VPS {ctx.config.require('VPS_IP')} configurado.")


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("refresh_known_host", refresh_known_host)
    registry.bind("install_software", install_software)
    registry.bind("load_credentials", load_credentials)
    registry.bind("bootstrap_vps", bootstrap_vps)
