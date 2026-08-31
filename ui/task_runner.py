from __future__ import annotations
from typing import Callable

from PySide6.QtCore import QThread, Signal

from core.context import TaskContext
from core.envfile import Config
from core.errors import Cancelled, MissingConfig, TaskError
from core.projects import Project


class TaskRunner(QThread):
    """Corre UNA capacidad atomica de verdad, en un hilo aparte.

    Primer conector real de la app: hasta ahora `TabPanel._run` solo
    simulaba (PLAN.md 10). Sirve para una capacidad simple — sin pasos, sin
    dialogos de confirmacion — que es el perfil de la primera tanda que se
    conecta (`clean_artifacts`). Una compuesta con `ctx.confirm()`/`ctx.ask()`
    de verdad va a necesitar puentear tambien `ask_sink` con una senal
    bloqueante; no hace falta hasta que se conecte la primera de esas.
    """
    logged = Signal(str, str)
    finished_ok = Signal(bool)

    def __init__(self, capability_id: str, project: Project, func: Callable,
                 kwargs: dict, parent=None):
        super().__init__(parent)
        self._capability_id = capability_id
        self._project = project
        self._func = func
        self._kwargs = kwargs

    def run(self) -> None:
        ctx = TaskContext(
            capability_id=self._capability_id,
            project=self._project,
            config=Config.for_project(self._project.path),
            log_sink=lambda msg, level: self.logged.emit(msg, level),
        )
        try:
            self._func(ctx, **self._kwargs)
        except Cancelled:
            ctx.warn('Detenido por el usuario.')
            self.finished_ok.emit(False)
            return
        except (TaskError, MissingConfig) as exc:
            ctx.error(str(exc))
            self.finished_ok.emit(False)
            return
        except Exception as exc:  # nunca dejar morir el hilo en silencio
            ctx.error(f'Error inesperado: {exc}')
            self.finished_ok.emit(False)
            return
        self.finished_ok.emit(True)
