from __future__ import annotations

import hashlib
import shlex
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core import process
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.host import HOST

# `accept-new`: la primera conexion a un VPS anota su huella, y una huella que
# cambio sigue cortando. Sin esto, `BatchMode` rechaza a un VPS nuevo y Consola
# dice que no se entra.
CONNECT_TIMEOUT = ["-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new"]
BATCH = ["-o", "BatchMode=yes"]


def identity_path(key_name: str) -> Path:
    return Path.home() / ".ssh" / key_name


def resolve_identity(key_name: str) -> Path:
    path = identity_path(key_name)
    if not path.is_file():
        raise TaskError(f"No existe la llave privada local: {path}")
    return path


def _control_args(identity: Path, target: str) -> list[str]:
    """Multiplexado: una sola conexion TCP para una rafaga de ssh/scp seguidos.

    Sin esto, subir cinco archivos abre cinco conexiones y el VPS puede cortarlas
    por rate-limiting. No todos los sistemas lo soportan (`HOST.ssh_multiplex`).
    """
    if not HOST.ssh_multiplex:
        return []
    digest = hashlib.sha1(f"{target}:{identity}".encode("utf-8")).hexdigest()[:16]
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
    """A donde y con que llave se llega al VPS.

    En los scripts, cada funcion remota recibia `host`, `user` e `identity_file`
    por separado y los volvia a resolver desde el .env. Aca se resuelven una vez
    y viajan juntos: quien opera el VPS pide un `Remote`, no tres strings.
    """

    host: str
    user: str
    identity: Path

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}"

    def as_user(self, user: str) -> "Remote":
        """El mismo servidor con otra cuenta (root durante el aprovisionamiento)."""
        return Remote(self.host, user, self.identity)

    def argv(
        self, command: str, *, tty: bool = False, stdin: bool = False, extra: Sequence[str] = ()
    ) -> list[str]:
        # `-n` salvo que se pida TTY o entrada: estos comandos no leen teclado,
        # y sin cerrarle el stdin `ssh` lo reenvia al comando remoto y puede
        # quedar esperando un EOF que nunca llega cuando corre dentro de la GUI.
        # `stdin=True` es para lo que si lee: la contraseña de `sudo -S` o las
        # lineas de `credentials.py`.
        modo = ["-t"] if tty else [] if stdin else ["-n"]
        return [
            "ssh",
            *CONNECT_TIMEOUT,
            *_control_args(self.identity, self.target),
            *modo,
            *extra,
            "-i",
            str(self.identity),
            self.target,
            command,
        ]

    def scp_argv(
        self, local: Path, remote_path: str, *, download: bool = False, recursive: bool = False
    ) -> list[str]:
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
    """Arma el `Remote` del proyecto desde `.consola/config.env`.

    `user` vacio significa VPS_USER. Antes de `install.py` esa cuenta no existe, y
    `core/tasks/vps_setup.py::access` entra como `ROOT_USER`.
    """
    return Remote(
        host=config.require("VPS_IP"),
        user=user or config.require("VPS_USER"),
        identity=resolve_identity(config.require("VPS_KEY_NAME")),
    )


def quote(value: str) -> str:
    """Cita un valor para el shell remoto. Los paths remotos son siempre POSIX."""
    return shlex.quote(value)


def capture(
    remote: Remote,
    command: str,
    *,
    timeout: float | None = 30.0,
    check: bool = True,
    stdin_text: str | None = None,
) -> str:
    """Consulta corta por SSH. Devuelve stdout; no toca el log.

    `stdin_text` llega a la entrada del comando remoto.
    """
    argv = remote.argv(command, stdin=stdin_text is not None, extra=BATCH)
    return process.capture(argv, timeout=timeout, check=check, stdin_text=stdin_text)


def run(
    ctx,
    remote: Remote,
    command: str,
    *,
    check: bool = True,
    echo: bool = True,
    stdin_text: str | None = None,
) -> int:
    """Comando remoto con streaming en vivo hacia la consola de la pestana.

    `stdin_text` llega a la entrada del comando remoto y no al log.
    """
    return ctx.run(
        remote.argv(command, stdin=stdin_text is not None),
        check=check,
        cwd=None,
        echo=echo,
        stdin_text=stdin_text,
    )


