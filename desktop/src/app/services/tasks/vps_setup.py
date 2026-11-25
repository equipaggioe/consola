"""VPS group, setup: leave a VPS ready with canone's programs.

ADR-0059.

The machine reaches `install.py` with its packages, uv and as much swap
as memory (despliegue.md of canone, «Máquina»): canone's `packages.py`,
`uv.py` and `swap.py` leave them, and Consola runs them. Then
`install.py` installs the app, creates the admin account and allows
entry only by key, and `credentials.py` encrypts the credentials.

The first time root enters with the `VPS_KEY_NAME` key, which the
provider's panel set or `install_key` added with root's password. After
`install.py` root no longer enters, and everything goes through the
`VPS_USER` account with `sudo`, which asks for its password.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.services import canone, envfile, fields, session, ssh
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.registry import registry
from app.services.settings import names

# Where canone's programs are uploaded. Deleted at the end.
REMOTE_DIR = "/tmp/consola-canone"
SUDO_KEY = "SUDO_PASSWORD"
ROOT_PASSWORD_KEY = "ROOT_PASSWORD"
AUTHORIZE = "authorize.py"
# canone's programs run with it, and an image may come without it.
PYTHON = (
    "command -v python3 >/dev/null || { apt-get update -qq && "
    "DEBIAN_FRONTEND=noninteractive apt-get install -y python3; }"
)


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

    def capture(self, command: str) -> str:
        """Return what a command prints as root on the VPS."""
        return ssh.capture(self.remote, self.command(command), stdin_text=self.stdin())

    def run(self, ctx: TaskContext, command: str, *, text: str = "", check: bool = True) -> int:
        """Run a command as root on the VPS."""
        return ssh.run(
            ctx, self.remote, self.command(command), check=check, stdin_text=self.stdin(text)
        )


def _sudo_password(ctx: TaskContext) -> str:
    """Return `SUDO_PASSWORD`, or the one asked once per session.

    It lives only in memory, and goes to `services/session.py` directly
    and not through `ctx.publish`, which would forget it when the run
    ends.
    """
    written = ctx.config.get(SUDO_KEY) or session.read(ctx.project_name, SUDO_KEY)
    if not written:
        user = ctx.config.require("VPS_USER")
        written = ctx.ask(
            QCoreApplication.translate("vps_setup", "Contraseña de {0} (la de sudo)").format(user),
            secret=True,
        )
        if not written:
            raise TaskError(
                QCoreApplication.translate(
                    "vps_setup", "Sin la contraseña de sudo no se puede administrar el VPS."
                )
            )
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
        ctx.info(
            QCoreApplication.translate("vps_setup", "{0} todavía no entra: se usa {1}.").format(
                admin.target, root.target
            )
        )
        return Access(root)
    raise TaskError(
        QCoreApplication.translate(
            "vps_setup", "No se entra al VPS ni como {0} ni como {1} con la llave {2}."
        ).format(admin.target, root.target, ctx.config.get("VPS_KEY_NAME"))
    )


def admin(ctx: TaskContext) -> Access:
    """Enter through the admin account: what `install.py` leaves.

    canone's programs run from it with `sudo`, and root no longer
    enters.
    """
    entry = access(ctx)
    if entry.is_root:
        raise TaskError(
            QCoreApplication.translate(
                "vps_setup",
                "La cuenta que administra todavía no existe: corre «Configurar VPS» con "
                "«Instalar infraestructura» primero.",
            )
        )
    return entry


def _upload(ctx: TaskContext, entry: Access) -> str:
    """Upload canone's `plantilla/infra/` and return the temp folder."""
    infra = canone.infra_dir(ctx.config)
    entry.run(ctx, f"rm -rf {REMOTE_DIR}")
    return ssh.upload(ctx, entry.remote, infra, f"{REMOTE_DIR}/{infra.name}")


def _cleanup(ctx: TaskContext, entry: Access) -> None:
    entry.run(ctx, f"rm -rf {REMOTE_DIR}", check=False)


