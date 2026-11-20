"""HTTP through the app's one QNetworkAccessManager, blocking.

Tasks run in their own thread and read top to bottom. The manager lives
in the interface thread: a call sends its request there through a
queued signal and waits on a queue for the parts of the answer
(ADR-0089). No widgets and no signals leave this module.
"""

from __future__ import annotations

import queue
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from PySide6.QtCore import QByteArray, QLocale, QObject, QThread, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# How often a waiting call checks whether it was asked to stop.
_STOP_CHECK_S = 0.2

# transversal.md of canone, «Reintentos»: a network failure, a 502, a
# 503 or a 504 is retried up to three times, with exponential backoff
# and full jitter, and only an idempotent request.
RETRIES = 3
BACKOFF_S = 0.5
_IDEMPOTENT = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"})
_RETRY_STATUSES = frozenset({502, 503, 504})
_Error = QNetworkReply.NetworkError
# A transfer timeout ends the reply with `OperationCanceledError`, the
# same as `abort()`: a stop is told apart by `should_stop`.
_NETWORK_FAILURES = frozenset(
    {
        _Error.ConnectionRefusedError,
        _Error.RemoteHostClosedError,
        _Error.HostNotFoundError,
        _Error.TimeoutError,
        _Error.OperationCanceledError,
        _Error.TemporaryNetworkFailureError,
        _Error.NetworkSessionFailedError,
        _Error.UnknownNetworkError,
    }
)


@dataclass(frozen=True)
class _Chunk:
    data: bytes


@dataclass(frozen=True)
class _Progress:
    done: int
    total: int


@dataclass(frozen=True)
class _End:
    error: QNetworkReply.NetworkError
    status: int | None
    message: str

    @property
    def retryable(self) -> bool:
        """Whether «Reintentos» retries this failure."""
        return self.error in _NETWORK_FAILURES or self.status in _RETRY_STATUSES


type _Event = _Chunk | _Progress | _End


@dataclass(eq=False)
class _Job:
    """One attempt: its request, and the queue its answer arrives on."""

    request: QNetworkRequest
    verb: bytes
    body: QByteArray
    events: queue.Queue[_Event] = field(default_factory=queue.Queue[_Event])
    reply: QNetworkReply | None = None


class _Network(QObject):
    """The app's one manager, living in the interface thread."""

    send = Signal(object)
    stop = Signal(object)

    def __init__(self) -> None:
        """Create the manager, which frees each reply when it ends."""
        super().__init__()
        self._manager = QNetworkAccessManager(self)
        self._manager.setAutoDeleteReplies(True)
        self.send.connect(self.start_job)
        self.stop.connect(self.abort_job)

    @Slot(object)
    def start_job(self, job: _Job) -> None:
        """Send the job's request and route its reply to its queue."""
        reply = self._manager.sendCustomRequest(job.request, job.verb, job.body)
        job.reply = reply

        def read() -> None:
            job.events.put(_Chunk(bytes(reply.readAll().data())))

        def progress(done: int, total: int) -> None:
            job.events.put(_Progress(done, total))

        def finish() -> None:
            # The manager deletes the reply after this: nothing may
            # touch it later.
            read()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            job.reply = None
            job.events.put(_End(reply.error(), status, reply.errorString()))

        reply.readyRead.connect(read)
        reply.downloadProgress.connect(progress)
        reply.finished.connect(finish)

    @Slot(object)
    def abort_job(self, job: _Job) -> None:
        """Abort the job's reply, unless it already ended."""
        if job.reply is not None:
            job.reply.abort()


_network: _Network | None = None


def start() -> None:
    """Create the app's one manager in this thread, the interface's."""
    global _network
    if _network is not None:
        raise RuntimeError("HTTP is already started.")
    _network = _Network()


def request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 30.0,
) -> bytes:
    """Return the body of the answer, or raise `OSError`."""
    chunks: list[bytes] = []
    _transfer(url, method, headers, body, timeout, chunks.append, chunks.clear)
    return b"".join(chunks)


def download(
    url: str,
    on_chunk: Callable[[bytes], object],
    *,
    on_restart: Callable[[], object],
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    timeout: float = 60.0,
) -> None:
    """Pass the answer to `on_chunk` as it arrives, or raise `OSError`.

    `timeout` counts time without data, not the whole transfer: an SDK
    takes minutes to download. A retry starts over, and `on_restart`
    tells the caller to drop what it got. When `should_stop` says so
    the transfer aborts and returns, and the caller decides what that
    means.
    """
    _transfer(url, "GET", None, None, timeout, on_chunk, on_restart, on_progress, should_stop)


def _transfer(
    url: str,
    method: str,
    headers: Mapping[str, str] | None,
    body: bytes | None,
    timeout: float,
    on_chunk: Callable[[bytes], object],
    on_restart: Callable[[], object],
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    # Retry the attempt as «Reintentos» says, starting over each time.
    network = _caller_network()
    target = QNetworkRequest(QUrl(url))
    target.setTransferTimeout(int(timeout * 1000))
    # transversal.md of canone, «Idiomas»: the interface language.
    target.setRawHeader(b"Accept-Language", QLocale().bcp47Name().encode("ascii"))
    for name, value in (headers or {}).items():
        target.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))
    stop = should_stop or _never

    for attempt in range(RETRIES + 1):
        job = _Job(target, method.encode("ascii"), QByteArray(body or b""))
        network.send.emit(job)
        end, delivered = _wait(network, job, on_chunk, on_progress, stop)
        if end is None or end.error == _Error.NoError:
            return
        if method not in _IDEMPOTENT or attempt == RETRIES or not end.retryable:
            raise OSError(end.message)
        if delivered:
            on_restart()
        if _sleep(random.uniform(0, BACKOFF_S * 2**attempt), stop):
            return


def _caller_network() -> _Network:
    # The manager, checking that the caller can wait for it.
    if _network is None:
        raise RuntimeError("HTTP is not started: main.py starts it.")
    if QThread.currentThread() == _network.thread():
        raise RuntimeError("HTTP blocks its caller: call it from a task's thread.")
    return _network


def _wait(
    network: _Network,
    job: _Job,
    on_chunk: Callable[[bytes], object],
    on_progress: Callable[[int, int], None] | None,
    stop: Callable[[], bool],
) -> tuple[_End | None, bool]:
    # Deliver the job's events until it ends. Returns its end, or None
    # if it was stopped, and whether it delivered any part.
    delivered = False
    stopped = False
    next_check = time.monotonic() + _STOP_CHECK_S
    while True:
        try:
            event: _Event | None = job.events.get(timeout=_STOP_CHECK_S)
        except queue.Empty:
            event = None
        if not stopped and time.monotonic() >= next_check:
            next_check = time.monotonic() + _STOP_CHECK_S
            if stop():
                stopped = True
                network.stop.emit(job)
        match event:
            case _End():
                return (None if stopped else event), delivered
            case _Chunk(data=data) if data and not stopped:
                delivered = True
                on_chunk(data)
            case _Progress(done=done, total=total) if on_progress is not None and not stopped:
                on_progress(done, total)
            case _:
                pass


def _never() -> bool:
    # The stop of a call that cannot be stopped.
    return False


def _sleep(seconds: float, stop: Callable[[], bool]) -> bool:
    # Wait between attempts. Returns whether it was asked to stop.
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        if stop():
            return True
        time.sleep(min(_STOP_CHECK_S, left))
    return stop()
