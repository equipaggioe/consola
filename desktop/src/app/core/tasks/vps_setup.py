from __future__ import annotations

from dataclasses import dataclass

from app.core import canone, session, ssh
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.registry import registry

"""
Grupo VPS - setup: dejar un VPS listo con los programas de canone (ADR-0059).

La maquina llega a `install.py` con sus paquetes, uv y tanto swap como memoria:
eso lo pone quien la prepara, que es Consola (despliegue.md de canone,
«Maquina»). Despues `install.py` instala la app, crea la cuenta que administra
y deja entrar solo por llave, y `credentials.py` cifra las credenciales.

La primera vez entra root con la llave `VPS_KEY_NAME`, puesta al crear el VPS.
Despues de `install.py` root ya no entra, y todo pasa por la cuenta de
`VPS_USER` con `sudo`, que pide su contraseña.
"""

# Donde se suben los programas de canone. Se borra al terminar.
REMOTE_DIR = "/tmp/consola-canone"
SUDO_KEY = "SUDO_PASSWORD"


@dataclass(frozen=True)
class Access:
    """Como se entra al VPS: root la primera vez, o la cuenta que administra con sudo."""

    remote: ssh.Remote
    password: str = ""

    @property
    def is_root(self) -> bool:
        return not self.password

    def command(self, command: str) -> str:
        """`command` como root: tal cual si se entro como root, con `sudo -S` si no."""
        if self.is_root:
            return command
        return f"sudo -S -p '' bash -c {ssh.quote(command)}"

    def stdin(self, text: str = "") -> str | None:
        """Lo que va a la entrada del comando: la contraseña de sudo primero."""
        if self.is_root:
            return text or None
        return f"{self.password}\n{text}"

    def run(self, ctx: TaskContext, command: str, *, text: str = "", check: bool = True) -> int:
        return ssh.run(
            ctx, self.remote, self.command(command), check=check, stdin_text=self.stdin(text)
        )


def _sudo_password(ctx: TaskContext) -> str:
    """`SUDO_PASSWORD`, o la que se pide una vez por sesion y vive solo en memoria.

    Va a `core/session.py` directo y no por `ctx.publish`, que la olvidaria al
    terminar la corrida.
    """
    escrita = ctx.config.get(SUDO_KEY) or session.read(ctx.project_name, SUDO_KEY)
    if not escrita:
        usuario = ctx.config.require("VPS_USER")
        escrita = ctx.ask(f"Contraseña de {usuario} (la de sudo)", secret=True)
        if not escrita:
            raise TaskError("Sin la contraseña de sudo no se puede administrar el VPS.")
        session.publish(ctx.project_name, SUDO_KEY, escrita)
    ctx.guard(escrita)
    return escrita


def access(ctx: TaskContext) -> Access:
    """Entra por la cuenta que administra si ya existe; si no, por root.

    Root entra solo antes de `install.py`, que despues lo deja afuera. Sin
    ninguna de las dos no hay forma de seguir.
    """
    admin = ssh.resolve_remote(ctx.config)
    if ssh.reachable(admin):
        return Access(admin, _sudo_password(ctx))
    root = admin.as_user(ctx.config.get("ROOT_USER"))
    if ssh.reachable(root):
        ctx.info(f"{admin.target} todavía no entra: se usa {root.target}.")
        return Access(root)
    raise TaskError(
        f"No se entra al VPS ni como {admin.target} ni como {root.target} "
        f"con la llave {ctx.config.get('VPS_KEY_NAME')}."
    )


def _upload(ctx: TaskContext, entrada: Access) -> str:
    """Sube `plantilla/infra/` de canone a una carpeta temporal y devuelve su ruta."""
    infra = canone.infra_dir(ctx.config)
    entrada.run(ctx, f"rm -rf {REMOTE_DIR}")
    return ssh.upload(ctx, entrada.remote, infra, f"{REMOTE_DIR}/{infra.name}")


def _cleanup(ctx: TaskContext, entrada: Access) -> None:
    entrada.run(ctx, f"rm -rf {REMOTE_DIR}", check=False)


# --- atomicas --------------------------------------------------------------


def refresh_known_host(ctx: TaskContext) -> str:
    """Olvida la huella vieja del VPS.

    Despues de reinstalar el servidor cambia la huella y todas las conexiones
    fallan con un error de "host key verification" que no dice como arreglarlo.
    La nueva la anota la primera conexion de cualquier otra atomica.
    """
    host = ctx.config.require("VPS_IP")
    ssh.forget_host(ctx, host)
    return host


def install_software(ctx: TaskContext) -> list[str]:
    """Instala los paquetes que `install.py` da por instalados, y uv con `uv.py`.

    Los paquetes salen del repo y no de un eje: PostGIS si `DB_EXTENSIONS` la
    nombra, coturn con `TURN`, y lo del journal con `LOGS` (`canone.packages`).
    `uv.py` instala la version de uv que fija canone (ADR-0110 de canone): se
    vuelve a correr cuando canone la cambia.
    """
    entrada = access(ctx)
    paquetes = canone.packages(ctx.config)
    lista = " ".join(ssh.quote(p) for p in paquetes)
    entrada.run(
        ctx,
        "export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && "
        f"apt-get install -y {lista}",
    )
    destino = _upload(ctx, entrada)
    try:
        entrada.run(ctx, f"python3 {destino}/uv.py")
    finally:
        _cleanup(ctx, entrada)
    ctx.ok(f"Paquetes y uv listos: {', '.join(paquetes)}")
    return paquetes


