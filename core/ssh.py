from __future__ import annotations
import hashlib
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import process
from .envfile import Config
from .errors import TaskError

CONNECT_TIMEOUT = ['-o', 'ConnectTimeout=15']
BATCH = ['-o', 'BatchMode=yes']


def identity_path(key_name: str) -> Path:
    return Path.home() / '.ssh' / key_name


def resolve_identity(key_name: str) -> Path:
    path = identity_path(key_name)
    if not path.is_file():
        raise TaskError(f'No existe la llave privada local: {path}')
    return path


def _control_args(identity: Path, target: str) -> list[str]:
    """Multiplexado: una sola conexion TCP para una rafaga de ssh/scp seguidos.

    Sin esto, subir cinco archivos abre cinco conexiones y el VPS puede cortarlas
    por rate-limiting. Se apaga en Windows: el ControlMaster de Win32-OpenSSH
    emula sockets Unix con pipes y falla al reusar el socket entre invocaciones.
    """
    if os.name == 'nt':
        return []
    digest = hashlib.sha1(f'{target}:{identity}'.encode('utf-8')).hexdigest()[:16]
    control_dir = Path(tempfile.gettempdir()) / 'consola_ssh'
    control_dir.mkdir(parents=True, exist_ok=True)
    socket_path = control_dir / f'{digest}.sock'
    return ['-o', 'ControlMaster=auto',
            '-o', f'ControlPath={socket_path}',
            '-o', 'ControlPersist=60s']


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
        return f'{self.user}@{self.host}'

    def as_user(self, user: str) -> 'Remote':
        """El mismo servidor con otra cuenta (root durante el aprovisionamiento)."""
        return Remote(self.host, user, self.identity)

    def argv(self, command: str, *, tty: bool = False, extra: Sequence[str] = ()) -> list[str]:
        # `-n` salvo que se pida TTY: estos comandos no leen teclado, y sin
        # cerrarle el stdin `ssh` lo reenvia al comando remoto y puede quedar
        # esperando un EOF que nunca llega cuando corre dentro de la GUI.
        return ['ssh', *CONNECT_TIMEOUT, *_control_args(self.identity, self.target),
                *(['-t'] if tty else ['-n']), *extra,
                '-i', str(self.identity), self.target, command]

    def scp_argv(self, local: Path, remote_path: str, *,
                 download: bool = False, recursive: bool = False) -> list[str]:
        spec = f'{self.target}:{remote_path}'
        argv = ['scp', *(['-r'] if recursive else []), *CONNECT_TIMEOUT,
                *_control_args(self.identity, self.target), '-i', str(self.identity)]
        argv.extend([spec, str(local)] if download else [str(local), spec])
        return argv


def resolve_remote(config: Config, *, user: str = '') -> Remote:
    """Arma el `Remote` del proyecto desde `.consola/config.env`.

    `user` vacio significa VPS_USER; los pasos de aprovisionamiento que todavia
    no tienen usuario de despliegue pasan ROOT_USER explicitamente.
    """
    return Remote(
        host=config.require('VPS_IP'),
        user=user or config.get('VPS_USER'),
        identity=resolve_identity(config.require('VPS_KEY_NAME')),
    )


def quote(value: str) -> str:
    """Cita un valor para el shell remoto. Los paths remotos son siempre POSIX."""
    return shlex.quote(value)


# --- contrasena sin consola ------------------------------------------------

_PASSWORD_VAR = 'CONSOLA_SSH_PASSWORD'

# Sin `PubkeyAuthentication=no`: si root ya tiene la llave instalada se entra con
# ella y la contrasena no llega a usarse, que es como funcionaba antes de que
# esto existiera. Forzar contrasena cerraba ese camino y el setup moria con
# "Permission denied" en servidores donde la llave alcanzaba.
# Un solo intento: con el helper, reintentar es mandar tres veces lo mismo.
PASSWORD_OPTS = ['-o', 'NumberOfPasswordPrompts=1']


def _askpass_helper() -> Path:
    """Script que solo reimprime la contrasena que le llega por el entorno."""
    directory = Path(tempfile.gettempdir()) / 'consola_ssh'
    directory.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # `!VAR!` y no `%VAR%`: con expansion retardada cmd no vuelve a parsear
        # el valor, asi que una contrasena con & | > ^ % ! llega entera.
        helper = directory / 'askpass.bat'
        helper.write_text('@echo off\r\nsetlocal EnableDelayedExpansion\r\n'
                          f'echo !{_PASSWORD_VAR}!\r\n', encoding='utf-8')
    else:
        helper = directory / 'askpass.sh'
        helper.write_text(f'#!/bin/sh\nprintf "%s\\n" "${_PASSWORD_VAR}"\n', encoding='utf-8')
        helper.chmod(0o700)
    return helper


