"""Where the project's code runs: here or on the VPS.

Loose SQL could already choose a side: with remote scope,
`database.Admin` sends `psql` over SSH and opens no tunnel. But what the
repo's *code* needs, Alembic for autogenerate and the seeders and
partitions, always ran on this machine regardless of scope.

This module is the missing half of the `scope` axis: it chooses the
interpreter and the project's folder, here or in the deployed repo, and
runs there.

It copies nothing to the other side. The program travels in the command
line (`-m alembic ...`, `-c <source>`) and the interpreter is the venv's
in the deployed repo; anything the server has in its venv can run this
way, without uploading a file first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core import canone, fields, ssh, vps
from app.core import database as db
from app.core.context import Level, TaskContext
from app.core.errors import TaskError
from app.core.toolchain import venv_python

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
    """A Python interpreter of the project.

    With its folder and database.

    A sibling of `database.Admin`: same split, another channel. `Admin`
    runs SQL as superuser, local with `psql` and remote over SSH;
    `Runner` runs Python programs with the server's dependencies, on the
    same side.
    """

    python: str
    cwd: str
    database_url: str
    remote: ssh.Remote | None = None
    # The credentials folder in a canone repo: its `Settings` reads only
    # from there, and `database_url` does not reach it.
    credentials: str = ""

    @property
    def is_remote(self) -> bool:
        """Return whether it runs on the VPS."""
        return self.remote is not None

    def run(self, ctx: TaskContext, *args: str, echo: bool = True) -> int:
        """Run `python <args>` in the server folder.

        With DATABASE_URL set.

        `DATABASE_URL` travels in the process's environment, never
        written to a file: it is what the runner's caller already
        resolved, not a second resolution or a second tunnel. On the
        remote side it goes as an assignment before the command;
        `ctx.guard` masks the password in the log.
        """
        if self.remote is None:
            environment = (
                {"CREDENTIALS_DIRECTORY": self.credentials}
                if self.credentials
                else {"DATABASE_URL": self.database_url}
            )
            return ctx.run([self.python, *args], cwd=self.cwd, env=environment, echo=echo)
        command = " ".join(ssh.quote(a) for a in (self.python, *args))
        return ssh.run(
            ctx,
            self.remote,
            f"cd {ssh.quote(self.cwd)} && DATABASE_URL={ssh.quote(self.database_url)} {command}",
            echo=echo,
        )

    def log_command(self, ctx: TaskContext, summary: str) -> None:
        """Announce in the log a command whose real argv cannot be read.

        A payload enters as `-c <whole program>`: dumping it fills the
        console with fifty lines of code that say nothing. Whoever uses
        this passes `echo=False` to `run`.
        """
        donde = f"{self.remote.target}:" if self.remote else ""
        ctx.log(f"{donde}{self.python} {summary}", Level.CMD)


def resolve(ctx: TaskContext, scope: str = db.LOCAL) -> Runner:
    """Return the runner of that scope.

    Local base here, or the VPS's there.

    It is the path of what only touches the database: applying
    migrations, seeding, ensuring partitions. None of that writes in the
    repo, so it runs fine on both sides and should run where the
    database is.
    """
    if scope not in db.SCOPES:
        raise TaskError(f"Ambito invalido: {scope!r}. Usa {' | '.join(db.SCOPES)}.")

    if scope == db.LOCAL:
        return local(ctx)

    remote = ssh.resolve_remote(ctx.config)
    interpreter = vps.remote_python(ctx.config)
    if not ssh.path_exists(remote, interpreter):
        raise TaskError(
            f"No existe el Python del venv en el VPS: {interpreter}. Lo dejaba el "
            "despliegue propio de Consola, que ya no existe (ADR-0059)."
        )

    destination = vps.remote_path(ctx.config, ctx.config.get("SERVER_DIR", "server"))
    ctx.info(f"Se ejecuta en el VPS: {remote.target}:{destination}")
    return Runner(interpreter, destination, db.vps_url(ctx, remote), remote)


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
    """Return the runner on this machine, against `conn`'s database.

    With its tunnel if that database is the VPS's. It is for what also
    writes in the open repo: Alembic `revision --autogenerate` leaves a
    file in `alembic/versions/` to review and commit. Generated on the
    VPS it would land in the deployed repo, which is not the one that
    gets committed.
    """
    root = server_root(ctx)
    return Runner(str(venv_python(root / ".venv")), str(root), conn.url)