def _ensure_python(ctx: TaskContext, entry: Access) -> None:
    """Install `python3` with apt if the machine lacks it.

    canone's programs run with it, `packages.py` and `swap.py` among
    them, and an image may come without it.
    """
    entry.run(ctx, PYTHON)


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


def install_key(ctx: TaskContext) -> None:
    """Create the local key, and leave it in root's `authorized_keys`.

    A new VPS may take only root's password, the one of the provider:
    it enters with it once, from `ROOT_PASSWORD` or asked, and canone's
    `authorize.py` adds the key. Then every step enters with the key.
    If the key already enters, as root or as the admin account, it does
    nothing.
    """
    _, app = canone.origin(ctx.root)
    private = ssh.ensure_local_keypair(ctx, ctx.config.require("VPS_KEY_NAME"), comment=app)
    admin_remote = ssh.resolve_remote(ctx.config)
    root = admin_remote.as_user(ctx.config.get("ROOT_USER"))
    if ssh.reachable(admin_remote) or ssh.reachable(root):
        ctx.ok(QCoreApplication.translate("vps_setup", "La llave ya entra al VPS."))
        return
    password = ctx.config.get(ROOT_PASSWORD_KEY) or ctx.ask(
        QCoreApplication.translate("vps_setup", "Contraseña de {0} (la del proveedor)").format(
            root.target
        ),
        secret=True,
    )
    if not password:
        raise TaskError(
            QCoreApplication.translate(
                "vps_setup", "Sin la contraseña de root no se puede poner la llave en el VPS."
            )
        )
    # canone's `authorize.py` writes the key, not Consola (ADR-0084).
    script = f"/tmp/consola-{AUTHORIZE}"
    ssh.upload_with_password(ctx, root, canone.infra_dir(ctx.config) / AUTHORIZE, script, password)
    ssh.run_with_password(
        ctx,
        root,
        f"{PYTHON}; python3 {script} {ssh.quote(ssh.public_key(private))}; "
        f"status=$?; rm -f {script}; exit $status",
        password,
    )
    if not ssh.reachable(root):
        raise TaskError(
            QCoreApplication.translate(
                "vps_setup", "La llave quedó en {0}, pero no entra con ella."
            ).format(root.target)
        )
    ctx.ok(
        QCoreApplication.translate("vps_setup", "La llave {0} entra como {1}.").format(
            private.name, root.target
        )
    )


def install_software(ctx: TaskContext) -> list[str]:
    """Run canone's `packages.py`, and then `uv.py`.

    The packages come from canone, not from here: `packages.py` gets the
    options of `install.py` that add one, from `config.env` and the repo
    (`canone.package_args`, ADR-0131 of canone). It runs with the
    machine's `python3`: an image without it gets it from apt first.
    `uv.py` installs the uv version canone fixes (ADR-0110 of canone):
    it runs again when canone changes it.
    """
    entry = access(ctx)
    packages = canone.packages(ctx.root, ctx.config)
    ctx.info(
        QCoreApplication.translate("vps_setup", "Paquetes de canone para este repo: {0}").format(
            ", ".join(packages)
        )
    )
    destination = _upload(ctx, entry)
    options = " ".join(ssh.quote(a) for a in canone.package_args(ctx.root, ctx.config))
    try:
        _ensure_python(ctx, entry)
        entry.run(ctx, f"python3 {destination}/packages.py {options}".rstrip())
        entry.run(ctx, f"python3 {destination}/uv.py")
    finally:
        _cleanup(ctx, entry)
    ctx.ok(
        QCoreApplication.translate("vps_setup", "Paquetes y uv listos: {0}").format(
            ", ".join(packages)
        )
    )
    return packages


def create_swap(ctx: TaskContext) -> None:
    """Run canone's `swap.py`, for the swap `install.py` asks for.

    It creates `/swapfile` with what is missing, and changes nothing if
    there is enough (ADR-0132 of canone).
    """
    entry = access(ctx)
    destination = _upload(ctx, entry)
    try:
        _ensure_python(ctx, entry)
        entry.run(ctx, f"python3 {destination}/swap.py")
    finally:
        _cleanup(ctx, entry)


