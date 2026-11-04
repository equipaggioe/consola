"""Remote, remote commands, scp, tunnels and keys."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core import process
from app.core.context import TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.host import HOST

# `accept-new`: the first connection to a VPS records its fingerprint,
# and a changed one still stops. Without this, `BatchMode` rejects a new
# VPS and Consola says it cannot get in.
CONNECT_TIMEOUT = ["-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new"]
BATCH = ["-o", "BatchMode=yes"]


def identity_path(key_name: str) -> Path:
    """Return the path of a private key in `~/.ssh`."""
    return Path.home() / ".ssh" / key_name


def resolve_identity(key_name: str) -> Path:
    """Return the private key's path, or stop if it does not exist."""
    path = identity_path(key_name)
    if not path.is_file():
        raise TaskError(f"No existe la llave privada local: {path}")
    return path


def _control_args(identity: Path, target: str) -> list[str]:
    """Return the multiplexing options, where the system supports them.

    One TCP connection for a burst of ssh and scp. Without it, uploading
    five files opens five connections and the VPS can cut them by rate
    limiting (`HOST.ssh_multiplex`).
    """
    if not HOST.ssh_multiplex:
        return []
    digest = hashlib.sha1(
        f"{target}:{identity}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()[:16]
    control_dir = Path(tempfile.gettempdir()) / "consola_ssh"
    control_dir.mkdir(parents=True, exist_ok=True)
    socket_path = control_dir / f"{digest}.sock"
    return [
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={socket_path}",
        "-o",
        "ControlPersist=60s",
    ]


@dataclass(frozen=True)
class Remote:
    """Where and with which key the VPS is reached.

    They resolve once and travel together: whoever operates the VPS asks
    for a `Remote`, not three strings.
    """

    host: str
    user: str
    identity: Path

    @property
    def target(self) -> str:
        """Return `user@host`."""
        return f"{self.user}@{self.host}"

    def as_user(self, user: str) -> "Remote":
        """Return the same server with another account.

        Root at provisioning.
        """
        return Remote(self.host, user, self.identity)

    def argv(
        self, command: str, *, tty: bool = False, stdin: bool = False, extra: Sequence[str] = ()
    ) -> list[str]:
        # `-n` unless a TTY or input is asked for: these commands read
        # no keyboard, and with stdin unclosed `ssh` forwards it to the
        # remote command and can wait for an EOF that never comes inside
        # the GUI. `stdin=True` is for what does read: the password of
        # `sudo -S` or the lines of `credentials.py`.
        """Return the argv of `ssh` for a remote command."""
        mode = ["-t"] if tty else [] if stdin else ["-n"]
        return [
            "ssh",
            *CONNECT_TIMEOUT,
            *_control_args(self.identity, self.target),
            *mode,
            *extra,
            "-i",
            str(self.identity),
            self.target,
            command,
        ]

    def scp_argv(
        self, local: Path, remote_path: str, *, download: bool = False, recursive: bool = False
    ) -> list[str]:
        """Return the argv of `scp` for a copy."""
        spec = f"{self.target}:{remote_path}"
        argv = [
            "scp",
            *(["-r"] if recursive else []),
            *CONNECT_TIMEOUT,
            *_control_args(self.identity, self.target),
            "-i",
            str(self.identity),
        ]
        argv.extend([spec, str(local)] if download else [str(local), spec])
        return argv


def resolve_remote(config: Config, *, user: str = "") -> Remote:
    """Build the project's `Remote` from `.consola/config.env`.

    An empty `user` means VPS_USER. Before `install.py` that account
    does not exist, and `core/tasks/vps_setup.py::access` enters as
    `ROOT_USER`.
    """
    return Remote(
        host=config.require("VPS_IP"),
        user=user or config.require("VPS_USER"),
        identity=resolve_identity(config.require("VPS_KEY_NAME")),
    )


def quote(value: str) -> str:
    """Quote a value for the remote shell.

    Remote paths are always POSIX.
    """
    return shlex.quote(value)


def capture(
    remote: Remote,
    command: str,
    *,
    timeout: float | None = 30.0,
    check: bool = True,
    stdin_text: str | None = None,
) -> str:
    """Run a short query over SSH and return stdout, without the log.

    `stdin_text` reaches the remote command's input.
    """
    argv = remote.argv(command, stdin=stdin_text is not None, extra=BATCH)
    return process.capture(argv, timeout=timeout, check=check, stdin_text=stdin_text)


def run(
    ctx: TaskContext,
    remote: Remote,
    command: str,
    *,
    check: bool = True,
    echo: bool = True,
    stdin_text: str | None = None,
) -> int:
    """Run a remote command, streaming live to the tab's console.

    `stdin_text` reaches the remote command's input and not the log.
    """
    return ctx.run(
        remote.argv(command, stdin=stdin_text is not None),
        check=check,
        cwd=None,
        echo=echo,
        stdin_text=stdin_text,
    )


def succeeds(remote: Remote, command: str) -> bool:
    """Return whether the remote command ends in 0.

    To detect before acting.
    """
    try:
        process.capture(remote.argv(command, extra=BATCH), timeout=30.0, check=True)
        return True
    except TaskError:
        return False


def reachable(remote: Remote) -> bool:
    """Return whether the VPS is reachable with the key.

    Without a password.

    It is the precondition of all the doors of `resolve_remote`: they
    fail equally badly when access is broken, and none can tell «did not
    reach the machine» from «the command failed». It is plumbing and not
    a task with its own button (ADR-0004).
    """
    return succeeds(remote, "echo ok")


def path_exists(remote: Remote, remote_path: str) -> bool:
    """Return whether the remote path exists."""
    return succeeds(remote, f"test -e {quote(remote_path)}")


def ensure_dir(remote: Remote, remote_path: str) -> None:
    """Create the remote folder if it is missing."""
    capture(remote, f"mkdir -p {quote(remote_path)}")


# --- transfer ---


def upload(
    ctx: TaskContext,
    remote: Remote,
    local: Path,
    remote_path: str,
    *,
    chmod: str = "",
    make_parent: bool = True,
) -> str:
    """Upload a file or folder and return the resulting remote path.

    A folder goes to the PARENT of `remote_path`. `scp -r source target`
    copies the folder *inside* the target when the target exists, so
    pointing at the final path works once and from the second time
    leaves `.../dist/dist`: the server keeps serving the old build and
    the new one stays buried a level below.
    """
    if not local.exists():
        raise TaskError(f"No existe la ruta local: {local}")

    parent, _, base = remote_path.rpartition("/")
    if local.is_dir() and base != local.name:
        raise TaskError(
            f"La carpeta local {local.name!r} no coincide con el destino remoto "
            f"{base!r}: scp -r no renombra, la dejaria en {remote_path}/{local.name}."
        )
    if make_parent and parent:
        ensure_dir(remote, parent)

    destination = parent if local.is_dir() else remote_path
    ctx.run(remote.scp_argv(local, destination, recursive=local.is_dir()))
    if chmod:
        capture(remote, f"chmod {chmod} {quote(remote_path)}")
    return remote_path


def download(
    ctx: TaskContext, remote: Remote, remote_path: str, local: Path, *, recursive: bool = False
) -> Path:
    """Download a remote file or folder."""
    local.parent.mkdir(parents=True, exist_ok=True)
    ctx.run(remote.scp_argv(local, remote_path, download=True, recursive=recursive))
    return local


# --- tunnel ---


@dataclass
class Tunnel:
    """A live `ssh -N -L`: a service, not a task (ADR-0016)."""

    remote: Remote
    local_port: int
    remote_port: int
    proc: subprocess.Popen[str]

    @property
    def alive(self) -> bool:
        """Return whether the tunnel's process lives."""
        return self.proc.poll() is None

    @property
    def endpoint(self) -> str:
        """Return the local `host:port`."""
        return f"127.0.0.1:{self.local_port}"

    def close(self) -> None:
        """Close the tunnel."""
        process.kill_tree(self.proc)

    def __enter__(self) -> "Tunnel":
        """Return the tunnel, for a `with` block."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the tunnel when leaving the `with` block."""
        self.close()


def open_tunnel(remote: Remote, *, local_port: int, remote_port: int) -> Tunnel:
    """Open a tunnel and return it once it forwards."""
    forward = f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}"
    # Without ExitOnForwardFailure, a taken local port leaves ssh alive
    # forwarding nothing, and the connection lands on what already
    # listened there.
    argv = [
        "ssh",
        *CONNECT_TIMEOUT,
        "-o",
        "ExitOnForwardFailure=yes",
        "-i",
        str(remote.identity),
        "-N",
        "-L",
        forward,
        remote.target,
    ]
    proc = process.spawn(argv, detached=True)
    process.bind_to_app(proc)
    return Tunnel(remote, local_port, remote_port, proc)


