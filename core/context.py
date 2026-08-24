from __future__ import annotations
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from . import process
from .envfile import Config
from .errors import Cancelled, MissingConfig, TaskError
from .projects import Project

__all__ = ['Level', 'TaskContext', 'TaskError', 'Cancelled', 'MissingConfig']


class Level:
    INFO = 'info'
    OK = 'ok'
    WARN = 'warn'
    ERROR = 'error'
    CMD = 'cmd'


LogSink = Callable[[str, str], None]
AskSink = Callable[[str, bool, bool], str]
ProgressSink = Callable[[int, int, str], None]
NoteSink = Callable[[str], None]

_YES = ('s', 'si', 'sí', 'y', 'yes', 'ok')
_MASK = '******'


@dataclass
class TaskContext:
    """Lo unico que recibe una capacidad. Reemplaza los cuatro patrones que los
    scripts repetian sueltos: `print`, `subprocess.run`, `SystemExit` e `input`.

    Nada de nivel 0 imprime a stdout ni lee de stdin: todo pasa por aca, asi la
    misma funcion sirve para la consola de una pestana, para un test sin UI y
    para un paso interno de una capacidad compuesta.
    """
    capability_id: str
    project: Project | None = None
    config: Config = field(default_factory=lambda: Config())
    log_sink: LogSink | None = None
    ask_sink: AskSink | None = None
    progress_sink: ProgressSink | None = None
    note_sink: NoteSink | None = None

    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _children: list = field(default_factory=list, repr=False)
    _secrets: set = field(default_factory=set, repr=False)

    # --- raiz del proyecto -------------------------------------------------

    @property
    def root(self) -> Path:
        if self.project is None:
            raise TaskError('No hay proyecto abierto.')
        return Path(self.project.path)

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    # --- log ---------------------------------------------------------------

    def log(self, msg: str, level: str = Level.INFO) -> None:
        if self.log_sink:
            self.log_sink(self.mask(msg), level)

    def info(self, msg: str) -> None:
        self.log(msg, Level.INFO)

    def ok(self, msg: str) -> None:
        self.log(msg, Level.OK)

    def warn(self, msg: str) -> None:
        self.log(msg, Level.WARN)

    def error(self, msg: str) -> None:
        self.log(msg, Level.ERROR)

    def step(self, title: str) -> None:
        """Encabezado de un paso dentro de una compuesta.

        El log de una receta queda plano, con un encabezado por paso y sin
        sub-pestanas (PLAN.md 7, caso 8).
        """
        self.log(f'--- {title}', Level.INFO)

    # --- secretos ----------------------------------------------------------

    def guard(self, *values: str) -> None:
        """Marca valores para enmascararlos en la consola y en el log guardado."""
        for value in values:
            if value and len(value) >= 4:
                self._secrets.add(value)

    def mask(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, _MASK)
        return text

    # --- ejecucion ---------------------------------------------------------

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
        echo: bool = True,
    ) -> int:
        """Corre un binario externo con streaming en vivo y cancelacion."""
        self.raise_if_cancelled()
        if echo:
            self.log(process.format_argv(argv), Level.CMD)

        code = process.stream(
            argv,
            on_line=lambda line: self.log(line, _guess_level(line)),
            cwd=cwd or self._default_cwd(),
            env=env,
            cancel=self._cancel,
            register=self._children.append,
        )
        if check and code != 0:
            raise TaskError(f'El comando termino con codigo {code}.')
        return code

    def capture(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        check: bool = True,
    ) -> str:
        """Corre un comando corto y devuelve su salida, sin volcarla al log."""
        self.raise_if_cancelled()
        return process.capture(
            argv,
            cwd=cwd or self._default_cwd(),
            env=env,
            timeout=timeout,
            check=check,
        )

    def detach(self, argv: Sequence[str], *, cwd: Path | str | None = None) -> subprocess.Popen:
        """Arranca un proceso que sobrevive a su pestana (servicio de fondo, 7.2)."""
        self.log(process.format_argv(argv), Level.CMD)
        return process.spawn(argv, cwd=cwd or self._default_cwd(), detached=True)

    def _default_cwd(self) -> str | None:
        return self.project.path if self.project else None

    # --- interaccion -------------------------------------------------------

    def confirm(self, question: str, *, danger: bool = False, expect: str = '') -> bool:
        """Pregunta si seguir. `expect` exige escribir ese texto (destructivos, 7.5)."""
        if self.ask_sink is None:
            return not danger
        answer = self.ask_sink(question, danger, False)
        if expect:
            return answer.strip() == expect
        return answer.strip().lower() in _YES

    def ask(self, prompt: str, *, secret: bool = False) -> str:
        if self.ask_sink is None:
            raise TaskError(f'Hace falta un dato que nadie puede responder: {prompt}')
        answer = self.ask_sink(prompt, False, secret)
        if secret:
            self.guard(answer)
        return answer

    def progress(self, done: int, total: int, label: str = '') -> None:
        if self.progress_sink:
            self.progress_sink(done, total, label)

    def note(self, entry: str) -> None:
        """Deja una entrada automatica en la bitacora del proyecto (PLAN.md 8)."""
        if self.note_sink:
            self.note_sink(self.mask(entry))

    # --- configuracion -----------------------------------------------------

    def require_config(self, *keys: str) -> None:
        """Falla antes de empezar si falta configuracion, no a mitad de flujo."""
        missing = self.config.missing(*keys)
        if missing:
            raise MissingConfig(missing)

    # --- cancelacion -------------------------------------------------------

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        for child in list(self._children):
            process.kill_tree(child)

    def raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise Cancelled('Detenido por el usuario.')

    def child(self, capability_id: str) -> 'TaskContext':
        """Contexto para un paso interno: misma consola, misma cancelacion.

        Una compuesta llama a sus atomicas con esto, no con un contexto nuevo:
        el usuario ve un solo log y un solo boton de Detener (PLAN.md 7, caso 8).
        """
        return TaskContext(
            capability_id=capability_id,
            project=self.project,
            config=self.config,
            log_sink=self.log_sink,
            ask_sink=self.ask_sink,
            progress_sink=self.progress_sink,
            note_sink=self.note_sink,
            _cancel=self._cancel,
            _children=self._children,
            _secrets=self._secrets,
        )


def _guess_level(line: str) -> str:
    """Colorea la salida de un binario externo por su propia etiqueta."""
    head = line.lstrip().lower()
    if head.startswith(('error', '[error', 'fatal')):
        return Level.ERROR
    if head.startswith(('warn', '[warn')):
        return Level.WARN
    if head.startswith(('[ok', 'success')):
        return Level.OK
    return Level.INFO
