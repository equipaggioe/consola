from __future__ import annotations
import secrets

from .. import github, ssh, vps
from ..errors import TaskError
from ..registry import registry

"""
Grupo VPS - setup.

`setup_ssh_key.py` era un unico comando shell de cuarenta lineas encadenadas con
`&&` que creaba el usuario, lo metia en sudo, escribia el sudoers, instalaba la
llave publica y probaba el login. Si el login fallaba habia que volver a correr
todo, incluida la creacion del usuario que ya existia.

Aca son dos atomicas —`ensure_deploy_access` y `configure_sudo`—: cada una
detecta su estado antes de actuar y se puede repetir sola. `setup_ssh_key` es la
compuesta que las corre en orden y cierra con la verificacion, que no es atomica
sino `ssh.reachable`: algo que necesitan casi todos los botones de SSH es
plomeria de nivel 0, no una tarea con boton (docs/atomicas.md 4.6).
"""

# `PACKAGE_GROUPS` y `DEFAULT_GROUPS` viven en `core/vps.py`: el catalogo los
# necesita para dibujar el eje y no puede importar de esta capa.
PACKAGE_GROUPS = vps.PACKAGE_GROUPS
DEFAULT_GROUPS = vps.DEFAULT_GROUPS

SUDO_MODES = ('all', 'specific', 'none')
# Modo 'specific': la lista tiene que cubrir TODOS los `sudo -n` que corre el
# resto de Consola, o el VPS queda a medias sin decir por que. Se habia recortado
# a tres comandos y dejaba afuera `tee` (unidad systemd y turnserver.conf), `ufw`
# (puertos de coturn) y `rm` (limpieza del servicio). Al agregar el eje sudo_mode
# el modo dejo de ser inalcanzable, asi que el hueco pasaba de latente a real.
SUDO_SPECIFIC = (
    '/usr/bin/apt-get',     # instalar y purgar paquetes
    '/usr/bin/apt',         # interfaz alternativa
    '/usr/bin/dpkg',        # consultar lo ya instalado
    '/usr/bin/systemctl',   # arrancar, parar y recargar el servicio
    '/usr/bin/journalctl',  # leer los logs del servicio
    '/usr/bin/tee',         # escribir la unidad systemd y turnserver.conf
    '/usr/bin/sed',         # habilitar coturn en /etc/default/coturn
    '/usr/sbin/ufw',        # abrir los puertos de coturn
    '/bin/mkdir',           # crear las carpetas del despliegue
    '/bin/chown',           # dueno de archivos y carpetas
    '/bin/chmod',           # permisos
    '/bin/rm',              # borrar la unidad al limpiar el VPS
)

REMOTE_KEY = '~/.ssh/id_ed25519'
TURN_PORT = 3478
RELAY_RANGE = (49160, 49360)


def _root_run(ctx, command: str, *, check: bool = True) -> int:
    """Comando como root, antes de que exista el usuario de despliegue.

    Es el unico momento en que Consola se conecta con contrasena: se pide al
    usuario en el momento y nunca se guarda en ningun archivo. `ask_once` la
    recuerda para el resto de la corrida, porque la compuesta abre una conexion
    por atomica y preguntarla dos veces seria un impuesto de la atomizacion.

    La contrasena es el ultimo recurso, no el primero: `ssh` prueba las llaves
    y solo si ninguna sirve la pide, asi que en un VPS donde root ya tiene la
    llave instalada no llega a usarse.
    """
    host = ctx.config.require('VPS_IP')
    root = ctx.config.get('ROOT_USER', 'root')
    opciones = ['-o', 'StrictHostKeyChecking=no']

    password = ctx.ask_once(f'Contrasena de {root}@{host}', secret=True)
    entorno = None
    if password:
        opciones += ssh.PASSWORD_OPTS
        entorno = ssh.password_env(password)
    return ctx.run(['ssh', *opciones, f'{root}@{host}', command], env=entorno, check=check)


# --- atomicas de acceso ----------------------------------------------------

