from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core import canone, fields, ssh, vps
from app.core import database as db
from app.core.context import Level, TaskContext
from app.core.errors import TaskError
from app.core.toolchain import venv_python

# Development credentials of a canone repo (ADR-0069). The owner's folder lives inside
# the other one, which the canone .gitignore already covers (ADR-0070).
CREDENTIALS = "credentials"
MIGRATE_CREDENTIALS = "credentials/migrate"

"""
Donde corre el codigo del proyecto: aca o en el VPS.

El SQL suelto ya sabia elegir lado. Con ambito remoto, `database.Admin` manda
`psql` por SSH y no abre ningun tunel. Pero lo que necesita el *codigo* del repo
—Alembic, que importa los modelos para el autogenerate; los seeders y las
particiones, que importan `app.core.settings`— corria siempre en esta maquina,
con el venv de Windows, sin mirar el ambito: reconstruir la base del VPS borraba
las tablas por SSH y despues moria buscando un `python.exe` local que en un
equipo que solo opera el servidor no tiene por que existir.

Este modulo es la mitad que faltaba del eje `scope`, y es lo que
`maybe_dispatch_remote` hacia en `scripts/common.py`: elegir el interprete y el
directorio del proyecto —los de aca o los del repo desplegado— y correr ahi.

No copia nada al otro lado. El programa viaja en la linea de comandos (`-m
alembic ...`, `-c <fuente>`) y el interprete es el del venv que ya este en el
repo desplegado; cualquier cosa que el servidor tenga en su venv se puede correr
asi, sin subir un archivo primero.
"""


def server_root(ctx: TaskContext) -> Path:
    """La carpeta del servidor dentro del repo abierto."""
    root = ctx.root / ctx.config.get("SERVER_DIR", "server")
    if not root.is_dir():
        raise TaskError(f"No existe la carpeta del servidor: {root}")
    return root


@dataclass(frozen=True)
class Runner:
    """Un interprete de Python del proyecto, con su directorio y su base.

    Hermano de `database.Admin`: mismo reparto, otro canal. `Admin` corre SQL
    como superusuario —local por `psql`, remoto por SSH—; `Runner` corre
    programas Python con las dependencias del servidor, del mismo lado.
    """

    python: str
    cwd: str
    database_url: str
    remote: ssh.Remote | None = None
    # La carpeta de credenciales, en un repo de canone: su `Settings` lee solo
    # de ahi, y `database_url` no le llega.
    credentials: str = ""

    @property
    def is_remote(self) -> bool:
        return self.remote is not None

    def run(self, ctx: TaskContext, *args: str, echo: bool = True) -> int:
        """`python <args>` en el directorio del servidor, con DATABASE_URL puesto.

        `DATABASE_URL` viaja por el entorno del proceso, nunca escrito a un
        archivo: es el mismo dato que ya resolvio quien pidio el runner, no una
        segunda resolucion (ni un segundo tunel). Del lado remoto va como
        asignacion delante del comando, igual que hacia `maybe_dispatch_remote`;
        la contrasena esta enmascarada en el log por `ctx.guard`.
        """
        if self.remote is None:
            entorno = (
                {"CREDENTIALS_DIRECTORY": self.credentials}
                if self.credentials
                else {"DATABASE_URL": self.database_url}
            )
            return ctx.run([self.python, *args], cwd=self.cwd, env=entorno, echo=echo)
        comando = " ".join(ssh.quote(a) for a in (self.python, *args))
        return ssh.run(
            ctx,
            self.remote,
            f"cd {ssh.quote(self.cwd)} && DATABASE_URL={ssh.quote(self.database_url)} {comando}",
            echo=echo,
        )

    def log_command(self, ctx: TaskContext, resumen: str) -> None:
        """Anuncia en el log un comando cuyo argv real no se puede leer.

        Un payload entra como `-c <programa entero>`: volcarlo tal cual llena la
        consola con cincuenta lineas de codigo que no dicen nada. Quien lo use
        pasa `echo=False` a `run`.
        """
        donde = f"{self.remote.target}:" if self.remote else ""
        ctx.log(f"{donde}{self.python} {resumen}", Level.CMD)


def resolve(ctx: TaskContext, scope: str = db.LOCAL) -> Runner:
    """El runner del ambito pedido: aca contra la base local, o en el VPS contra la suya.

    Es el camino de todo lo que solo toca la base —aplicar migraciones, sembrar,
    asegurar particiones—: nada de eso escribe en el repo, asi que corre bien de
    los dos lados y conviene que corra donde esta la base.
    """
    if scope not in db.SCOPES:
        raise TaskError(f"Ambito invalido: {scope!r}. Usa {' | '.join(db.SCOPES)}.")

    if scope == db.LOCAL:
        return local(ctx)

    remote = ssh.resolve_remote(ctx.config)
    interprete = vps.remote_python(ctx.config)
    if not ssh.path_exists(remote, interprete):
        raise TaskError(
            f"No existe el Python del venv en el VPS: {interprete}. Lo dejaba el "
            "despliegue propio de Consola, que ya no existe (ADR-0059)."
        )

    destino = vps.remote_path(ctx.config, ctx.config.get("SERVER_DIR", "server"))
    ctx.info(f"Se ejecuta en el VPS: {remote.target}:{destino}")
    return Runner(interprete, destino, db.vps_url(ctx, remote), remote)


def write_credentials(
    ctx: TaskContext, server: Path, folder: str, archivos: dict[str, str]
) -> Path:
    """Escribe una carpeta de credenciales de desarrollo y devuelve su ruta.

    Corta si git no la ignora: un secreto commiteado por escribirlo aca no se
    borra con otro commit. Un `app_*` que ya no es un campo de `Settings` sale,
    para que la carpeta diga lo mismo que `config.env`.
    """
    carpeta = server / folder
    try:
        ctx.capture(["git", "check-ignore", "-q", f"{carpeta}/"], cwd=server)
    except TaskError as exc:
        raise TaskError(
            f"git no ignora {carpeta}: agrégala a .gitignore antes de escribir credenciales ahí."
        ) from exc
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("app_*"):
        if viejo.name not in archivos:
            viejo.unlink()
    for nombre, valor in archivos.items():
        (carpeta / nombre).write_text(valor, encoding="utf-8")
    return carpeta


def local(ctx: TaskContext) -> Runner:
    """Siempre en esta maquina y contra la base local.

    Un repo de canone corre Alembic como el dueño del esquema, con sus propias
    credenciales (ADR-0069). Los demas siguen recibiendo `DATABASE_URL`.
    """
    raiz = server_root(ctx)
    if not fields.settings_fields(raiz):
        return here(ctx, db.connect(ctx, db.LOCAL))
    carpeta = write_credentials(
        ctx, raiz, MIGRATE_CREDENTIALS, canone.credential_files(raiz, ctx.config, owner=True)
    )
    ctx.info(f"Base de datos LOCAL, como el dueño del esquema: {carpeta}")
    return Runner(str(venv_python(raiz / ".venv")), str(raiz), "", credentials=str(carpeta))


def here(ctx: TaskContext, conn: db.Connection) -> Runner:
    """Siempre en esta maquina, contra la base que diga `conn` —con su tunel si
    esa base es la del VPS.

    Es para lo que ademas de tocar la base escribe en el repo abierto: Alembic
    `revision --autogenerate` deja un archivo en `alembic/versions/` que hay que
    revisar y comitear. Generado en el VPS caeria en el repo desplegado, que no
    es el que se commitea.
    """
    raiz = server_root(ctx)
    return Runner(str(venv_python(raiz / ".venv")), str(raiz), conn.url)
