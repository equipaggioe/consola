"""HTTP through the app's one manager, against a local server."""

import http.server
import json
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import override

import pytest
from PySide6.QtCore import QLocale
from pytestqt.qtbot import QtBot

from app.api import http as consola_http

SIZE = 3_000_000


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answer the paths the tests ask for."""

    # How many times each path was asked for.
    calls: Counter[str] = Counter()

    def _answer(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        """Answer a text, a large body, a failure or a missing page."""
        self.calls[self.path] += 1
        first = self.calls[self.path] == 1
        if self.path == "/text":
            self._answer(200, f"ua={self.headers['User-Agent']}".encode())
        elif self.path == "/language":
            self._answer(200, str(self.headers["Accept-Language"]).encode())
        elif self.path == "/large":
            self._answer(200, b"x" * SIZE)
        elif self.path == "/unavailable":
            self._answer(503, b"busy")
        elif self.path == "/refused":
            self._answer(400, b'{"success": false, "errors": [{"code": 6003}]}')
        elif self.path == "/unavailable-once":
            self._answer(503, b"busy") if first else self._answer(200, b"ok")
        elif self.path == "/slow-once":
            time.sleep(2 if first else 0)
            self._answer(200, b"ok")
        elif self.path == "/cut-once":
            self._cut() if first else self._answer(200, b"x" * SIZE)
        else:
            self._answer(404, b"missing")

    def _cut(self) -> None:
        # Promise the large body and close after half of it.
        self.send_response(200)
        self.send_header("Content-Length", str(SIZE))
        self.end_headers()
        self.wfile.write(b"y" * (SIZE // 2))
        self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802
        """Echo the method's body and a header, or fail."""
        self.calls[self.path] += 1
        length = int(self.headers["Content-Length"])
        echo = {"body": self.rfile.read(length).decode(), "auth": self.headers["Authorization"]}
        if self.path == "/unavailable":
            self._answer(503, b"busy")
        else:
            self._answer(200, json.dumps(echo).encode())

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def server() -> Iterator[str]:
    """Serve on a free local port and return its URL."""
    _Handler.calls.clear()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join()


