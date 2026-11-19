"""Choose free ports and wait for servers to answer."""

from __future__ import annotations

import socket
import threading
import time
from urllib.parse import urlsplit

from app.services.errors import TaskError


def is_free(port: int, *, host: str = "") -> bool:
    """Return whether the port is free on `host`, or on both without it.

    Windows lets `0.0.0.0` listen on a port another holds on `127.0.0.1`
    (an `ssh -L` tunnel), and whoever enters through `127.0.0.1` reaches
    the old one.
    """
    for addr in [host] if host else ["0.0.0.0", "127.0.0.1"]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((addr, port))
            except OSError:
                return False
    return True


def resolve_port(preferred: int, *, search: bool = True, label: str = "puerto") -> int:
    """Return `preferred` if free; if not and `search`, the next free.

    The port is session state (ADR-0009): whoever starts the service
    publishes it and whoever starts later reads it, without touching the
    disk.
    """
    if is_free(preferred):
        return preferred
    if not search:
        raise TaskError(f"El {label} {preferred} esta ocupado.")

    for port in range(preferred + 1, 65536):
        if is_free(port):
            return port
    raise TaskError("No quedan puertos libres.")


def is_serving(port: int, *, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    """Return whether something accepts connections on that port now.

    It differs from `is_free`, which asks whether one can listen there.
    This asks whether someone answers already: a chosen port with no
    server yet gives `False` on both.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_until_serving(
    port: int,
    *,
    host: str = "127.0.0.1",
    timeout: float = 60.0,
    cancel: threading.Event | None = None,
) -> bool:
    """Wait until the server truly answers, and return whether it did.

    Choosing the port (`resolve_port`) is not serving: between the two
    there is a `pnpm run dev` that takes two seconds or a uvicorn that
    takes ten. Without this wait, the tab's browser would open the URL
    before it exists and show an error that is not one (ADR-0008).

    `cancel` is the task's `threading.Event`: stopping it must not leave
    this loop alive until the timeout.
    """
    limit = time.monotonic() + timeout
    while time.monotonic() < limit:
        if cancel is not None and cancel.is_set():
            return False
        if is_serving(port, host=host):
            return True
        time.sleep(0.25)
    return False


def split_host_port(url: str) -> tuple[str, int]:
    """Return a URL's host and port, with its scheme's default port.

    `localhost` becomes `127.0.0.1` because the probe opens an IPv4
    socket: resolving `localhost` may give `::1` first, and a server
    that only listens on IPv4 would read as down.
    """
    parts = urlsplit(url)
    host = parts.hostname or "127.0.0.1"
    if host in ("localhost", "0.0.0.0", "::"):
        host = "127.0.0.1"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return host, port
