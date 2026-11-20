"""TaskContext: log, run, confirm, ask, note, cancel."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from app.services import ports, process, session
from app.services.envfile import Config
from app.services.errors import Cancelled, MissingConfig, TaskError
from app.services.projects import Project
from app.services.session import Endpoint

if TYPE_CHECKING:
    from app.services.ssh import Tunnel

__all__ = ["Level", "TaskContext", "TaskError", "Cancelled", "MissingConfig"]


class Level:
    """The levels of a log line."""

    INFO = "info"
    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    CMD = "cmd"


LogSink = Callable[[str, str], None]
# question, answer shape, dangerous, text to type to accept. The shape
# travels explicitly because it alone decides which dialog the UI opens,
# and deducing it from the other fields is not enough: an ordinary
# `ask`, such as a folder's name, is not secret and asks for no typing,
# and without this datum it read like a confirmation and came out as a
# yes/no.
ASK_YES_NO = "si_no"  # confirmation: two buttons
ASK_TEXT = "texto"  # a datum the task cannot deduce
ASK_SECRET = "secreto"  # the same, hidden while typing
# Closing the text dialog is not leaving it empty, and an empty string
# for both made them indistinguishable: `create_avd` takes empty as «use
# the derived name», so an Escape created the AVD anyway. The UI answers
# this on cancel and `ask()` turns it into `Cancelled`.
ASK_CANCELLED = "\x00cancelado"
AskSink = Callable[[str, str, bool, str], str]
ProgressSink = Callable[[int, int, str], None]
NoteSink = Callable[[str], None]
# url, label, opens in browser, state. What the tab needs to draw its
# endpoint bar and decide whether to offer the browser view.
ServeSink = Callable[[str, str, bool, str], None]

_YES = ("s", "si", "sí", "y", "yes", "ok")
_MASK = "******"


@dataclass
class TaskContext:
    """All a capability receives.

    Nothing at level 0 prints to stdout or reads stdin: everything goes
    through here, so the same function serves a tab's console, a UI-less
    test and an inner step of a composite.
    """

    capability_id: str
    project: Project | None = None
    config: Config = field(default_factory=lambda: Config())
    log_sink: LogSink | None = None
    ask_sink: AskSink | None = None
    progress_sink: ProgressSink | None = None
    note_sink: NoteSink | None = None
    serve_sink: ServeSink | None = None

    _asked: dict[str, str] = field(default_factory=dict, repr=False)
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _children: list[subprocess.Popen[str]] = field(default_factory=list, repr=False)
    _secrets: set[str] = field(default_factory=set, repr=False)
    _stoppers: list[Callable[[], None]] = field(default_factory=list, repr=False)
    _served: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _published: list[tuple[str, str]] = field(default_factory=list, repr=False)
    _tunnels: list[Tunnel] = field(default_factory=list, repr=False)

    # --- project root ---

    @property
    def root(self) -> Path:
        """Return the project's root, or stop if none is open."""
        if self.project is None:
            raise TaskError(QCoreApplication.translate("TaskContext", "No hay proyecto abierto."))
        return Path(self.project.path)

    @property
    def project_name(self) -> str:
        """Return the project's name, or stop if none is open."""
        if self.project is None:
            raise TaskError(QCoreApplication.translate("TaskContext", "No hay proyecto abierto."))
        return self.project.name

    def path(self, *parts: str) -> Path:
        """Return a path inside the project."""
        return self.root.joinpath(*parts)

    # --- log ---

    def log(self, msg: str, level: str = Level.INFO) -> None:
        """Write a line to the log, masking secrets."""
        if self.log_sink:
            self.log_sink(self.mask(msg), level)

    def info(self, msg: str) -> None:
        """Log an informative line."""
        self.log(msg, Level.INFO)

    def ok(self, msg: str) -> None:
        """Log a success."""
        self.log(msg, Level.OK)

    def warn(self, msg: str) -> None:
        """Log a warning."""
        self.log(msg, Level.WARN)

    def error(self, msg: str) -> None:
        """Log an error."""
        self.log(msg, Level.ERROR)

    def step(self, step_id: str) -> None:
        """Write the heading of a step inside a composite.

        A recipe's log stays flat, with one heading per step and no
        sub-tabs (ADR-0005).

        It receives the step's ID and resolves the label from the
        catalog, where the panel's checkbox already has it. A step that
        is no one's checkbox prints as is: not every step of the log has
        to be a panel decision.
        """
        self.log(f"--- {self._step_label(step_id)}", Level.INFO)

    def _step_label(self, step_id: str) -> str:
        from app.services.registry import registry

        cap = registry.get_capability(self.capability_id)
        if cap is not None:
            for step in cap.steps:
                if step.id == step_id:
                    return step.label
        return step_id

    # --- secrets ---

    def guard(self, *values: str) -> None:
        """Mark values to mask in the console and the saved log."""
        for value in values:
            if value and len(value) >= 4:
                self._secrets.add(value)

    def mask(self, text: str) -> str:
        """Return the text with marked values masked."""
        for secret in self._secrets:
            text = text.replace(secret, _MASK)
        return text

    # --- running ---

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
        echo: bool = True,
        stdin_text: str | None = None,
    ) -> int:
        """Run an external binary with live streaming and cancellation.

        `stdin_text` goes to the process's input and not the log.
        """
        self.raise_if_cancelled()
        if echo:
            self.log(process.format_argv(argv), Level.CMD)

        code = process.stream(
            argv,
            on_line=lambda line: self.log(line, _guess_level(line)),
            cwd=cwd or self._default_cwd(),
            env=env,
            cancel=self._cancel,
            register=self._children.append,
            stdin_text=stdin_text,
        )
        if check and code != 0:
            raise TaskError(
                QCoreApplication.translate(
                    "TaskContext", "El comando termino con codigo {0}."
                ).format(code)
            )
        return code

    def converse(
        self, argv: Sequence[str], answers: Sequence[tuple[str, str]], *, check: bool = True
    ) -> int:
        """Run a program, answering each question as it appears.

        See `process.converse`. Answers do not pass through the log.
        """
        self.raise_if_cancelled()
        self.log(process.format_argv(argv), Level.CMD)
        for _, answer in answers:
            self.guard(answer)
        code = process.converse(
            argv,
            on_line=lambda line: self.log(line, _guess_level(line)),
            answers=answers,
            cancel=self._cancel,
            register=self._children.append,
        )
        if check and code != 0:
            raise TaskError(
                QCoreApplication.translate(
                    "TaskContext", "El comando termino con codigo {0}."
                ).format(code)
            )
        return code

    def capture(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        check: bool = True,
    ) -> str:
        """Run a short command and return its output, unlogged."""
        self.raise_if_cancelled()
        return process.capture(
            argv,
            cwd=cwd or self._default_cwd(),
            env=env,
            timeout=timeout,
            check=check,
        )

    def detach(
        self, argv: Sequence[str], *, cwd: Path | str | None = None
    ) -> subprocess.Popen[str]:
        """Start a background service, which outlives its tab."""
        self.log(process.format_argv(argv), Level.CMD)
        return process.spawn(argv, cwd=cwd or self._default_cwd(), detached=True)

    def _default_cwd(self) -> str | None:
        return self.project.path if self.project else None

    # --- endpoints ---

    def serve(
        self, url: str, *, key: str = "", label: str = "", web: bool = True, wait: float = 90.0
    ) -> None:
        """Announce that this task will serve at that URL.

        What a launcher delivers is not its log but an endpoint: the
        console is the by-product (ADR-0008). Calling this before
        starting the process does three things at once: the tab's bar
        with its URL, the embedded browser view, and the «ready» signal
        dependent launchers wait for.

        It is called BEFORE `ctx.run()`, which blocks until the process
        dies: the port was already chosen (`ports.resolve_port`), so the
        URL is known without sniffing vite's or uvicorn's output.
        """
        endpoint_key = key or self.capability_id
        project = self.project.name if self.project else ""
        endpoint = session.Endpoint(
            key=endpoint_key, url=url, label=label or endpoint_key, web=web
        )
        if project:
            session.publish_endpoint(project, endpoint)
        self._served.append((project, endpoint_key))
        self.log(
            QCoreApplication.translate("TaskContext", "Disponible en {0} (arrancando...)").format(
                url
            ),
            Level.INFO,
        )
        self._emit_serve(endpoint)
        if wait > 0:
            threading.Thread(
                target=self._watch_endpoint, args=(endpoint, wait), daemon=True
            ).start()

    def _watch_endpoint(self, endpoint: Endpoint, timeout: float) -> None:
        """Probe the port until it answers, in a separate thread.

        Separate because whoever calls `serve()` goes straight on to
        `ctx.run()`, which does not return until the process dies:
        waiting here, the URL would never get past «starting».
        """
        host, port = ports.split_host_port(endpoint.url)
        ready = ports.wait_until_serving(port, host=host, timeout=timeout, cancel=self._cancel)
        if self._cancel.is_set():
            return
        project = self.project.name if self.project else ""
        state = session.READY if ready else session.DOWN
        if project:
            session.mark_endpoint(project, endpoint.key, state)
        endpoint.state = state
        if ready:
            self.log(
                QCoreApplication.translate("TaskContext", "Listo: {0}").format(endpoint.url),
                Level.OK,
            )
        else:
            self.warn(
                QCoreApplication.translate(
                    "TaskContext", "{0} no contesto despues de {1}s."
                ).format(endpoint.url, int(timeout))
            )
        self._emit_serve(endpoint)

    def _emit_serve(self, endpoint: Endpoint) -> None:
        if self.serve_sink:
            self.serve_sink(endpoint.url, endpoint.label, endpoint.web, endpoint.state)

    def endpoint(self, key: str, *, wait: float = 0.0) -> Endpoint | None:
        """Return another task's endpoint in this project, if any."""
        if self.project is None:
            return None
        return session.wait_for_endpoint(self.project.name, key, wait)

    def release_endpoints(self) -> None:
        """Erase the endpoints and values this task published.

        Whoever runs it calls this at the end: a URL that serves nothing
        should not stay offered.
        """
        for project, endpoint_key in self._served:
            if project:
                session.forget_endpoint(project, endpoint_key)
        self._served.clear()
        for project, endpoint_key in self._published:
            session.forget(project, endpoint_key)
        self._published.clear()

    def publish(self, key: str, value: object) -> None:
        """Leave a value in the project's session while the task lives.

        It is the other half of `serve()` for what cannot show in the
        bar: the URL with a password the explorer needs to open its own
        connection (ADR-0015). It stays in memory and erases by itself
        when the task ends.
        """
        if self.project is None:
            return
        session.publish(self.project.name, key, value)
        self._published.append((self.project.name, key))

    # --- interaction ---

    def confirm(self, question: str, *, danger: bool = False, expect: str = "") -> bool:
        """Ask whether to go on. `expect` requires typing that text."""
        if self.ask_sink is None:
            return not danger
        answer = self.ask_sink(question, ASK_YES_NO, danger, expect)
        if expect:
            return answer.strip() == expect
        return answer.strip().lower() in _YES

    def ask(self, prompt: str, *, secret: bool = False) -> str:
        """Ask for a datum and return the answer.

        Closing the dialog cancels.
        """
        if self.ask_sink is None:
            raise TaskError(
                QCoreApplication.translate(
                    "TaskContext", "Hace falta un dato que nadie puede responder: {0}"
                ).format(prompt)
            )
        answer = self.ask_sink(prompt, ASK_SECRET if secret else ASK_TEXT, False, "")
        if answer == ASK_CANCELLED:
            raise Cancelled(
                QCoreApplication.translate(
                    "TaskContext", "Cancelado: no se dio el dato que la accion pedia."
                )
            )
        if secret:
            self.guard(answer)
        return answer

    def ask_once(self, prompt: str, *, secret: bool = False) -> str:
        """Like `ask`, but remember the answer for the rest of the run.

        A composite opening several root connections would ask for the
        same password once per atomic capability: each is independent on
        purpose and none knows the others asked. The memory lives in
        this run's context, shared with `child()`, and dies with it; it
        goes to no file.
        """
        if prompt not in self._asked:
            self._asked[prompt] = self.ask(prompt, secret=secret)
        return self._asked[prompt]

    def progress(self, done: int, total: int, label: str = "") -> None:
        """Report the progress of a long step."""
        if self.progress_sink:
            self.progress_sink(done, total, label)

    def note(self, entry: str) -> None:
        """Leave an automatic entry in the project's log book.

        See docs/arquitectura/30_riesgos_y_pendientes.md.
        """
        if self.note_sink:
            self.note_sink(self.mask(entry))

    # --- configuration ---

    def require_config(self, *keys: str) -> None:
        """Fail before starting, not midway, if config is missing."""
        missing = self.config.missing(*keys)
        if missing:
            raise MissingConfig(missing)

    # --- cancellation ---

    @property
    def cancelled(self) -> bool:
        """Return whether the task was stopped."""
        return self._cancel.is_set()

    def on_cancel(self, stopper: Callable[[], None]) -> None:
        """Register a clean shutdown for when the task is stopped.

        Killing the process serves almost everything, but not what saves
        state on closing: the emulator has to be asked with `adb emu
        kill` and given a moment, or the AVD stays half written
        (ADR-0028). The hook runs BEFORE `kill_tree`, which then almost
        always finds the process already ended.
        """
        self._stoppers.append(stopper)

    def cancel(self) -> None:
        """Stop the task: run its hooks and kill its processes."""
        self._cancel.set()
        for stopper in list(self._stoppers):
            try:
                stopper()
            except Exception:
                # a clean shutdown that fails does not prevent the dirty
                # one
                pass
        for child in list(self._children):
            process.kill_tree(child)

    def kill_children(self) -> None:
        """Kill the task's live processes without stopping it.

        The `ctx.run` waiting for them returns with its code and the
        task goes on. It is the relaunch of `run_python_app`'s watcher.
        """
        for child in list(self._children):
            process.kill_tree(child)

    def hold_tunnel(self, tunnel: Tunnel) -> None:
        """Note an SSH tunnel of this task.

        Clearing the tab stops it if it has a live one
        (`widgets/tab_panel.py::_on_cleared`).
        """
        self._tunnels.append(tunnel)

    @property
    def has_tunnel(self) -> bool:
        """Return whether the task holds a live tunnel."""
        return any(t.alive for t in self._tunnels)

    def wait_cancelled(self, timeout: float | None = None) -> bool:
        """Sleep until stopped or `timeout`, and say if stopped.

        What lives without a process holding it, such as an open
        connection, uses it to wait for the tab to close.
        """
        return self._cancel.wait(timeout)

    def raise_if_cancelled(self) -> None:
        """Raise `Cancelled` if the task was stopped."""
        if self._cancel.is_set():
            raise Cancelled(QCoreApplication.translate("TaskContext", "Detenido por el usuario."))

    def child(self, capability_id: str) -> "TaskContext":
        """Return a context for an inner step.

        Same console, same cancellation.

        A composite calls its atomic capabilities with this and not a
        new context: the user sees one log and one Stop button
        (ADR-0005).
        """
        return TaskContext(
            capability_id=capability_id,
            project=self.project,
            config=self.config,
            log_sink=self.log_sink,
            ask_sink=self.ask_sink,
            progress_sink=self.progress_sink,
            note_sink=self.note_sink,
            serve_sink=self.serve_sink,
            _asked=self._asked,
            _cancel=self._cancel,
            _served=self._served,
            _published=self._published,
            _children=self._children,
            _secrets=self._secrets,
            _stoppers=self._stoppers,
            _tunnels=self._tunnels,
        )


def _guess_level(line: str) -> str:
    """Color an external binary's output by its own tag."""
    head = line.lstrip().lower()
    if head.startswith(("error", "[error", "fatal")):
        return Level.ERROR
    if head.startswith(("warn", "[warn")):
        return Level.WARN
    if head.startswith(("[ok", "success")):
        return Level.OK
    return Level.INFO
