from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from . import database as db, ssh, vps
from .context import Level
from .errors import TaskError
from .toolchain import venv_python

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
alembic ...`, `-c <fuente>`) y el interprete es el que `install_remote_deps` ya
dejo instalado en el VPS; cualquier cosa que el servidor tenga en su venv se
puede correr asi, sin subir un archivo primero.
"""


def server_root(ctx) -> Path:
    """La carpeta del servidor dentro del repo abierto."""
    root = ctx.root / ctx.config.get('SERVER_DIR', 'server')
    if not root.is_dir():
        raise TaskError(f'No existe la carpeta del servidor: {root}')
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

    @property
    def is_remote(self) -> bool:
        return self.remote is not None

    def run(self, ctx, *args: str, echo: bool = True) -> int:
        """`python <args>` en el directorio del servidor, con DATABASE_URL puesto.

        `DATABASE_URL` viaja por el entorno del proceso, nunca escrito a un
        archivo: es el mismo dato que ya resolvio quien pidio el runner, no una
        segunda resolucion (ni un segundo tunel). Del lado remoto va como
        asignacion delante del comando, igual que hacia `maybe_dispatch_remote`;
        la contrasena esta enmascarada en el log por `ctx.guard`.
        """
        if self.remote is None:
            return ctx.run([self.python, *args], cwd=self.cwd,
                           env={'DATABASE_URL': self.database_url}, echo=echo)
        comando = ' '.join(ssh.quote(a) for a in (self.python, *args))
        return ssh.run(ctx, self.remote,
                       f'cd {ssh.quote(self.cwd)} && '
                       f'DATABASE_URL={ssh.quote(self.database_url)} {comando}',
                       echo=echo)

    def log_command(self, ctx, resumen: str) -> None:
        """Anuncia en el log un comando cuyo argv real no se puede leer.

        Un payload entra como `-c <programa entero>`: volcarlo tal cual llena la
        consola con cincuenta lineas de codigo que no dicen nada. Quien lo use
        pasa `echo=False` a `run`.
        """
        donde = f'{self.remote.target}:' if self.remote else ''
        ctx.log(f'{donde}{self.python} {resumen}', Level.CMD)


def resolve(ctx, scope: str = db.LOCAL) -> Runner:
    """El runner del ambito pedido: aca contra la base local, o en el VPS contra la suya.

    Es el camino de todo lo que solo toca la base —aplicar migraciones, sembrar,
    asegurar particiones—: nada de eso escribe en el repo, asi que corre bien de
    los dos lados y conviene que corra donde esta la base.
    """
    if scope not in db.SCOPES:
        raise TaskError(f'Ambito invalido: {scope!r}. Usa {" | ".join(db.SCOPES)}.')

    if scope == db.LOCAL:
        return here(ctx, db.connect(ctx, db.LOCAL))

    remote = ssh.resolve_remote(ctx.config)
    interprete = vps.remote_python(ctx.config)
    if not ssh.path_exists(remote, interprete):
        raise TaskError(
            f'No existe el Python del venv en el VPS: {interprete}. '
            'Corre "Actualizar remoto" para crearlo e instalar las dependencias.')

    destino = vps.remote_path(ctx.config, ctx.config.get('SERVER_DIR', 'server'))
    ctx.info(f'Se ejecuta en el VPS: {remote.target}:{destino}')
    return Runner(interprete, destino, db.vps_url(ctx, remote), remote)


def here(ctx, conn: db.Connection) -> Runner:
    """Siempre en esta maquina, contra la base que diga `conn` —con su tunel si
    esa base es la del VPS.

    Es para lo que ademas de tocar la base escribe en el repo abierto: Alembic
    `revision --autogenerate` deja un archivo en `alembic/versions/` que hay que
    revisar y comitear. Generado en el VPS caeria en el repo desplegado, donde
    el `git reset --hard` de "Actualizar remoto" se lo lleva puesto.
    """
    raiz = server_root(ctx)
    return Runner(str(venv_python(raiz / '.venv')), str(raiz), conn.url)