def password_env(password: str) -> dict[str, str]:
    """Entorno para darle una contrasena a `ssh` sin consola donde escribirla.

    La GUI lanza todo con el stdin cerrado y sin ventana (`core/process.py`), y
    `ssh` pide la contrasena a la consola, no a stdin: dentro de la app no hay
    donde escribirla y la conexion se queda esperando. `SSH_ASKPASS_REQUIRE`
    (OpenSSH 8.4+) la deriva a un helper, que es lo que `sshpass` conseguia con
    un PTY falso; y `sshpass` no existe en Windows, que era el error con el que
    moria el boton de setup.

    La contrasena viaja por el entorno del proceso: no toca el disco ni la
    linea de comandos, que es lo unico que se ve en el log.
    """
    return {
        'SSH_ASKPASS': str(_askpass_helper()),
        'SSH_ASKPASS_REQUIRE': 'force',
        # Antes de 8.4 el helper se ignora si no hay DISPLAY, aunque no se use.
        'DISPLAY': os.environ.get('DISPLAY') or ':0',
        _PASSWORD_VAR: password,
    }


# --- ejecucion remota ------------------------------------------------------

def capture(remote: Remote, command: str, *, timeout: float | None = 30.0,
            check: bool = True) -> str:
    """Consulta corta por SSH. Devuelve stdout; no toca el log."""
    return process.capture(remote.argv(command, extra=BATCH), timeout=timeout, check=check)


def run(ctx, remote: Remote, command: str, *, check: bool = True,
        echo: bool = True) -> int:
    """Comando remoto con streaming en vivo hacia la consola de la pestana."""
    return ctx.run(remote.argv(command), check=check, cwd=None, echo=echo)


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
    con boton propio (docs/atomicas.md 0).
    """
    return succeeds(remote, 'echo ok')


def path_exists(remote: Remote, remote_path: str) -> bool:
    return succeeds(remote, f'test -e {quote(remote_path)}')


def ensure_dir(remote: Remote, remote_path: str) -> None:
    capture(remote, f'mkdir -p {quote(remote_path)}')


# --- transferencia ---------------------------------------------------------

def upload(ctx, remote: Remote, local: Path, remote_path: str, *,
           chmod: str = '', make_parent: bool = True) -> str:
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
        raise TaskError(f'No existe la ruta local: {local}')

    parent, _, base = remote_path.rpartition('/')
    if local.is_dir() and base != local.name:
        raise TaskError(
            f'La carpeta local {local.name!r} no coincide con el destino remoto '
            f'{base!r}: scp -r no renombra, la dejaria en {remote_path}/{local.name}.')
    if make_parent and parent:
        ensure_dir(remote, parent)

    destino = parent if local.is_dir() else remote_path
    ctx.run(remote.scp_argv(local, destino, recursive=local.is_dir()))
    if chmod:
        capture(remote, f'chmod {chmod} {quote(remote_path)}')
    return remote_path


def download(ctx, remote: Remote, remote_path: str, local: Path, *,
             recursive: bool = False) -> Path:
    local.parent.mkdir(parents=True, exist_ok=True)
    ctx.run(remote.scp_argv(local, remote_path, download=True, recursive=recursive))
    return local


# --- tunel -----------------------------------------------------------------

@dataclass
class Tunnel:
    """Un `ssh -N -L` vivo. Es un servicio de fondo, no una tarea (PLAN.md 7.2)."""
    remote: Remote
    local_port: int
    remote_port: int
    proc: subprocess.Popen

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def endpoint(self) -> str:
        return f'127.0.0.1:{self.local_port}'

    def close(self) -> None:
        process.kill_tree(self.proc)

    def __enter__(self) -> 'Tunnel':
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_tunnel(remote: Remote, *, local_port: int, remote_port: int) -> Tunnel:
    forward = f'127.0.0.1:{local_port}:127.0.0.1:{remote_port}'
    argv = ['ssh', *CONNECT_TIMEOUT, '-i', str(remote.identity),
            '-N', '-L', forward, remote.target]
    return Tunnel(remote, local_port, remote_port, process.spawn(argv, detached=True))


# --- llaves y known_hosts --------------------------------------------------

def ensure_local_keypair(ctx, key_name: str, *, comment: str = '') -> Path:
    """Crea `~/.ssh/<key_name>` si falta. Idempotente: si ya existe, no la toca."""
    private = identity_path(key_name)
    if private.is_file():
        ctx.info(f'La llave local ya existe: {private}')
        return private

    private.parent.mkdir(parents=True, exist_ok=True)
    ctx.run(['ssh-keygen', '-t', 'ed25519', '-f', str(private),
             '-N', '', '-C', comment or key_name])
    return private


def public_key_path(private: Path) -> Path:
    return private.with_name(private.name + '.pub')


def public_key(private: Path) -> str:
    pub = public_key_path(private)
    if not pub.is_file():
        raise TaskError(f'No existe la llave publica: {pub}')
    return pub.read_text(encoding='utf-8').strip()


def forget_host(ctx, host: str) -> None:
    """Saca la entrada vieja de known_hosts.

    Tras reinstalar el VPS cambia la huella y el cliente rechaza la conexion
    hasta que se limpia la entrada anterior.
    """
    ctx.run(['ssh-keygen', '-R', host], check=False)


def terminal_argv(remote: Remote) -> list[str]:
    """Sesion interactiva en terminal externa: necesita TTY real (PLAN.md 7.1)."""
    ssh = ['ssh', '-i', str(remote.identity), remote.target]
    if os.name == 'nt':
        return ['wt.exe', *ssh]
    return ssh