def refresh_known_host(ctx) -> str:
    """Olvida la huella vieja del VPS.

    Despues de reinstalar el servidor cambia la huella y todas las conexiones
    fallan con un error de "host key verification" que no dice como arreglarlo.

    Solo borra la entrada vieja: la nueva la vuelve a anotar la primera conexion
    de cualquier otra atomica, que se conecta con `StrictHostKeyChecking=no`.
    """
    host = ctx.config.require('VPS_IP')
    ssh.forget_host(ctx, host)
    return host


def ensure_deploy_access(ctx) -> str:
    """Da de alta la cuenta de despliegue y le instala la llave con la que se entra.

    Eran dos atomicas, `ensure_remote_user` e `install_public_key`. Se fusionaron
    porque la primera no pasaba el criterio del 1 de docs/atomicas.md: nadie la
    corre sola, y si lo hiciera quedaria con un usuario al que no puede entrar.
    Tampoco servia como casilla desmarcable, porque el paso ya era idempotente y
    saltearlo solo ahorraba un `id -u`.

    Fusionarlas ademas baja de tres a dos las conexiones de root que abre la
    compuesta, y con eso las veces que pide la contrasena.
    """
    user = ctx.config.get('VPS_USER')
    quoted = ssh.quote(user)
    key_name = ctx.config.require('VPS_KEY_NAME')
    privada = ssh.ensure_local_keypair(ctx, key_name, comment=ctx.config.repo_name)
    publica = ssh.public_key(privada)

    _root_run(ctx, (
        f'if id -u {quoted} >/dev/null 2>&1; then echo "[OK] El usuario ya existe."; '
        f'else useradd -m -s /bin/bash {quoted} && echo "[OK] Usuario creado."; fi; '
        'if getent group sudo >/dev/null 2>&1; then '
        f'  usermod -aG sudo {quoted} && echo "[OK] Agregado al grupo sudo."; '
        'else echo "[AVISO] Este sistema no tiene grupo sudo."; fi; '
        f'home="$(getent passwd {quoted} | cut -d: -f6)"; '
        'if [ -z "$home" ]; then echo "[ERROR] El usuario no tiene home."; exit 1; fi; '
        'mkdir -p "$home/.ssh" && chmod 700 "$home/.ssh"; '
        'auth="$home/.ssh/authorized_keys"; '
        f'if [ -f "$auth" ] && grep -qxF -- {ssh.quote(publica)} "$auth"; then '
        '  echo "[OK] La llave ya estaba instalada."; '
        f'else printf "%s\\n" {ssh.quote(publica)} >> "$auth" && echo "[OK] Llave instalada."; fi; '
        f'chmod 600 "$auth" && chown -R {quoted}:{quoted} "$home/.ssh"'
    ))
    return user


def configure_sudo(ctx, mode: str = 'all') -> str:
    """Escribe la regla de sudo sin contrasena para el usuario de despliegue.

    Sin esto, cada `systemctl restart` remoto se cuelga esperando una contrasena
    que nadie puede escribir desde una pestana de consola.
    """
    if mode not in SUDO_MODES:
        raise TaskError(f'Modo de sudo invalido: {mode!r}. Usa {" | ".join(SUDO_MODES)}.')
    if mode == 'none':
        ctx.info('Modo "none": no se toca el sudoers.')
        return mode

    user = ctx.config.get('VPS_USER')
    archivo = f'/etc/sudoers.d/consola-{user}'
    if mode == 'all':
        reglas = f'{user} ALL=(ALL) NOPASSWD: ALL'
    else:
        reglas = (f'{user} ALL=(root) NOPASSWD: {", ".join(SUDO_SPECIFIC)}\n'
                  f'{user} ALL=(postgres) NOPASSWD: /usr/bin/psql')

    _root_run(ctx, (
        f'printf "%s\\n" {ssh.quote(reglas)} > {ssh.quote(archivo)} && '
        f'chmod 440 {ssh.quote(archivo)} && visudo -cf {ssh.quote(archivo)}'
    ))
    ctx.ok(f'Sudo sin contrasena configurado ({mode}).')
    return mode


