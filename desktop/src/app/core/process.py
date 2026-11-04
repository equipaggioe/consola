from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from app.core.errors import Cancelled, TaskError
from app.core.host import HOST

Argv = Sequence[str]
LineSink = Callable[[str], None]


def format_argv(argv: Argv) -> str:
    """Linea legible para el log. No es para volver a ejecutar: es para leer."""
    return " ".join(f'"{a}"' if " " in str(a) else str(a) for a in argv)


def which_any(names: Iterable[str]) -> str | None:
    """Primer ejecutable de `names` que exista en el PATH."""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def as_argv(executable: str) -> list[str]:
    """Envuelve los shims `.bat`/`.cmd` de Windows, que no son ejecutables reales."""
    return HOST.wrap_script(executable)


def resolve_executable(
    names: Iterable[str],
    *,
    override: str | None = None,
    label: str = "ejecutable",
    hint: str = "",
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
        extra = f" {hint}" if hint else ""
        raise TaskError(f"No se encontro {label} en el PATH.{extra}")
    return as_argv(found)


def spawn(
    argv: Argv,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    detached: bool = False,
    stdin: bool = False,
) -> subprocess.Popen:
    """Arranca un proceso con la salida unificada y lista para leer linea a linea.

    `stdin=True` le deja la entrada abierta para escribirle; si no, lee EOF.
    """
    return subprocess.Popen(
        [str(a) for a in argv],
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **env} if env else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **HOST.spawn_options(detached=detached),
    )


def bind_to_app(proc: subprocess.Popen) -> None:
    """El proceso muere con Consola, aunque Consola se cierre de golpe o se caiga.

    Un tunel `ssh -L` que sobrevive a su Consola sigue ocupando el puerto local
    y la proxima conexion entra por el.

    No es para todo hijo: un emulador muerto de golpe deja el AVD a medio
    escribir, y ese se apaga por adb (`core/tasks/emulators.py`).
    """
    HOST.bind_to_app(proc)


def stream(
    argv: Argv,
    *,
    on_line: LineSink,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    cancel: threading.Event | None = None,
    register: Callable[[subprocess.Popen], None] | None = None,
    stdin_text: str | None = None,
) -> int:
    """Corre un proceso volcando su salida linea a linea, cancelable.

    Reemplaza el `subprocess.run(...)` a secas de los scripts: alli la salida
    aparecia recien al terminar y no habia forma de frenar a mitad de camino.

    `stdin_text` se escribe entero al arrancar y la entrada se cierra: es para
    lo que el programa lee de stdin (la contraseña de `sudo -S`, las lineas de
    `credentials.py`), nunca se vuelca al log.
    """
    proc = spawn(argv, cwd=cwd, env=env, stdin=stdin_text is not None)
    if register:
        register(proc)
    if stdin_text is not None:
        assert proc.stdin is not None
        proc.stdin.write(stdin_text)
        proc.stdin.close()

    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if cancel is not None and cancel.is_set():
                kill_tree(proc)
                raise Cancelled("Detenido por el usuario.")
            line = raw.rstrip("\r\n")
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


