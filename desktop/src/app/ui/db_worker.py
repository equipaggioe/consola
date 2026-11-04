"""The database explorer's thread (ADR-0015).

psycopg does not allow two queries at once on the same connection, and
the interface cannot wait for the network: one thread owns the
connection and serves requests in a queue. Each answer comes back with
its request's id, and the view discards those it no longer wants, for
example when the table changed before the previous answer arrived.

The connection is its own and not that of the `explore_db` task: a
psycopg connection does not pass between threads. The task owns the
tunnel; this thread owns the SQL session.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any, cast, override

from psycopg import Connection
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QApplication

from app.core import db_explorer, db_models
from app.core.errors import TaskError

_STOP = object()
# A live reference to each thread until it truly ends: dropping a
# QThread that still runs brings the application down. Stopping does not
# wait, since a slow query can take up to `statement_timeout`, so the
# thread stays here until it exits.
_alive: set["DbWorker"] = set()
_quit_hooked = False


class DbWorker(QThread):
    """The thread that owns the explorer's connection."""

    result = Signal(int, str, object)  # request id, kind, result
    failed = Signal(int, str, str)  # request id, kind, message

    def __init__(
        self, url: str, server_root: Path | None = None, parent: QObject | None = None
    ) -> None:
        """Keep the URL; the connection opens on the first request."""
        super().__init__(parent)
        self._url = url
        self._server_root = server_root
        # Models are reread only if a .py changed
        # (`db_models.signature`): importing them launches a Python, and
        # the comparison is requested each time the tab shows.
        self._models: tuple[tuple[tuple[str, int], ...], list[db_models.ModelTable]] | None = None
        self._queue: queue.Queue[tuple[int, str, dict[str, Any]] | object] = queue.Queue()
        self._next_id = 0
        self._conn: Connection | None = None
        self._stopping = False
        _alive.add(self)
        self.finished.connect(lambda: _alive.discard(self))
        global _quit_hooked
        app = QApplication.instance()
        if app is not None and not _quit_hooked:
            app.aboutToQuit.connect(_stop_all)
            _quit_hooked = True

    # --- requests (interface thread) ---
    def request(self, kind: str, **kwargs: Any) -> int:
        """Queue a request and return its id."""
        self._next_id += 1
        self._queue.put((self._next_id, kind, kwargs))
        return self._next_id

    def stop(self) -> None:
        """Cut what is running and exit, not waiting: see `_alive`."""
        self._stopping = True
        conn = self._conn
        if conn is not None:
            try:
                conn.cancel_safe(timeout=2.0)
            except Exception:
                pass
        self._queue.put(_STOP)

    # --- thread ---
    @override
    def run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is _STOP or self._stopping:
                    return
                req_id, kind, kwargs = cast(tuple[int, str, dict[str, Any]], item)
                try:
                    payload = self._handle(kind, kwargs)
                except Exception as exc:
                    if not self._stopping:
                        self.failed.emit(req_id, kind, _message(exc))
                    continue
                if not self._stopping:
                    self.result.emit(req_id, kind, payload)
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def _connection(self) -> Connection:
        """Return the connection, reopened if it fell.

        A restarted Postgres or a reconnected tunnel should not force
        closing the tab.
        """
        if self._conn is None or self._conn.closed or self._conn.broken:
            self._conn = db_explorer.open_readonly(self._url)
        return self._conn

    def _handle(self, kind: str, kwargs: dict[str, Any]) -> object:
        conn = self._connection()
        if kind == "relations":
            return db_explorer.list_relations(conn)
        if kind == "describe":
            return db_explorer.describe(conn, kwargs["relation"])
        if kind == "rows":
            return db_explorer.fetch_rows(conn, **kwargs)
        if kind == "count":
            return db_explorer.count_exact(conn, **kwargs)
        if kind == "models":
            return self._compare(conn)
        raise TaskError(f"Pedido desconocido: {kind}")

    def _compare(self, conn: Connection) -> db_models.Comparison:
        if self._server_root is None:
            raise TaskError("La pestaña no tiene repo: no hay modelos con qué comparar.")
        signature = db_models.signature(self._server_root)
        if self._models is None or self._models[0] != signature:
            self._models = (signature, db_models.read_models(self._server_root))
        return db_models.compare(
            db_explorer.list_relations(conn), db_explorer.all_columns(conn), self._models[1]
        )


def _message(exc: Exception) -> str:
    """Return the error's first line, without psycopg's dump."""
    text = str(exc).strip()
    if not text:
        return type(exc).__name__
    first = text.splitlines()[0]
    lowered = first.lower()
    if "permission denied" in lowered:
        return f"Sin permiso para el rol de la app: {first}"
    if "canceling statement due to statement timeout" in lowered:
        seconds = db_explorer.STATEMENT_TIMEOUT_MS // 1000
        return f"La consulta tardó más de {seconds} s y se canceló."
    return first


def _stop_all() -> None:
    for worker in list(_alive):
        worker.stop()
    for worker in list(_alive):
        worker.wait(2500)
