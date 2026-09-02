from __future__ import annotations
import threading
from typing import Callable

from PySide6.QtCore import QThread, Signal

from core.context import TaskContext
from core.envfile import Config
from core.errors import Cancelled, MissingConfig, TaskError
from core.projects import Project


class TaskRunner(QThread):
    """Corre una capacidad de verdad, en un hilo aparte.

    Puentea los cuatro canales del `TaskContext` hacia la interfaz. Tres son de
    ida y viajan como senales sueltas (`log`, `note`, `progress`); el cuarto,
    `ask`, es de ida y vuelta: la tarea se queda esperando la respuesta.

    Ese cuarto es el que obliga a esta maquinaria. Un dialogo Qt solo puede
    abrirse en el hilo de la interfaz, pero quien pregunta es este hilo, asi que
    `_ask` emite la senal y se duerme sobre un `Event` hasta que el hilo de la
    interfaz llame a `provide_answer`. Se espera en tandas cortas y no de una
    vez para que `cancel()` pueda cortar tambien con el dialogo abierto: el boton
    de Detener todavia no existe en la UI, pero cuando exista no debe encontrarse
    con una tarea dormida para siempre esperando una respuesta que nadie dio.
    """
    logged = Signal(str, str)
    noted = Signal(str)
    ask_requested = Signal(str, bool, bool, str)
    # url, etiqueta, se abre en navegador, estado. Lo emite `ctx.serve()` dos
    # veces: al anunciar la URL y cuando el puerto contesta de verdad. La
    # segunda llega desde el hilo que sondea el puerto, no desde este — una
    # senal Qt entre hilos se entrega igual, en cola (docs/launchers.md 2.2).
    serve_requested = Signal(str, str, bool, str)
    finished_ok = Signal(bool)

    def __init__(self, capability_id: str, project: Project, func: Callable,
                 kwargs: dict, parent=None):
        super().__init__(parent)
        self._capability_id = capability_id
        self._project = project
        self._func = func
        self._kwargs = kwargs
        self._ctx: TaskContext | None = None
        self._answer = ''
        self._answered = threading.Event()

    # --- puente de preguntas ------------------------------------------------

    def _ask(self, question: str, danger: bool, secret: bool, expect: str) -> str:
        """Pregunta desde el hilo de la tarea y espera la respuesta de la UI."""
        self._answer = ''
        self._answered.clear()
        self.ask_requested.emit(question, danger, secret, expect)
        while not self._answered.wait(0.1):
            self._raise_if_cancelled()
        # Tambien despues de salir del bucle: `cancel()` levanta el Event para
        # despertar a la tarea, asi que sin este segundo control la cancelacion
        # se leeria como una respuesta vacia — es decir, como un "no" — y la
        # tarea seguiria corriendo el resto de sus pasos.
        self._raise_if_cancelled()
        return self._answer

    def _raise_if_cancelled(self) -> None:
        if self._ctx is not None and self._ctx.cancelled:
            raise Cancelled('Detenido por el usuario.')

    def provide_answer(self, answer: str) -> None:
        """La respuesta del dialogo. La llama el hilo de la interfaz."""
        self._answer = answer
        self._answered.set()

    def cancel(self) -> None:
        """Detiene la tarea, incluso si esta esperando una respuesta.

        El apagado corre en un hilo aparte porque quien llama es la interfaz
        (cerrar la pestana, apretar Detener) y los ganchos de
        `TaskContext.on_cancel` pueden tardar un segundo o dos — un emulador
        pidiendole a adb que se cierre. Nada de eso debe congelar la ventana.
        """
        self._answered.set()
        if self._ctx is None:
            return
        self._ctx._cancel.set()   # inmediato: los bucles largos ya lo ven
        threading.Thread(target=self._ctx.cancel, daemon=True).start()

    # --- ejecucion ----------------------------------------------------------

    def run(self) -> None:
        ctx = TaskContext(
            capability_id=self._capability_id,
            project=self._project,
            config=Config.for_project(self._project.path),
            log_sink=lambda msg, level: self.logged.emit(msg, level),
            ask_sink=self._ask,
            note_sink=lambda entry: self.noted.emit(entry),
            serve_sink=lambda url, label, web, state: self.serve_requested.emit(
                url, label, web, state),
        )
        self._ctx = ctx
        try:
            self._func(ctx, **self._kwargs)
        except Cancelled:
            ctx.warn('Detenido por el usuario.')
            self._done(False)
            return
        except (TaskError, MissingConfig) as exc:
            ctx.error(str(exc))
            self._done(False)
            return
        except Exception as exc:  # nunca dejar morir el hilo en silencio
            ctx.error(f'Error inesperado: {exc}')
            self._done(False)
            return
        self._done(True)

    def _done(self, ok: bool) -> None:
        """Cierre unico de la corrida.

        Los endpoints se borran aca y no en cada `finally` de cada launcher: el
        que publico la URL fue el contexto, y una URL que ya no sirve nada no
        debe seguir ofrecida a la SPA que arranque despues.
        """
        if self._ctx is not None:
            self._ctx.release_endpoints()
        self.finished_ok.emit(ok)
