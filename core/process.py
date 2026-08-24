from __future__ import annotations
import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .errors import Cancelled, TaskError

Argv = Sequence[str]
LineSink = Callable[[str], None]

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def format_argv(argv: Argv) -> str:
    """Linea legible para el log. No es para volver a ejecutar: es para leer."""
    return ' '.join(f'"{a}"' if ' ' in str(a) else str(a) for a in argv)


def which_any(names: Iterable[str]) -> str | None:
    """Primer ejecutable de `names` que exista en el PATH."""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def as_argv(executable: str) -> list[str]:
    """Envuelve los shims `.bat`/`.cmd` de Windows, que no son ejecutables reales.

    En Windows, `flutter.bat` o `npm.cmd` solo corren a traves de `cmd.exe /c`;
    en el resto de los sistemas el ejecutable se invoca tal cual.
    """
    if os.name == 'nt' and executable.lower().endswith(('.bat', '.cmd')):
        return ['cmd.exe', '/c', executable]
    return [executable]


def resolve_executable(
    names: Iterable[str],
    *,
    override: str | None = None,
    label: str = 'ejecutable',
    hint: str = '',
) -> list[str]:
    """Ubica una herramienta externa: primero el override explicito, luego el PATH.

    Unifica lo que en los scripts eran tres funciones casi iguales
    (`resolve_flutter_cmd`, `resolve_flet_cmd`, `resolve_android_tool`): cada una
    repetia el mismo "mira la variable, si no mira el PATH, si no error".
    """
    if override and override.strip():
        path = Path(override.strip()).expanduser()
        if not path.is_file():
            raise TaskError(f"La ruta configurada de {label} no existe: {path}")
        return as_argv(str(path))

    found = which_any(names)
    if not found:
        extra = f" {hint}" if hint else ''
        raise TaskError(f"No se encontro {label} en el PATH.{extra}")
    return as_argv(found)


def spawn(
    argv: Argv,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    detached: bool = False,
) -> subprocess.Popen:
    """Arranca un proceso con la salida unificada y lista para leer linea a linea."""
    creation = _NO_WINDOW
    if detached and os.name == 'nt':
        creation |= subprocess.CREATE_NEW_PROCESS_GROUP

    return subprocess.Popen(
        [str(a) for a in argv],
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **env} if env else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
        creationflags=creation,
        start_new_session=detached and os.name != 'nt',
    )


def stream(
    argv: Argv,
    *,
    on_line: LineSink,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    cancel: threading.Event | None = None,
    register: Callable[[subprocess.Popen], None] | None = None,
) -> int:
    """Corre un proceso volcando su salida linea a linea, cancelable.

    Reemplaza el `subprocess.run(...)` a secas de los scripts: alli la salida
    aparecia recien al terminar y no habia forma de frenar a mitad de camino.
    """
    proc = spawn(argv, cwd=cwd, env=env)
    if register:
        register(proc)

    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if cancel is not None and cancel.is_set():
                kill_tree(proc)
                raise Cancelled('Detenido por el usuario.')
            line = raw.rstrip('\r\n')
            if line:
                on_line(line)
        return proc.wait()
    except Cancelled:
        raise
    except BaseException:
        kill_tree(proc)
        raise
    finally:
        if proc.stdout and not proc.stdout.closed:
            proc.stdout.close()


def capture(
    argv: Argv,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> str:
    """Corre un proceso y devuelve su salida. Para consultas cortas, no para builds."""
    try:
        result = subprocess.run(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise TaskError(f"No se encontro el ejecutable: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TaskError(f"El comando excedio {timeout}s: {format_argv(argv)}") from exc

    if check and result.returncode != 0:
        detalle = (result.stderr or result.stdout or '').strip()
        raise TaskError(f"Fallo ({result.returncode}): {format_argv(argv)}\n{detalle}")
    return (result.stdout or '').strip()


def kill_tree(proc: subprocess.Popen, *, grace: float = 5.0) -> None:
    """Termina el proceso y sus hijos, de abajo hacia arriba (PLAN.md §7, caso 6).

    Un launcher que vigila archivos y relanza a su hijo deja el puerto ocupado si
    solo se mata al padre; `taskkill /T` y el grupo de procesos POSIX se encargan
    del arbol completo.
    """
    if proc.poll() is not None:
        return

    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                capture_output=True,
                creationflags=_NO_WINDOW,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        proc.terminate()

    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        proc.kill()
