from __future__ import annotations
import queue

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from core import db_explorer
from core.errors import TaskError

"""
El hilo del explorador de base (docs/explorador-db.md 4).

psycopg no admite dos consultas a la vez sobre la misma conexion, y la interfaz
no puede esperar a la red: un solo hilo es dueno de la conexion y atiende los
pedidos en fila. Cada respuesta vuelve con el id de su pedido, y la vista
descarta las que ya no le interesan —cambiaste de tabla antes de que llegara la
anterior—.

La conexion es propia y no la de la tarea `explore_db`: una conexion psycopg no
se pasa entre hilos. La tarea es duena del tunel; este hilo, de la sesion SQL.
"""

_STOP = object()
# Referencia viva a cada hilo hasta que termine de verdad: soltar un QThread que
# todavia corre tumba la aplicacion. Detener no espera —una consulta lenta puede
# tardar hasta el `statement_timeout`— asi que el hilo sigue aca hasta salir.
_alive: set['DbWorker'] = set()
_quit_hooked = False


class DbWorker(QThread):
    result = Signal(int, str, object)   # id del pedido, tipo, resultado
    failed = Signal(int, str, str)      # id del pedido, tipo, mensaje

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url
        self._queue: queue.Queue = queue.Queue()
        self._next_id = 0
        self._conn = None
        self._stopping = False
        _alive.add(self)
        self.finished.connect(lambda: _alive.discard(self))
        global _quit_hooked
        app = QApplication.instance()
        if app is not None and not _quit_hooked:
            app.aboutToQuit.connect(_stop_all)
            _quit_hooked = True

    # --- pedidos (hilo de la interfaz) -----------------------------------------
    def request(self, kind: str, **kwargs) -> int:
        self._next_id += 1
        self._queue.put((self._next_id, kind, kwargs))
        return self._next_id

    def stop(self) -> None:
        """Corta lo que este corriendo y sale. No espera: ver `_alive`."""
        self._stopping = True
        conn = self._conn
        if conn is not None:
            try:
                conn.cancel_safe(timeout=2.0)
            except Exception:
                pass
        self._queue.put(_STOP)

    # --- hilo --------------------------------------------------------------------
    def run(self) -> None:
        try:
            while True:
                item = self._queue.get()
                if item is _STOP or self._stopping:
                    return
                req_id, kind, kwargs = item
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

    def _connection(self):
        """La conexion, reabierta si se cayo: un Postgres reiniciado o un tunel
        que se reconecto no deberian obligar a cerrar la pestana."""
        if self._conn is None or self._conn.closed or self._conn.broken:
            self._conn = db_explorer.open_readonly(self._url)
        return self._conn

    def _handle(self, kind: str, kwargs: dict):
        conn = self._connection()
        if kind == 'relations':
            return db_explorer.list_relations(conn)
        if kind == 'describe':
            return db_explorer.describe(conn, kwargs['relation'])
        if kind == 'rows':
            return db_explorer.fetch_rows(conn, **kwargs)
        if kind == 'count':
            return db_explorer.count_exact(conn, **kwargs)
        raise TaskError(f'Pedido desconocido: {kind}')


def _message(exc: Exception) -> str:
    """La primera linea del error, sin el volcado de psycopg: la vista lo
    muestra en un renglon."""
    text = str(exc).strip()
    if not text:
        return type(exc).__name__
    first = text.splitlines()[0]
    lowered = first.lower()
    if 'permission denied' in lowered:
        return f'Sin permiso para el rol de la app: {first}'
    if 'canceling statement due to statement timeout' in lowered:
        segundos = db_explorer.STATEMENT_TIMEOUT_MS // 1000
        return f'La consulta tardó más de {segundos} s y se canceló.'
    return first


def _stop_all() -> None:
    for worker in list(_alive):
        worker.stop()
    for worker in list(_alive):
        worker.wait(2500)
