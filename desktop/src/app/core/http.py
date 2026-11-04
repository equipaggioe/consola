"""HTTP through QNetworkAccessManager, blocking the calling thread.

Tasks run in their own thread and read top to bottom, so each call runs
a local event loop until the reply ends. Qt comes in only for this, as
in `core/tasks/raster.py`: no widgets and no signals leave this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from PySide6.QtCore import QByteArray, QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# How often a transfer checks whether it was asked to stop.
_STOP_CHECK_MS = 200


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
    _transfer(url, method, headers, body, timeout, chunks.append)
    return b"".join(chunks)


def download(
    url: str,
    on_chunk: Callable[[bytes], object],
    *,
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    timeout: float = 60.0,
) -> None:
    """Pass the answer to `on_chunk` as it arrives, or raise `OSError`.

    `timeout` counts time without data, not the whole transfer: an SDK
    takes minutes to download. When `should_stop` says so the transfer
    aborts and returns, and the caller decides what that means.
    """
    _transfer(url, "GET", None, None, timeout, on_chunk, on_progress, should_stop)


def _transfer(
    url: str,
    method: str,
    headers: Mapping[str, str] | None,
    body: bytes | None,
    timeout: float,
    on_chunk: Callable[[bytes], object],
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    if QCoreApplication.instance() is None:
        raise OSError("HTTP needs a running QCoreApplication.")
    target = QNetworkRequest(QUrl(url))
    target.setTransferTimeout(int(timeout * 1000))
    for name, value in (headers or {}).items():
        target.setRawHeader(name.encode("utf-8"), value.encode("utf-8"))

    manager = QNetworkAccessManager()
    reply = manager.sendCustomRequest(target, method.encode("ascii"), QByteArray(body or b""))
    loop = QEventLoop()
    stopped = False

    def read() -> None:
        on_chunk(bytes(reply.readAll().data()))

    def check_stop() -> None:
        nonlocal stopped
        if should_stop is not None and should_stop():
            stopped = True
            reply.abort()

    reply.readyRead.connect(read)
    reply.finished.connect(loop.quit)
    if on_progress is not None:
        reply.downloadProgress.connect(on_progress)
    timer = QTimer()
    timer.setInterval(_STOP_CHECK_MS)
    timer.timeout.connect(check_stop)
    timer.start()
    loop.exec()
    timer.stop()

    error = reply.error()
    message = reply.errorString()
    reply.deleteLater()
    if error != QNetworkReply.NetworkError.NoError and not stopped:
        raise OSError(message)