# --- keys and known_hosts ---


def ensure_local_keypair(ctx: TaskContext, key_name: str, *, comment: str = "") -> Path:
    """Create `~/.ssh/<key_name>` if missing. Idempotent."""
    private = identity_path(key_name)
    if private.is_file():
        ctx.info(f"La llave local ya existe: {private}")
        return private

    private.parent.mkdir(parents=True, exist_ok=True)
    ctx.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(private), "-N", "", "-C", comment or key_name]
    )
    return private


def public_key_path(private: Path) -> Path:
    """Return the path of the private key's public half."""
    return private.with_name(private.name + ".pub")


def public_key(private: Path) -> str:
    """Return the text of the public key."""
    pub = public_key_path(private)
    if not pub.is_file():
        raise TaskError(f"No existe la llave publica: {pub}")
    return pub.read_text(encoding="utf-8").strip()


def forget_host(ctx: TaskContext, host: str) -> None:
    """Remove the old entry from known_hosts.

    After reinstalling the VPS its fingerprint changes, and the client
    rejects the connection until the old entry is cleared.
    """
    ctx.run(["ssh-keygen", "-R", host], check=False)


def terminal_argv(remote: Remote) -> list[str]:
    """Return a session for an external terminal (ADR-0005)."""
    return HOST.terminal_argv(["ssh", "-i", str(remote.identity), remote.target])