def _valkey_memory(ctx: TaskContext, entry: Access) -> str:
    """Return `VALKEY_MEMORY`, or the share of the VPS's memory.

    The share is `VALKEY_PERCENT` of `MemTotal`, read on the VPS, and
    the log says which it was (ADR-0086).
    """
    written = ctx.config.get("VALKEY_MEMORY")
    if written:
        return written
    percent = ctx.config.get("VALKEY_PERCENT")
    meminfo = ssh.capture(entry.remote, "cat /proc/meminfo")
    memory = canone.valkey_memory(meminfo, percent)
    ctx.info(
        QCoreApplication.translate(
            "vps_setup", "Memoria de Valkey: {0}, el {1} % de la RAM del VPS."
        ).format(memory, percent)
    )
    return memory


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
    outside = ssh.read_public_key(Path(ctx.config.require("OFFLINE_KEY")).expanduser())
    if outside.split()[:2] == key.split()[:2]:
        raise TaskError(
            QCoreApplication.translate(
                "vps_setup",
                "{0} es la misma llave que {1}: hace falta otra, guardada fuera de esta máquina.",
            ).format(names(["OFFLINE_KEY"]), names(["VPS_KEY_NAME"]))
        )
    entry = access(ctx)
    memory = _valkey_memory(ctx, entry)
    arguments = canone.install_args(ctx.root, ctx.config, app, owner, (key, outside), memory)
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
    ctx.ok(
        QCoreApplication.translate("vps_setup", "{0} instalado en {1}.").format(
            app, entry.remote.host
        )
    )


def load_credentials(
    ctx: TaskContext, generate: Sequence[str] = (), replace: bool = False
) -> None:
    """Pass the `config.env` credentials to `credentials.py`, by stdin.

    One `field=value` line per `Settings` field, plus `restic_password`
    and, in a private repo, `github_token` (ADR-0063). It stops before
    sending if one is missing or if `config.env` has a key in no source.
    `install.py` does not install `credentials.py`, so it uploads each
    time. The secrets named in `generate` get a value first: those with
    none, or all with `replace` (ADR-0098). They are saved only once the
    rest is known to be right.
    """
    _, app = canone.origin(ctx.root)
    entry = admin(ctx) if generate else None
    new = new_secrets(ctx, entry, app, generate, replace) if entry else {}
    ctx.config.values.update(new)
    if fields.SETUP_CODE in fields.settings_fields(ctx.root / ctx.config.get("SERVER_DIR")):
        setup_code(ctx)
    lines = canone.credential_lines(ctx.root, ctx.config)
    for line in lines.splitlines():
        field, _, value = line.partition("=")
        # The domain is public, and the next steps name it in the log.
        if field != fields.DOMAIN:
            ctx.guard(value)
    entry = entry or admin(ctx)
    destination = _upload(ctx, entry)
    try:
        if new:
            _keep(ctx, new)
            ctx.warn(
                QCoreApplication.translate(
                    "vps_setup", "Secretos generados y guardados en config.env: {0}."
                ).format(names(list(new)))
            )
        entry.run(ctx, f"python3 {destination}/credentials.py {ssh.quote(app)}", text=lines)
    finally:
        _cleanup(ctx, entry)
    ctx.ok(
        QCoreApplication.translate("vps_setup", "{0} credenciales cargadas.").format(
            len(lines.splitlines())
        )
    )


def _keep(ctx: TaskContext, new: dict[str, str]) -> None:
    """Save generated values in `config.env` and in this run."""
    server = ctx.root / ctx.config.get("SERVER_DIR")
    values = envfile.load_config(str(ctx.root)) | new
    envfile.save_config(str(ctx.root), values, fields.field_settings(server))
    ctx.config.values.update(new)


