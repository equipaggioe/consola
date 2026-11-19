"""Run group.

The port is in-memory session state (`services/session.py`): whoever
starts the backend publishes it and whoever starts later reads it.

What a launcher delivers is not its log but an **endpoint**, a URL. So
they all call `ctx.serve()` as soon as they know their port, before
starting the process. The tab's bar, the embedded browser and the signal
the next launcher waits for all come from there (ADR-0008).

None of the `resolve_*` functions here is an atomic capability with a
button: they are the plumbing of those that are, like `_download` or
`_extract` inside `install_android_tools` (ADR-0004). `serve_backend` is
ONE atomic capability made of five functions.
"""

from __future__ import annotations

import threading
from pathlib import Path

from app.services import canone, envfile, fields, ports, runner, session, ssh, targets, toolchain
from app.services import database as db
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.registry import registry
from app.services.tasks import emulators
from app.services.toolchain import venv_python

SERVER_PORT = "SERVER_PORT"
BACKEND = "backend"  # key of the backend's endpoint in `services/session`

# How long a dependent launcher waits for the backend to answer.
# Generous because the case that matters is starting together
# (ADR-0011): uvicorn with --reload and a remote database through a
# tunnel takes a good few seconds.
BACKEND_WAIT = 90.0


# --- atomic ---


def resolve_server_port(ctx: TaskContext, preferred: int = 8000, search: bool = True) -> int:
    """Choose the backend's port and publish it for later tasks.

    Not a button: nobody asks to choose a port and nothing else. It is
    plumbing of `serve_backend`, which is one (ADR-0008).
    """
    port = ports.resolve_port(preferred, search=search, label="puerto del backend")
    session.publish(ctx.project_name, SERVER_PORT, port)
    ctx.info(f"Puerto del backend: {port}")
    return port


def backend_url(ctx: TaskContext, *, wait: float = 0.0, required: bool = True) -> str:
    """Return this run's backend URL, for the launchers that need it.

    With `wait`, it waits for the backend to truly answer instead of
    only checking that someone published a port. That makes «Entorno de
    desarrollo» work regardless of the order tabs started in: the SPA
    waits on the backend's endpoint, not on a `sleep` (ADR-0011).

    With `required=False` it returns an empty string if there is no
    backend instead of failing: for the SPA that is no error but
    starting with its own config.
    """
    endpoint = ctx.endpoint(BACKEND, wait=wait)
    if endpoint is not None:
        if endpoint.state == session.DOWN and required:
            raise TaskError(f"El backend no llego a responder en {endpoint.url}.")
        return endpoint.url
    if not required:
        return ""
    raise TaskError(
        "El backend todavia no arranco en esta sesion: "
        'levantalo primero, o usa "Entorno de desarrollo".'
    )


def resolve_tls(ctx: TaskContext, server: Path) -> tuple[Path, Path] | None:
    """Return the backend's certificates, if any.

    Without them it starts in plain text. They are looked for in
    `certs/` of the server's folder.
    """
    cert = server / "certs" / "cert.pem"
    key = server / "certs" / "key.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    ctx.warn("TLS deshabilitado: faltan los certificados.")
    return None


# --- launchers ---