@pytest.fixture(autouse=True)
def network(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Start a fresh manager in this thread, with short waits."""
    monkeypatch.setattr(consola_http, "_network", None)
    monkeypatch.setattr(consola_http, "BACKOFF_S", 0.01)
    consola_http.start()


def _in_task[T](qtbot: QtBot, work: Callable[[], T]) -> T:
    # Run the call in its own thread, as a task does, while this one
    # serves the manager.
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(work)
        qtbot.waitUntil(future.done, timeout=30_000)
        return future.result()


def test_a_get_returns_the_body_and_sends_the_headers(qtbot: QtBot, server: str) -> None:
    """A GET returns the body and sends the headers."""
    body = _in_task(
        qtbot, lambda: consola_http.request(f"{server}/text", headers={"User-Agent": "consola"})
    )
    assert body == b"ua=consola"


def test_a_request_sends_the_interface_language(qtbot: QtBot, server: str) -> None:
    """A request sends the interface language in `Accept-Language`."""
    body = _in_task(qtbot, lambda: consola_http.request(f"{server}/language"))
    assert body.decode() == QLocale().bcp47Name()


def test_a_post_sends_its_body_and_headers(qtbot: QtBot, server: str) -> None:
    """A POST sends its body and headers."""
    body = _in_task(
        qtbot,
        lambda: consola_http.request(
            f"{server}/post", method="POST", headers={"Authorization": "Bearer t"}, body=b"data"
        ),
    )
    assert json.loads(body) == {"body": "data", "auth": "Bearer t"}


def test_an_http_error_raises_oserror(qtbot: QtBot, server: str) -> None:
    """An HTTP error raises OSError, without retrying a 404."""
    with pytest.raises(OSError, match="404|not found|Not Found"):
        _in_task(qtbot, lambda: consola_http.request(f"{server}/none"))
    assert _Handler.calls["/none"] == 1


def test_an_http_error_keeps_the_status_and_the_body(qtbot: QtBot, server: str) -> None:
    """An error status raises `HttpError` with what the server said."""
    with pytest.raises(consola_http.HttpError) as caught:
        _in_task(qtbot, lambda: consola_http.request(f"{server}/refused"))
    assert caught.value.status == 400
    assert json.loads(caught.value.body) == {"success": False, "errors": [{"code": 6003}]}


def test_a_refused_connection_raises_oserror(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused connection raises OSError."""
    # Windows takes seconds to give up on each attempt.
    monkeypatch.setattr(consola_http, "RETRIES", 0)
    with pytest.raises(OSError, match=r"\w"):
        _in_task(qtbot, lambda: consola_http.request("http://127.0.0.1:9/", timeout=5))


def test_a_503_is_retried_until_it_answers(qtbot: QtBot, server: str) -> None:
    """A 503 is retried, and the answer has only the last body."""
    body = _in_task(qtbot, lambda: consola_http.request(f"{server}/unavailable-once"))
    assert body == b"ok"
    assert _Handler.calls["/unavailable-once"] == 2


def test_a_503_gives_up_after_three_retries(qtbot: QtBot, server: str) -> None:
    """A 503 that does not go away fails after three retries."""
    with pytest.raises(OSError, match=r"\w"):
        _in_task(qtbot, lambda: consola_http.request(f"{server}/unavailable"))
    assert _Handler.calls["/unavailable"] == 1 + consola_http.RETRIES


def test_a_post_is_not_retried(qtbot: QtBot, server: str) -> None:
    """A POST is not idempotent: a 503 fails at once."""
    with pytest.raises(OSError, match=r"\w"):
        _in_task(
            qtbot,
            lambda: consola_http.request(f"{server}/unavailable", method="POST", body=b"x"),
        )
    assert _Handler.calls["/unavailable"] == 1


def test_a_transfer_timeout_is_retried(qtbot: QtBot, server: str) -> None:
    """An answer that does not arrive in time is asked for again."""
    body = _in_task(qtbot, lambda: consola_http.request(f"{server}/slow-once", timeout=0.5))
    assert body == b"ok"
    assert _Handler.calls["/slow-once"] == 2


def test_a_download_streams_and_reports_progress(qtbot: QtBot, server: str) -> None:
    """A download streams the whole body and reports its progress."""
    chunks: list[bytes] = []
    progress: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    _in_task(
        qtbot,
        lambda: consola_http.download(
            f"{server}/large", chunks.append, on_restart=chunks.clear, on_progress=on_progress
        ),
    )
    assert sum(len(c) for c in chunks) == SIZE
    assert progress[-1] == (SIZE, SIZE)


def test_a_cut_download_starts_over(qtbot: QtBot, server: str) -> None:
    """A download cut midway drops what it got and starts over."""
    chunks: list[bytes] = []
    restarts: list[int] = []

    def restart() -> None:
        restarts.append(sum(len(c) for c in chunks))
        chunks.clear()

    _in_task(
        qtbot,
        lambda: consola_http.download(f"{server}/cut-once", chunks.append, on_restart=restart),
    )
    assert restarts
    assert restarts[0] > 0
    assert b"".join(chunks) == b"x" * SIZE


def test_stopping_a_download_returns_without_error(qtbot: QtBot, server: str) -> None:
    """Stopping a download returns without an error."""
    _in_task(
        qtbot,
        lambda: consola_http.download(
            f"{server}/large",
            lambda _chunk: None,
            on_restart=lambda: None,
            should_stop=lambda: True,
        ),
    )


def test_the_interface_thread_cannot_wait_for_an_answer(server: str) -> None:
    """A call from the manager's own thread fails instead of hanging."""
    with pytest.raises(RuntimeError, match="task's thread"):
        consola_http.request(f"{server}/text")


def test_the_manager_starts_only_once() -> None:
    """Starting HTTP twice is a mistake that shows."""
    with pytest.raises(RuntimeError, match="already started"):
        consola_http.start()