# --- atomicas de software --------------------------------------------------

def install_base_software(ctx, groups: list[str] | None = None) -> list[str]:
    """Instala los paquetes de los grupos elegidos, salteando lo ya instalado."""
    elegidos = groups or DEFAULT_GROUPS
    desconocidos = [g for g in elegidos if g not in PACKAGE_GROUPS]
    if desconocidos:
        raise TaskError(f'Grupos de paquetes desconocidos: {", ".join(desconocidos)}')

    remote = ssh.resolve_remote(ctx.config)
    paquetes = [p for grupo in elegidos for p in PACKAGE_GROUPS[grupo]]
    vps.install_packages(ctx, remote, paquetes)
    return paquetes


def install_coturn(ctx, realm: str = '') -> str:
    """Aprovisiona un servidor TURN para llamadas detras de NAT simetrico."""
    remote = ssh.resolve_remote(ctx.config)
    dominio = realm or ctx.config.get('CF_DOMAIN_NAME') or remote.host
    secreto = secrets.token_hex(24)
    ctx.guard(secreto)

    vps.install_packages(ctx, remote, ['coturn'])
    conf = '\n'.join([
        f'listening-port={TURN_PORT}',
        'fingerprint',
        'use-auth-secret',
        f'static-auth-secret={secreto}',
        f'realm={dominio}',
        f'min-port={RELAY_RANGE[0]}',
        f'max-port={RELAY_RANGE[1]}',
        f'external-ip={remote.host}',
        'no-cli',
    ]) + '\n'

    ssh.run(ctx, remote, f'sudo -n tee /etc/turnserver.conf > /dev/null <<"TURN_CONF"\n{conf}TURN_CONF')
    ssh.run(ctx, remote, 'sudo -n sed -i "s/^#TURNSERVER_ENABLED=1/TURNSERVER_ENABLED=1/" /etc/default/coturn',
            check=False)

    if ssh.succeeds(remote, 'sudo -n ufw status | grep -q active'):
        ssh.run(ctx, remote, f'sudo -n ufw allow {TURN_PORT}/tcp && sudo -n ufw allow {TURN_PORT}/udp')
        ssh.run(ctx, remote, f'sudo -n ufw allow {RELAY_RANGE[0]}:{RELAY_RANGE[1]}/udp')

    vps.systemctl(ctx, remote, 'enable', 'coturn')
    vps.systemctl(ctx, remote, 'restart', 'coturn')
    ctx.ok(f'coturn escuchando en {remote.host}:{TURN_PORT} (realm {dominio}).')
    ctx.warn('Guarda el TURN_SECRET en la configuracion del servidor: no se persiste solo.')
    return secreto


# --- atomicas de GitHub ----------------------------------------------------

def generate_remote_keypair(ctx) -> str:
    """Crea la llave SSH del VPS (la que usa para clonar de GitHub) si falta."""
    remote = ssh.resolve_remote(ctx.config)
    if ssh.succeeds(remote, f'test -f {REMOTE_KEY}.pub'):
        ctx.ok('El VPS ya tiene su llave SSH.')
    else:
        ssh.run(ctx, remote, f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
                             f'ssh-keygen -t ed25519 -f {REMOTE_KEY} -N ""')
    publica = ssh.capture(remote, f'cat {REMOTE_KEY}.pub')
    if not publica:
        raise TaskError('La llave publica del VPS quedo vacia.')
    return publica


def register_github_key(ctx) -> dict:
    """Sube la llave publica del VPS a GitHub, por titulo."""
    token = ctx.config.require('GITHUB_TOKEN')
    ctx.guard(token)
    return github.register_key(ctx, token,
                               title=ctx.config.require('GITHUB_KEY_TITLE'),
                               public_key=generate_remote_keypair(ctx))


def test_github_ssh(ctx) -> bool:
    """Comprueba que el VPS puede autenticarse contra GitHub."""
    remote = ssh.resolve_remote(ctx.config)
    salida = ssh.capture(remote, 'ssh -o StrictHostKeyChecking=no -T git@github.com 2>&1 || true',
                         check=False)
    ctx.info(salida)
    ok = 'successfully authenticated' in salida.lower()
    (ctx.ok if ok else ctx.warn)('GitHub reconoce la llave.' if ok else 'GitHub todavia no reconoce la llave.')
    return ok