def serve_backend(
    ctx: TaskContext,
    target: str = "",
    scope: str = db.LOCAL,
    host: str = "0.0.0.0",
    preferred_port: int = 8000,
    reload: bool = True,
) -> None:
    """Start uvicorn with the chosen scope's database.

    The tunnel, if the scope is remote, lives as long as the server: it
    closes only when the tab stops. A canone repo runs with its
    development credentials and only against the local database
    (ADR-0069).
    """
    server = targets.pick(ctx.root, (targets.FASTAPI,), target).path
    interpreter = venv_python(server / ".venv")
    port = resolve_server_port(ctx, preferred_port)
    app = targets.asgi_app(server)

    argv = [str(interpreter), "-m", "uvicorn", app, "--host", host, "--port", str(port)]
    if reload:
        argv.append("--reload")
    tls = resolve_tls(ctx, server)
    if tls:
        argv.extend(["--ssl-certfile", str(tls[0]), "--ssl-keyfile", str(tls[1])])

    # The announced URL is not the listening one: `0.0.0.0` is where it
    # listens, `localhost` is the way in. A browser pointed at `0.0.0.0`
    # reaches nothing.
    schema = "https" if tls else "http"

    def start(environment: dict[str, str]) -> None:
        ctx.info(f"Backend {app} escuchando en {host}:{port}")
        ctx.serve(f"{schema}://localhost:{port}", key=BACKEND, label="Backend")
        try:
            ctx.run(argv, cwd=server, env=environment, check=False)
        finally:
            session.forget(ctx.project_name, SERVER_PORT)

    if not fields.settings_fields(server):
        with db.connect(ctx, scope) as conn:
            start({"DATABASE_URL": conn.url})
        return
    if scope != db.LOCAL:
        raise TaskError("Un repo de canone levanta su backend solo contra la base local.")
    folder = runner.write_credentials(
        ctx, server, runner.CREDENTIALS, canone.credential_files(server, ctx.config)
    )
    # `.env` is the repo's: it says, for example, where
    # `STATE_DIRECTORY` is.
    start({**envfile.load_env(str(server / ".env")), "CREDENTIALS_DIRECTORY": str(folder)})


def serve_spa(
    ctx: TaskContext,
    target: str = "",
    preferred_port: int = 5173,
    wait_backend: float = BACKEND_WAIT,
) -> None:
    """Start an SPA's `pnpm run dev`, pointed at this session's backend.

    It runs ONE SPA. Checking several in the panel does not make it
    iterate: each one is a live process with its port and console, so
    the interface opens one tab each and calls this once per tab
    (ADR-0010).
    """
    spa = targets.pick(ctx.root, (targets.SPA_VITE,), target)
    port = ports.resolve_port(preferred_port, label=f"puerto de {spa.name}")

    # No backend is no error: the SPA starts with what its .env has.
    # With a backend starting in another tab, it waits: the order the
    # buttons were pressed in should not decide whether the SPA knows
    # where to connect.
    api = backend_url(ctx, wait=wait_backend, required=False)
    if api:
        ctx.info(f"Backend detectado: {api}")
    else:
        ctx.warn("El backend no esta corriendo: la SPA va a usar su propia configuracion.")

    ctx.serve(f"http://localhost:{port}", key=f"spa:{spa.name}", label=spa.name)
    # pnpm hands the options after the script to it: a `--` would reach
    # Vite as is.
    ctx.run(
        [*toolchain.pnpm_cmd(), "run", "dev", "--port", str(port)],
        cwd=spa.path,
        env={"VITE_SERVER_URL": api} if api else None,
        check=False,
    )


def run_mobile(ctx: TaskContext, target: str = "", device: str = "") -> None:
    """Run the mobile app on the active emulator, by its framework.

    If no emulator is alive it says so and does not try to start against
    the desktop: that was the easiest way to lose ten minutes with
    `flutter run`.
    """
    app = targets.pick(ctx.root, targets.MOBILE_APP, target)
    kind = toolchain.detect_app_kind(app.path)

    # Order of preference: what was asked by hand, the emulator this
    # session's «Emulador» tab started, and only then the first to
    # answer. With two live emulators, «the first» is a lottery.
    serial = (
        device
        or session.read(session.MACHINE, emulators.EMULATOR_SERIAL, "")
        or toolchain.pick_emulator(toolchain.devices(ctx, app.path))
    )
    if not serial:
        raise TaskError("No hay ningun emulador Android corriendo. Arranca uno primero.")

    api = ctx.config.get("API_URL") or backend_url(ctx, wait=BACKEND_WAIT)
    ctx.info(f"{kind} en {serial} contra {api}")

    if kind == toolchain.FLUTTER:
        argv = [*toolchain.flutter_cmd(), "run", "-d", serial, f"--dart-define=API_BASE_URL={api}"]
        ctx.run(argv, cwd=app.path, check=False)
    else:
        ctx.run(
            [*toolchain.flet_cmd(), "run", "--android"],
            cwd=app.path,
            env={"API_BASE_URL": api},
            check=False,
        )


