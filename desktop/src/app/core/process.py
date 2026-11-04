"""Run external binaries: stream, capture, kill."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from app.core.errors import Cancelled, TaskError
from app.core.host import HOST

Argv = Sequence[str]
LineSink = Callable[[str], None]


def format_argv(argv: Argv) -> str:
    """Return a line for the log: to read it, not to rerun it."""
    return " ".join(f'"{a}"' if " " in str(a) else str(a) for a in argv)


def which_any(names: Iterable[str]) -> str | None:
    """Return the first executable of `names` on the PATH."""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def as_argv(executable: str) -> list[str]:
    """Wrap Windows `.bat` and `.cmd` shims, not real executables."""
    return HOST.wrap_script(executable)


def resolve_executable(
    names: Iterable[str],
    *,
    override: str | None = None,
    label: str = "ejecutable",
    hint: str = "",
) -> list[str]:
    """Locate an external tool.

    The explicit override first, then the PATH.
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
) -> subprocess.Popen[str]:
    """Start a process with unified output, ready to read line by line.

    `stdin=True` leaves its input open to write to it; otherwise it
    reads EOF.
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


def bind_to_app(proc: subprocess.Popen[str]) -> None:
    """Make the process die with Consola, even if Consola crashes.

    An `ssh -L` tunnel that outlives its Consola keeps holding the local
    port, and the next connection goes through it.

    Not for every child: an emulator killed at once leaves the AVD half
    written, and that one shuts down through adb
    (`core/tasks/emulators.py`).
    """
    HOST.bind_to_app(proc)


def stream(
    argv: Argv,
    *,
    on_line: LineSink,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    cancel: threading.Event | None = None,
    register: Callable[[subprocess.Popen[str]], None] | None = None,
    stdin_text: str | None = None,
) -> int:
    """Run a process and stream its output line by line, cancellably.

    `stdin_text` is written whole at the start and the input closes: it
    is for what the program reads from stdin (the password of `sudo -S`,
    the lines of `credentials.py`), and it is never dumped to the log.
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
    register: Callable[[subprocess.Popen[str]], None] | None = None,
) -> int:
    """Run a process that asks, answering each question as it appears.

    `answers` are pairs of question text and answer, in the program's
    order. The answer is written only when the question appears in the
    output: written earlier, a remote terminal (`ssh -tt`) echoes it
    into the log and `getpass` discards it. The question ends without a
    line break, so output reads by blocks and not lines. Answers never
    pass through `on_line`.
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
    pending = list(answers)
    rest = ""
    try:
        assert proc.stdout is not None
        assert proc.stdin is not None
        fd = proc.stdout.fileno()
        while True:
            if cancel is not None and cancel.is_set():
                kill_tree(proc)
                raise Cancelled("Detenido por el usuario.")
            block = os.read(fd, 4096)
            if not block:
                break
            rest += block.decode("utf-8", errors="replace").replace("\r", "")
            *lines, rest = rest.split("\n")
            for line in lines:
                if line:
                    on_line(line)
            if pending and pending[0][0] in rest:
                on_line(rest)
                rest = ""
                proc.stdin.write((pending.pop(0)[1] + "\n").encode("utf-8"))
                proc.stdin.flush()
        if rest:
            on_line(rest)
        return proc.wait()
    except Cancelled:
        raise
    except BaseException:
        kill_tree(proc)
        raise
    finally:
        for channel in (proc.stdout, proc.stdin):
            if channel and not channel.closed:
                channel.close()


def capture(
    argv: Argv,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
    stdin_text: str | None = None,
) -> str:
    """Run a process and return its output.

    For short queries, not builds.

    `stdin` goes to DEVNULL as in `spawn`: a short query reads no
    keyboard, and unclosed it inherits the parent's stdin. From a
    terminal that goes unnoticed, but inside the GUI that inherited
    handle leaves `ssh`, which forwards stdin to the remote command,
    waiting for an EOF that never comes, and the query hangs until the
    timeout even though the remote command ended. `stdin_text` is what
    the query reads, and the input closes after it.
    """
    entry: dict[str, Any] = (
        {"stdin": subprocess.DEVNULL} if stdin_text is None else {"input": stdin_text}
    )
    try:
        result = subprocess.run(
            [str(a) for a in argv],
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **env} if env else None,
            **entry,
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
        detail = (result.stderr or result.stdout or "").strip()
        raise TaskError(f"Fallo ({result.returncode}): {format_argv(argv)}\n{detail}")
    return (result.stdout or "").strip()


def feed(argv: Argv, *, stdin_text: str, timeout: float | None = None) -> str:
    """Run a process writing to its stdin, and return all it printed.

    `stream` and `capture` close stdin on purpose: a background task
    waiting for a keyboard is a silent hang. The exception is
    `sdkmanager --licenses`, which asks one by one and has no flag to
    accept; without an answer it reads EOF and accepts none.
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


def kill_tree(proc: subprocess.Popen[str], *, grace: float = 5.0) -> None:
    """End the process and its children, bottom up (ADR-0005).

    A launcher that watches files and relaunches its child leaves the
    port taken if only the parent is killed; `taskkill /T` and the POSIX
    process group handle the whole tree.
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
