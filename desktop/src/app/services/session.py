"""Session state: what one task publishes for another, in memory.

It is what the backend obtained *in this run*, such as its port, which
is not configuration (ADR-0009). It lives in memory per project and goes
away when the app closes. None of it is written to disk.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

# The scope for what belongs to the machine and to no repo: the serial
# of the emulator just started serves any project.
MACHINE = "@machine"

_lock = threading.Lock()
_state: dict[str, dict[str, Any]] = {}


def publish(project: str, key: str, value: object) -> None:
    """Save a value for the session."""
    with _lock:
        _state.setdefault(project, {})[key] = value


def read(project: str, key: str, default: Any = None) -> Any:
    """Return a value of the session, or `default`."""
    with _lock:
        return _state.get(project, {}).get(key, default)


def require(project: str, key: str) -> Any:
    """Return a value of the session, or raise KeyError."""
    value = read(project, key)
    if value is None:
        raise KeyError(key)
    return value


def forget(project: str, key: str = "") -> None:
    """Forget one key, or the whole project without one."""
    with _lock:
        if not key:
            _state.pop(project, None)
        else:
            _state.get(project, {}).pop(key, None)


def snapshot(project: str) -> dict[str, object]:
    """Return a copy of what the project has published."""
    with _lock:
        return dict(_state.get(project, {}))


# --- endpoints ---
#
# What a launcher leaves available: a URL with a state. It is the part
# of session state the interface watches all the time, in the tab's
# endpoint bar and embedded browser, and it also chains launchers: the
# SPA and the terminal wait for the backend to answer instead of
# trusting the order the buttons were pressed in (ADR-0011).

STARTING = "starting"
READY = "ready"
DOWN = "down"

_ENDPOINTS = "@endpoints"


@dataclass
class Endpoint:
    """A URL published by a live task."""

    key: str
    url: str
    label: str = ""
    web: bool = True
    state: str = STARTING
    _ready: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def is_ready(self) -> bool:
        """Return whether it answers."""
        return self.state == READY


def publish_endpoint(project: str, endpoint: Endpoint) -> None:
    """Publish an endpoint."""
    with _lock:
        _state.setdefault(project, {}).setdefault(_ENDPOINTS, {})[endpoint.key] = endpoint


def mark_endpoint(project: str, key: str, state: str) -> None:
    """Change an endpoint's state, and wake whoever waits for it."""
    endpoint = read_endpoint(project, key)
    if endpoint is None:
        return
    endpoint.state = state
    if state == READY:
        endpoint._ready.set()
    else:
        endpoint._ready.clear()


def read_endpoint(project: str, key: str) -> "Endpoint | None":
    """Return the endpoint, if published."""
    with _lock:
        return _state.get(project, {}).get(_ENDPOINTS, {}).get(key)


def endpoints(project: str) -> list["Endpoint"]:
    """Return the project's endpoints."""
    with _lock:
        return list(_state.get(project, {}).get(_ENDPOINTS, {}).values())


def forget_endpoint(project: str, key: str) -> None:
    """Forget an endpoint."""
    with _lock:
        _state.get(project, {}).get(_ENDPOINTS, {}).pop(key, None)


def wait_for_endpoint(project: str, key: str, timeout: float = 0.0) -> "Endpoint | None":
    """Return the endpoint, waiting if it is still starting.

    Without `timeout` it does not wait: it answers what there is. That
    lets `serve_spa` work alike when the backend is already up (answers
    at once), when it is starting in another tab (waits) and when there
    is no backend at all (returns `None`, and the SPA goes on with its
    own config).
    """
    endpoint = read_endpoint(project, key)
    if endpoint is None or timeout <= 0 or endpoint.is_ready:
        return endpoint
    endpoint._ready.wait(timeout)
    return endpoint