# --- compuestas ------------------------------------------------------------

def setup_ssh_key(
    ctx,
    sudo_mode: str = 'all',
    *,
    access: bool = True,
    sudo: bool = True,
    verify: bool = True,
) -> None:
    """Compuesta: acceso (cuenta + llave) -> sudo -> verificacion.

    La verificacion no es un paso atomico con nombre propio: es `ssh.reachable`,
    la plomeria que comparten las once puertas de `resolve_remote`. Lo mismo que
    verifica el final del setup es lo que `health_check` informa despues.
    """
    if access:
        ctx.step('Acceso de despliegue')
        ensure_deploy_access(ctx)
    if sudo:
        ctx.step('Sudo sin contrasena')
        configure_sudo(ctx, sudo_mode)
    if verify:
        ctx.step('Prueba de login')
        remote = ssh.resolve_remote(ctx.config)
        if ssh.reachable(remote):
            ctx.ok(f'Login sin contrasena funcionando: {remote.target}')
        else:
            ctx.error(f'No se pudo entrar como {remote.target} con la llave.')


def setup_github_ssh(ctx, *, generate: bool = True, register: bool = True,
                     verify: bool = True) -> None:
    """Compuesta: llave del VPS -> registro en GitHub -> prueba."""
    if generate:
        ctx.step('Llave del VPS')
        generate_remote_keypair(ctx)
    if register:
        ctx.step('Registro en GitHub')
        register_github_key(ctx)
    if verify:
        ctx.step('Prueba contra GitHub')
        test_github_ssh(ctx)


def bootstrap_vps(ctx, sudo_mode: str = 'all', groups: list[str] | None = None, *,
                  known_host: bool = True,
                  ssh_key: bool = True, software: bool = True,
                  github_ssh: bool = True, deploy: bool = True,
                  database: bool = True, service: bool = True) -> None:
    """Compuesta de compuestas: el VPS desde cero (PLAN.md 7, caso 8).

    Encadena capacidades que ya tienen su propio boton compuesto. Si un paso
    falla, la receta se detiene ahi: cada compuesta interna ya sabe revertir lo
    suyo, asi que la externa no necesita un rollback propio ademas.

    `sudo_mode` y `groups` se reenvian a las compuestas de adentro. No es
    duplicar sus ejes: un parametro que el bootstrap no reenvia queda clavado en
    su default y el eje del boton suelto no sirve de nada aca — el mismo agujero
    que tenia `sudo_mode` antes de docs/atomicas.md 4.6, una capa mas arriba.
    """
    from . import database as db_tasks
    from . import vps_server

    if known_host:
        ctx.step('known_hosts')
        refresh_known_host(ctx)
    if ssh_key:
        ctx.step('Acceso SSH')
        setup_ssh_key(ctx, sudo_mode)
    if software:
        ctx.step('Software base')
        install_base_software(ctx, groups)
    if github_ssh:
        ctx.step('GitHub SSH')
        setup_github_ssh(ctx)
    if deploy:
        ctx.step('Codigo en el VPS')
        vps_server.update_remote(ctx, restart=False)
    if database:
        ctx.step('Base de datos')
        db_tasks.bootstrap_db(ctx, scope='remoto')
        db_tasks.rebuild_db(ctx, scope='remoto')
    if service:
        ctx.step('Servicio systemd')
        vps_server.install_systemd(ctx)
    ctx.note('Bootstrap completo del VPS.')


def bind_all() -> None:
    registry.bind('refresh_known_host', refresh_known_host)
    registry.bind('setup_ssh_key', setup_ssh_key)
    registry.bind('setup_github_ssh', setup_github_ssh)
    registry.bind('install_software', install_base_software)
    registry.bind('install_coturn', install_coturn)
    registry.bind('bootstrap_vps', bootstrap_vps)