# Crea `/swapfile` con lo que falte para tener tanto swap como memoria, que es
# lo que pide `install.py`. Si ya habia un `/swapfile` que no alcanza, lo rehace.
_SWAP = r"""set -e
mem=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
swap=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
[ "$swap" -ge "$mem" ] && { echo "[OK] Ya hay tanto swap como memoria."; exit 0; }
if swapon --show=NAME --noheadings | grep -qx /swapfile; then swapoff /swapfile; fi
rm -f /swapfile
swap=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
falta=$(( (mem - swap) / 1024 + 1 ))
fallocate -l "${falta}M" /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
echo "[OK] Swap de ${falta} MiB en /swapfile."
"""


def create_swap(ctx: TaskContext) -> None:
    """Deja tanto swap como memoria: sin eso, `install.py` falla."""
    access(ctx).run(ctx, _SWAP)


def install_infra(ctx: TaskContext) -> None:
    """Sube `plantilla/infra/` de canone y corre `install.py` con los datos del repo.

    La primera vez corre como root, y `install.py` pide dos veces la contraseña
    de la cuenta que crea: se escribe en un `ssh -tt` recien cuando aparece cada
    pregunta, porque escrita antes la terminal remota la repite en el log
    (`ctx.converse`). Despues corre con `sudo` desde esa cuenta, y las llaves que
    ya tiene no se vuelven a agregar.
    """
    owner, app = canone.origin(ctx.root)
    llave = ssh.public_key(
        ssh.ensure_local_keypair(ctx, ctx.config.require("VPS_KEY_NAME"), comment=app)
    )
    fuera = ctx.config.require("OFFLINE_KEY").strip()
    if fuera.split()[:2] == llave.split()[:2]:
        raise TaskError(
            "OFFLINE_KEY es la misma llave que VPS_KEY_NAME: hace falta otra, "
            "guardada fuera de esta máquina."
        )
    argumentos = canone.install_args(ctx.root, ctx.config, app, owner, (llave, fuera))
    entrada = access(ctx)
    destino = _upload(ctx, entrada)
    comando = " ".join(ssh.quote(a) for a in ("python3", f"{destino}/install.py", *argumentos))
    try:
        if entrada.is_root:
            password = _sudo_password(ctx)
            ctx.converse(
                entrada.remote.argv(comando, tty=True, extra=["-t"]),
                [("Password of", password), ("Again", password)],
            )
        else:
            entrada.run(ctx, comando)
    finally:
        # `install.py` deja a root sin entrada: limpia la cuenta que queda.
        _cleanup(ctx, access(ctx))
    ctx.ok(f"{app} instalado en {entrada.remote.host}.")


def load_credentials(ctx: TaskContext) -> None:
    """Pasa las credenciales de `config.env` a `credentials.py`, por stdin.

    Una linea `campo=valor` por campo de `Settings`, mas `restic_password` y, en
    un repo privado, `github_token` (ADR-0063). Corta antes de enviar si falta
    alguna o si `config.env` tiene una clave que no cae en ninguna fuente.
    `install.py` no instala `credentials.py`, asi que se sube cada vez.
    """
    _, app = canone.origin(ctx.root)
    lineas = canone.credential_lines(ctx.root, ctx.config)
    for linea in lineas.splitlines():
        ctx.guard(linea.partition("=")[2])
    entrada = access(ctx)
    if entrada.is_root:
        raise TaskError(
            "La cuenta que administra todavía no existe: corre «Configurar VPS» "
            "con «Instalar infraestructura» primero."
        )
    destino = _upload(ctx, entrada)
    try:
        entrada.run(ctx, f"python3 {destino}/credentials.py {ssh.quote(app)}", text=lineas)
    finally:
        _cleanup(ctx, entrada)
    ctx.ok(f"{len(lineas.splitlines())} credenciales cargadas.")


# --- compuesta -------------------------------------------------------------


def bootstrap_vps(
    ctx: TaskContext,
    *,
    known_host: bool = False,
    software: bool = True,
    swap: bool = True,
    infra: bool = True,
    credentials: bool = True,
    deploy: bool = True,
) -> None:
    """Paquetes y uv → swap → `install.py` → credenciales → ultimo release.

    Cada paso detecta lo que ya esta, asi que la compuesta se puede volver a
    correr: es lo que hace falta para agregar un instalable o pasar a privado,
    que piden reinstalar (ADR-0106 de canone). El despliegue no: `deploy.py`
    no instala una version que ya esta en el VPS.
    """
    # Circular: `vps_release` entra al VPS con `access`, de este modulo.
    from app.core.tasks.vps_release import deploy_latest

    if known_host:
        ctx.step("known_host")
        refresh_known_host(ctx)
    if software:
        ctx.step("software")
        install_software(ctx)
    if swap:
        ctx.step("swap")
        create_swap(ctx)
    if infra:
        ctx.step("infra")
        install_infra(ctx)
    if credentials:
        ctx.step("credentials")
        load_credentials(ctx)
    if deploy:
        ctx.step("deploy")
        deploy_latest(ctx)
    ctx.note(f"VPS {ctx.config.require('VPS_IP')} configurado.")


def bind_all() -> None:
    registry.bind("refresh_known_host", refresh_known_host)
    registry.bind("install_software", install_software)
    registry.bind("load_credentials", load_credentials)
    registry.bind("bootstrap_vps", bootstrap_vps)