def converse(
    argv: Argv,
    *,
    on_line: LineSink,
    answers: Sequence[tuple[str, str]],
    cancel: threading.Event | None = None,
    register: Callable[[subprocess.Popen], None] | None = None,
) -> int:
    """Corre un proceso que pregunta, y contesta cada pregunta cuando aparece.

    `answers` son pares (texto de la pregunta, respuesta), en el orden en que
    el programa pregunta. La respuesta se escribe recien cuando la pregunta
    aparece en la salida: escrita antes, una terminal remota (`ssh -tt`) la
    repite y queda en el log, y `getpass` la descarta. La pregunta no termina
    en salto de linea, asi que la salida se lee por bloques y no por lineas.
    Las respuestas nunca pasan por `on_line`.
    """
    proc = subprocess.Popen(
        [str(a) for a in argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        **HOST.spawn_options(detached=False),
    )
    if register:
        register(proc)
    pendientes = list(answers)
    resto = ""
    try:
        assert proc.stdout is not None and proc.stdin is not None
        fd = proc.stdout.fileno()
        while True:
            if cancel is not None and cancel.is_set():
                kill_tree(proc)
                raise Cancelled("Detenido por el usuario.")
            bloque = os.read(fd, 4096)
            if not bloque:
                break
            resto += bloque.decode("utf-8", errors="replace").replace("\r", "")
            *lineas, resto = resto.split("\n")
            for linea in lineas:
                if linea:
                    on_line(linea)
            if pendientes and pendientes[0][0] in resto:
                on_line(resto)
                resto = ""
                proc.stdin.write((pendientes.pop(0)[1] + "\n").encode("utf-8"))
                proc.stdin.flush()
        if resto:
            on_line(resto)
        return proc.wait()
    except Cancelled:
        raise
    except BaseException:
        kill_tree(proc)
        raise
    finally:
        for canal in (proc.stdout, proc.stdin):
            if canal and not canal.closed:
                canal.close()


def capture(
    argv: Argv,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
    stdin_text: str | None = None,
) -> str:
    """Corre un proceso y devuelve su salida. Para consultas cortas, no para builds.

    `stdin` va a DEVNULL igual que en `spawn`: una consulta corta no lee teclado,
    y sin cerrarlo hereda el stdin del proceso padre. Desde la terminal eso no se
    nota, pero corriendo dentro de la GUI ese handle heredado deja a `ssh` (que
    reenvia stdin al comando remoto) esperando un EOF que no llega, y la consulta
    se cuelga hasta el timeout aunque el comando remoto ya haya terminado.
    `stdin_text` es lo que la consulta lee, y la entrada se cierra despues.
    """
    entrada = {"stdin": subprocess.DEVNULL} if stdin_text is None else {"input": stdin_text}
    try:
        result = subprocess.run(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            **entrada,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **HOST.run_options(),
        )
    except FileNotFoundError as exc:
        raise TaskError(f"No se encontro el ejecutable: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TaskError(f"El comando excedio {timeout}s: {format_argv(argv)}") from exc

    if check and result.returncode != 0:
        detalle = (result.stderr or result.stdout or "").strip()
        raise TaskError(f"Fallo ({result.returncode}): {format_argv(argv)}\n{detalle}")
    return (result.stdout or "").strip()


def feed(argv: Argv, *, stdin_text: str, timeout: float | None = None) -> str:
    """Corre un proceso escribiendole a stdin y devuelve todo lo que imprimio.

    `stream` y `capture` cierran stdin a proposito: una tarea de fondo esperando
    teclado es un cuelgue silencioso. La excepcion es `sdkmanager --licenses`,
    que pregunta una por una y no tiene bandera para aceptar; sin respuesta lee
    EOF y no acepta ninguna.
    """
    try:
        result = subprocess.run(
            [str(a) for a in argv],
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **HOST.run_options(),
        )
    except FileNotFoundError as exc:
        raise TaskError(f"No se encontro el ejecutable: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TaskError(f"El comando excedio {timeout}s: {format_argv(argv)}") from exc
    return ((result.stdout or "") + (result.stderr or "")).strip()


def kill_tree(proc: subprocess.Popen, *, grace: float = 5.0) -> None:
    """Termina el proceso y sus hijos, de abajo hacia arriba (ADR-0005).

    Un launcher que vigila archivos y relanza a su hijo deja el puerto ocupado si
    solo se mata al padre; `taskkill /T` y el grupo de procesos POSIX se encargan
    del arbol completo.
    """
    if proc.poll() is not None:
        return

    try:
        HOST.kill_group(proc)
    except (OSError, subprocess.SubprocessError):
        proc.terminate()

    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        proc.kill()
