"""HTTP through QNetworkAccessManager, against a local server."""

import http.server
import json
import threading
from collections.abc import Iterator
from typing import override

import pytest
from PySide6.QtWidgets import QApplication

from app.core import http as consola_http

SIZE = 3_000_000


class _Handler(http.server.BaseHTTPRequestHandler):
    """Answer the paths the tests ask for."""

    def _answer(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        """Answer a text, a large body or a missing page."""
        if self.path == "/text":
            self._answer(200, f"ua={self.headers['User-Agent']}".encode())
        elif self.path == "/large":
            self._answer(200, b"x" * SIZE)
        else:
            self._answer(404, b"missing")

    def do_POST(self) -> None:  # noqa: N802
        """Echo the method's body and a header."""
        length = int(self.headers["Content-Length"])
        echo = {"body": self.rfile.read(length).decode(), "auth": self.headers["Authorization"]}
        self._answer(200, json.dumps(echo).encode())

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def server() -> Iterator[str]:
    """Serve on a free local port and return its URL."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_a_get_returns_the_body_and_sends_the_headers(qapp: QApplication, server: str) -> None:
    """A GET returns the body and sends the headers."""
    body = consola_http.request(f"{server}/text", headers={"User-Agent": "consola"})
    assert body == b"ua=consola"


def test_a_post_sends_its_body_and_headers(qapp: QApplication, server: str) -> None:
    """A POST sends its body and headers."""
    body = consola_http.request(
        f"{server}/post", method="POST", headers={"Authorization": "Bearer t"}, body=b"data"
    )
    assert json.loads(body) == {"body": "data", "auth": "Bearer t"}


def test_an_http_error_raises_oserror(qapp: QApplication, server: str) -> None:
    """An HTTP error raises OSError."""
    with pytest.raises(OSError, match="404|not found|Not Found"):
        consola_http.request(f"{server}/none")


def test_a_refused_connection_raises_oserror(qapp: QApplication) -> None:
    """A refused connection raises OSError."""
    with pytest.raises(OSError, match=r"\w"):
        consola_http.request("http://127.0.0.1:9/", timeout=5)


def test_a_download_streams_and_reports_progress(qapp: QApplication, server: str) -> None:
    """A download streams the whole body and reports its progress."""
    chunks: list[bytes] = []
    progress: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    consola_http.download(f"{server}/large", chunks.append, on_progress=on_progress)
    assert sum(len(c) for c in chunks) == SIZE
    assert progress[-1] == (SIZE, SIZE)


def test_stopping_a_download_returns_without_error(qapp: QApplication, server: str) -> None:
    """Stopping a download returns without an error."""
    consola_http.download(f"{server}/large", lambda _chunk: None, should_stop=lambda: True)


def test_it_works_inside_a_worker_thread(qapp: QApplication, server: str) -> None:
    """A task thread gets its answer through its own event loop."""
    result: list[bytes] = []

    def work() -> None:
        result.append(consola_http.request(f"{server}/text", headers={"User-Agent": "t"}))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join(timeout=30)
    assert result == [b"ua=t"]
