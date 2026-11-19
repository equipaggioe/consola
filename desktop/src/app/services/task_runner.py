"""The thread a capability runs in."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, override

from PySide6.QtCore import QObject, QThread, Signal

from app.services import params_store
from app.services.context import TaskContext
from app.services.errors import Cancelled, MissingConfig, TaskError
from app.services.projects import Project


class TaskRunner(QThread):
    """Run a capability for real, in a separate thread.

    It bridges the four channels of `TaskContext` to the interface.
    Three go one way as loose signals (`log`, `note`, `progress`); the
    fourth, `ask`, goes both ways: the task stays waiting for the
    answer.

    That fourth forces this machinery. A Qt dialog can only open in the
    interface thread, but this thread asks, so `_ask` emits the signal
    and sleeps on an `Event` until the interface thread calls
    `provide_answer`. It waits in short rounds so `cancel()` can also
    cut with the dialog open: the Stop button does not exist in the UI
    yet, but when it does it must not meet a task asleep forever on an
    answer nobody gave.
    """

    logged = Signal(str, str)
    noted = Signal(str)
    # question, shape, dangerous, expect; then url, label, opens in
    # browser, state. `ctx.serve()` emits it twice: when announcing the
    # URL and when the port truly answers. The second comes from the
    # thread probing the port, not this one: a Qt signal between threads
    # is still delivered, queued (ADR-0008).
    ask_requested = Signal(str, str, bool, str)
    serve_requested = Signal(str, str, bool, str)
    finished_ok = Signal(bool)

    def __init__(
        self,
        capability_id: str,
        project: Project,
        func: Callable[..., Any],
        kwargs: dict[str, Any],
        parent: QObject | None = None,
    ) -> None:
        """Keep what the run needs; the thread starts with `start()`."""
        super().__init__(parent)
        self._capability_id = capability_id
        self._project = project
        self._func = func
        self._kwargs = kwargs
        self._ctx: TaskContext | None = None
        # What the function returned. Almost no capability uses it,
        # since they deliver their log or endpoint, but those declaring
        # `opens_repo` return the folder of the repo they left on disk,
        # and the window needs it to open it as a tab.
        self.result: object = None
        self._answer = ""
        self._answered = threading.Event()

    # --- question bridge ---

    def _ask(self, question: str, shape: str, danger: bool, expect: str) -> str:
        """Ask from the task's thread and wait for the UI's answer."""
        self._answer = ""
        self._answered.clear()
        self.ask_requested.emit(question, shape, danger, expect)
        while not self._answered.wait(0.1):
            self._raise_if_cancelled()
        # Also after leaving the loop: `cancel()` raises the Event to
        # wake the task, so without this second check the cancellation
        # would read as an empty answer, that is, a «no», and the task
        # would run the rest of its steps.
        self._raise_if_cancelled()
        return self._answer

    def _raise_if_cancelled(self) -> None:
        if self._ctx is not None and self._ctx.cancelled:
            raise Cancelled("Detenido por el usuario.")

    def provide_answer(self, answer: str) -> None:
        """Give the dialog's answer. The interface thread calls this."""
        self._answer = answer
        self._answered.set()

    def cancel(self) -> None:
        """Stop the task, even if it is waiting for an answer.

        The shutdown runs in a separate thread because the interface
        calls it (closing the tab, pressing Stop) and
        `TaskContext.on_cancel` hooks can take a second or two, such as
        an emulator asking adb to close. None of that should freeze the
        window.
        """
        self._answered.set()
        if self._ctx is None:
            return
        self._ctx._cancel.set()  # immediate: long loops see it already
        threading.Thread(target=self._ctx.cancel, daemon=True).start()

    @property
    def has_tunnel(self) -> bool:
        """Return whether the task holds a live tunnel."""
        return self._ctx is not None and self._ctx.has_tunnel

    # --- running ---

    @override
    def run(self) -> None:
        ctx = TaskContext(
            capability_id=self._capability_id,
            project=self._project,
            config=params_store.task_config(self._project.path),
            log_sink=lambda msg, level: self.logged.emit(msg, level),
            ask_sink=self._ask,
            note_sink=lambda entry: self.noted.emit(entry),
            serve_sink=lambda url, label, web, state: self.serve_requested.emit(
                url, label, web, state
            ),
        )
        self._ctx = ctx
        try:
            self.result = self._func(ctx, **self._kwargs)
        except Cancelled:
            ctx.warn("Detenido por el usuario.")
            self._done(False)
            return
        except (TaskError, MissingConfig) as exc:
            ctx.error(str(exc))
            self._done(False)
            return
        except Exception as exc:  # never let the thread die in silence
            ctx.error(f"Error inesperado: {exc}")
            self._done(False)
            return
        self._done(True)

    def _done(self, ok: bool) -> None:
        """Close the run, once.

        Endpoints are erased here and not in each launcher's `finally`:
        the context published the URL, and a URL that serves nothing
        should not stay offered to the SPA that starts next.
        """
        if self._ctx is not None:
            self._ctx.release_endpoints()
        self.finished_ok.emit(ok)