def new_secrets(
    ctx: TaskContext, entry: Access, app: str, chosen: Sequence[str], replace: bool
) -> dict[str, str]:
    """Return a new value for the chosen secrets, by `config.env` key.

    Without `replace`, only for those with no value. One that the VPS
    has and `config.env` does not stops: its value is unknown here, and
    a new one would replace it.
    """
    wanted = [f for f in canone.random_secrets(ctx.root, ctx.config) if f in chosen]
    if not replace:
        kept = [f for f in wanted if ctx.config.get(f.upper())]
        if kept:
            ctx.info(
                QCoreApplication.translate(
                    "vps_setup", "Ya tienen valor y se conservan: {0}."
                ).format(", ".join(kept))
            )
        wanted = [f for f in wanted if f not in kept]
        stored = entry.capture(canone.stored_command(app, wanted)).split() if wanted else []
        if stored:
            raise TaskError(
                QCoreApplication.translate(
                    "vps_setup",
                    "El VPS ya tiene {0}, y config.env no: escribe su valor o marca «Reemplazar».",
                ).format(", ".join(stored))
            )
    new = {field.upper(): canone.GENERATED[field]() for field in wanted}
    ctx.guard(*new.values())
    return new


def setup_code(ctx: TaskContext) -> str:
    """Return `SETUP_CODE`, generating and saving one if it is empty.

    The code registers the first superadmin («Superadministrador» of
    canone's autenticacion.md). A generated one is 6 digits, goes to
    `config.env` so every load sends the same, and shows in the log.
    """
    code = ctx.config.get("SETUP_CODE").strip()
    if code:
        return code
    code = f"{secrets.randbelow(10**6):06d}"
    _keep(ctx, {"SETUP_CODE": code})
    ctx.note(QCoreApplication.translate("vps_setup", "Código de instalación: {0}").format(code))
    return code


def load_setup_code(ctx: TaskContext) -> None:
    """Load `SETUP_CODE` on the VPS, generating it if it is empty.

    It goes alone: `credentials.py` writes only the fields it reads,
    and restarts the server so it reads it.
    """
    code = setup_code(ctx)
    _, app = canone.origin(ctx.root)
    entry = admin(ctx)
    destination = _upload(ctx, entry)
    try:
        entry.run(
            ctx,
            f"python3 {destination}/credentials.py {ssh.quote(app)}",
            text=f"{fields.SETUP_CODE}={code}\n",
        )
    finally:
        _cleanup(ctx, entry)
    ctx.ok(
        QCoreApplication.translate(
            "vps_setup", "Código de instalación cargado en {0}: el servidor se reinició."
        ).format(entry.remote.host)
    )


# --- undo ---


def clean_vps(ctx: TaskContext, level: str = "database", apply: bool = False) -> None:
    """Run canone's `uninstall.py` at that level; a dry run only lists.

    ADR-0083. It enters through the admin account, which no level
    touches: root stays locked, so it is the way back in.
    """
    _, app = canone.origin(ctx.root)
    entry = admin(ctx)
    destination = _upload(ctx, entry)
    command = f"python3 {destination}/uninstall.py {ssh.quote(app)} {ssh.quote(level)}"
    try:
        entry.run(ctx, command if apply else f"{command} --dry-run")
    finally:
        _cleanup(ctx, entry)
    if apply:
        ctx.ok(QCoreApplication.translate("vps_setup", "VPS vaciado: {0}.").format(level))
        ctx.note(
            QCoreApplication.translate("vps_setup", "VPS {0} vaciado: {1}.").format(
                ctx.config.require("VPS_IP"), level
            )
        )


# --- composite ---


def bootstrap_vps(
    ctx: TaskContext,
    *,
    known_host: bool = False,
    key: bool = True,
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
    from app.services.tasks.vps_release import deploy_latest

    if known_host:
        ctx.step("known_host")
        refresh_known_host(ctx)
    if key:
        ctx.step("key")
        install_key(ctx)
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
    ctx.note(
        QCoreApplication.translate("vps_setup", "VPS {0} configurado.").format(
            ctx.config.require("VPS_IP")
        )
    )


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("refresh_known_host", refresh_known_host)
    registry.bind("install_software", install_software)
    registry.bind("load_credentials", load_credentials)
    registry.bind("load_setup_code", load_setup_code)
    registry.bind("bootstrap_vps", bootstrap_vps)
    registry.bind("clean_vps", clean_vps)