def run_python_app(
    ctx: TaskContext,
    target: str = "",
    auto_login: bool = False,
    watch: bool = True,
    wait_backend: float = BACKEND_WAIT,
) -> None:
    """Start a Python app of the repo, reloading when sources change.

    It runs ONE app: checking several opens one tab each, like SPAs
    (ADR-0010). With `watch` there are two process levels, the watcher
    and its child, and stopping the tab kills both bottom up (ADR-0005).
    Without `watch` it is one process, for an app that should not
    relaunch by itself (a bot, a one-off script).
    """
    app = targets.pick(ctx.root, targets.DESKTOP_APP, target)
    entry = targets.python_entrypoint(app.path)
    if entry is None:
        raise TaskError(
            f"{app.name} no tiene punto de entrada ({', '.join(targets.PYTHON_ENTRYPOINTS)})."
        )
    source = entry.parent
    interpreter = toolchain.app_python(app.path, ctx.root)

    # With a backend it gets its URL; without one, the app starts anyway
    # with its own configuration, like the SPA. Whether it needs one is
    # the app's business.
    environment = {}
    api = backend_url(ctx, wait=wait_backend, required=False)
    if api:
        environment["SERVER_URL"] = api
        ctx.info(f"Backend detectado: {api}")
    if auto_login:
        environment["TERMINAL_DEV_AUTO_LOGIN"] = "true"

    if not watch:
        ctx.info(f"Lanzando {app.name}...")
        ctx.run([*interpreter, entry.name], cwd=source, env=environment or None, check=False)
        return

    while not ctx.cancelled:
        ctx.info(f"Lanzando {app.name}...")
        # The watcher runs next to the process and kills it as soon as a
        # source changes: `ctx.run` returns and the next round
        # relaunches it. If the process ends by itself with no changes,
        # the task ends with it.
        change, end = threading.Event(), threading.Event()
        watchdog = threading.Thread(target=_watch, args=(ctx, source, change, end), daemon=True)
        watchdog.start()
        try:
            code = ctx.run(
                [*interpreter, entry.name],
                cwd=source,
                env=environment or None,
                check=False,
                echo=False,
            )
        finally:
            end.set()
            watchdog.join()
        if ctx.cancelled:
            return
        if not change.is_set():
            ctx.info(f"{app.name} termino con codigo {code}.")
            return
        ctx.info("Cambios detectados: reiniciando.")


# How often sources are checked. Half a second goes unnoticed when
# saving.
WATCH_INTERVAL = 0.5
# What gets watched: code and Qt style sheets.
_WATCHED = {".py", ".qss"}


def _watch(ctx: TaskContext, root: Path, change: threading.Event, end: threading.Event) -> None:
    signature = _snapshot(root)
    while not end.wait(WATCH_INTERVAL):
        try:
            current = _snapshot(root)
        except OSError:
            # a file deleted mid-walk: it is checked on the next round
            continue
        if current != signature:
            change.set()
            ctx.kill_children()
            return


def _snapshot(root: Path) -> dict[str, float]:
    # Without the venv or artifacts: an app at the repo's root would
    # have to walk them whole each round.
    return {
        str(p): p.stat().st_mtime
        for p in root.rglob("*")
        if p.suffix in _WATCHED
        and p.is_file()
        and not any(
            part in targets.IGNORED or part.startswith(".")
            for part in p.relative_to(root).parts[:-1]
        )
    }


def open_ssh_session(ctx: TaskContext) -> None:
    """Open the SSH session in an external terminal.

    It needs a real TTY.

    ADR-0005.
    """
    remote = ssh.resolve_remote(ctx.config)
    ctx.detach(ssh.terminal_argv(remote))
    ctx.ok(f"Sesion SSH abierta en una terminal externa: {remote.target}")


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("backend", serve_backend)
    registry.bind("serve_vite", serve_spa)
    registry.bind("run_mobile", run_mobile)
    registry.bind("run_python", run_python_app)
    registry.bind("ssh_login", open_ssh_session)