def succeeds(remote: Remote, command: str) -> bool:
    """True si el comando remoto termina en 0. Para detectar antes de actuar."""
    try:
        process.capture(remote.argv(command, extra=BATCH), timeout=30.0, check=True)
        return True
    except TaskError:
        return False


def reachable(remote: Remote) -> bool:
    """True si se llega al VPS con la llave y sin contrasena.

    Es la precondicion que comparten las once puertas de `resolve_remote`:
    todas fallan igual de feo cuando el acceso esta roto y ninguna sabe
    distinguir "no llego a la maquina" de "el comando fallo". Vivio un tiempo
    como la atomica `test_ssh_login` de `vps_setup`, y se bajo aca al notar que
    algo que necesitan casi todos los botones de SSH es plomeria, no una tarea
    con boton propio (ADR-0004).
    """
    return succeeds(remote, "echo ok")


def path_exists(remote: Remote, remote_path: str) -> bool:
    return succeeds(remote, f"test -e {quote(remote_path)}")


def ensure_dir(remote: Remote, remote_path: str) -> None:
    capture(remote, f"mkdir -p {quote(remote_path)}")


# --- transferencia ---------------------------------------------------------


def upload(
    ctx,
    remote: Remote,
    local: Path,
    remote_path: str,
    *,
    chmod: str = "",
    make_parent: bool = True,
) -> str:
    """Sube un archivo o directorio y devuelve la ruta remota resultante.

    Un directorio se manda al PADRE de `remote_path`, no a `remote_path`.
    `scp -r origen destino` copia la carpeta *dentro* del destino cuando el
    destino ya existe, asi que apuntar a la ruta final funciona la primera vez
    y a partir de la segunda deja `.../dist/dist`: el servidor sigue sirviendo
    el build viejo y el nuevo queda enterrado un nivel mas abajo.

    Es exactamente lo que hacia `scripts/common.py::copy_to_vps`, que pasaba
    `remote_parent` para directorios y la ruta completa para archivos.
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

    destino = parent if local.is_dir() else remote_path
    ctx.run(remote.scp_argv(local, destino, recursive=local.is_dir()))
    if chmod:
        capture(remote, f"chmod {chmod} {quote(remote_path)}")
    return remote_path


def download(
    ctx, remote: Remote, remote_path: str, local: Path, *, recursive: bool = False
) -> Path:
    local.parent.mkdir(parents=True, exist_ok=True)
    ctx.run(remote.scp_argv(local, remote_path, download=True, recursive=recursive))
    return local


# --- tunel -----------------------------------------------------------------


@dataclass
class Tunnel:
    """Un `ssh -N -L` vivo. Es un servicio de fondo, no una tarea (ADR-0016)."""

    remote: Remote
    local_port: int
    remote_port: int
    proc: subprocess.Popen

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def endpoint(self) -> str:
        return f"127.0.0.1:{self.local_port}"

    def close(self) -> None:
        process.kill_tree(self.proc)

    def __enter__(self) -> "Tunnel":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_tunnel(remote: Remote, *, local_port: int, remote_port: int) -> Tunnel:
    forward = f"127.0.0.1:{local_port}:127.0.0.1:{remote_port}"
    # Sin ExitOnForwardFailure, un puerto local ocupado deja a ssh vivo sin
    # reenviar nada y la conexion cae en lo que ya escuchaba ahi.
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


# --- llaves y known_hosts --------------------------------------------------


def ensure_local_keypair(ctx, key_name: str, *, comment: str = "") -> Path:
    """Crea `~/.ssh/<key_name>` si falta. Idempotente: si ya existe, no la toca."""
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
    return private.with_name(private.name + ".pub")


def public_key(private: Path) -> str:
    pub = public_key_path(private)
    if not pub.is_file():
        raise TaskError(f"No existe la llave publica: {pub}")
    return pub.read_text(encoding="utf-8").strip()


def forget_host(ctx, host: str) -> None:
    """Saca la entrada vieja de known_hosts.

    Tras reinstalar el VPS cambia la huella y el cliente rechaza la conexion
    hasta que se limpia la entrada anterior.
    """
    ctx.run(["ssh-keygen", "-R", host], check=False)


def terminal_argv(remote: Remote) -> list[str]:
    """Sesion interactiva en terminal externa: necesita TTY real (ADR-0005)."""
    return HOST.terminal_argv(["ssh", "-i", str(remote.identity), remote.target])
