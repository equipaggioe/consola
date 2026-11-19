"""Run the project's code on this machine: Alembic, seeders, partitions.

It chooses the server venv's interpreter, the project's folder and how
the database is reached: as the schema's owner with its credentials in
a canone repo, by `DATABASE_URL` in the others. On the VPS that code
runs with canone's `deploy.py` and `database.py` (ADR-0060).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services import canone, fields
from app.services import database as db
from app.services.context import Level, TaskContext
from app.services.errors import TaskError
from app.services.toolchain import venv_python

# Development credentials of a canone repo (ADR-0069). The owner's
# folder lives inside the other one, which the canone .gitignore already
# covers (ADR-0070).
CREDENTIALS = "credentials"
MIGRATE_CREDENTIALS = "credentials/migrate"


def server_root(ctx: TaskContext) -> Path:
    """Return the server's folder inside the open repo."""
    root = ctx.root / ctx.config.get("SERVER_DIR", "server")
    if not root.is_dir():
        raise TaskError(f"No existe la carpeta del servidor: {root}")
    return root


@dataclass(frozen=True)
class Runner:
    """A Python interpreter of the project, its folder and database.

    A sibling of `database.Admin`: same split, another channel. `Admin`
    runs SQL as superuser with `psql`; `Runner` runs Python programs
    with the server's dependencies.
    """

    python: str
    cwd: str
    database_url: str
    # The credentials folder in a canone repo: its `Settings` reads only
    # from there, and `database_url` does not reach it.
    credentials: str = ""

    def run(self, ctx: TaskContext, *args: str, echo: bool = True) -> int:
        """Run `python <args>` in the server folder.

        `DATABASE_URL` travels in the process's environment, never
        written to a file: it is what the runner's caller already
        resolved, not a second resolution.
        """
        environment = (
            {"CREDENTIALS_DIRECTORY": self.credentials}
            if self.credentials
            else {"DATABASE_URL": self.database_url}
        )
        return ctx.run([self.python, *args], cwd=self.cwd, env=environment, echo=echo)

    def log_command(self, ctx: TaskContext, summary: str) -> None:
        """Announce in the log a command whose real argv cannot be read.

        A payload enters as `-c <whole program>`: dumping it fills the
        console with fifty lines of code that say nothing. Whoever uses
        this passes `echo=False` to `run`.
        """
        ctx.log(f"{self.python} {summary}", Level.CMD)


def write_credentials(ctx: TaskContext, server: Path, folder: str, files: dict[str, str]) -> Path:
    """Write a development credentials folder and return its path.

    It stops if git does not ignore it: a secret committed through this
    is not erased by another commit. An `app_*` that is no longer a
    `Settings` field goes away, so the folder says the same as
    `config.env`.
    """
    credentials_folder = server / folder
    try:
        ctx.capture(["git", "check-ignore", "-q", f"{credentials_folder}/"], cwd=server)
    except TaskError as exc:
        raise TaskError(
            f"git no ignora {credentials_folder}: agrégala a .gitignore antes de escribir "
            f"credenciales ahí."
        ) from exc
    credentials_folder.mkdir(parents=True, exist_ok=True)
    for old in credentials_folder.glob("app_*"):
        if old.name not in files:
            old.unlink()
    for name, value in files.items():
        (credentials_folder / name).write_text(value, encoding="utf-8")
    return credentials_folder


def local(ctx: TaskContext) -> Runner:
    """Return the runner on this machine, against the local database.

    A canone repo runs Alembic as the schema's owner, with its own
    credentials (ADR-0069). The others still receive `DATABASE_URL`.
    """
    root = server_root(ctx)
    if not fields.settings_fields(root):
        return here(ctx, db.connect(ctx, db.LOCAL))
    credentials_folder = write_credentials(
        ctx, root, MIGRATE_CREDENTIALS, canone.credential_files(root, ctx.config, owner=True)
    )
    ctx.info(f"Base de datos LOCAL, como el dueño del esquema: {credentials_folder}")
    return Runner(
        str(venv_python(root / ".venv")), str(root), "", credentials=str(credentials_folder)
    )


def here(ctx: TaskContext, conn: db.Connection) -> Runner:
    """Return the runner on this machine, against `conn`'s database."""
    root = server_root(ctx)
    return Runner(str(venv_python(root / ".venv")), str(root), conn.url)
