from __future__ import annotations
from .. import envfile, ssh, vps
from ..errors import TaskError
from ..process import which_any
from ..registry import registry

"""
Grupo VPS - server.

`update_remote.py` eran 607 lineas en un solo archivo: clonar o actualizar el
repo, crear el venv, instalar dependencias, subir el `.env` y los certificados,
generar la migracion y reiniciar el servicio. Todo o nada: para recopiar un
certificado habia que rehacer el `git pull`, el venv y el `pip install`.

Aca cada paso es una atomica con boton propio, `publish_code` encadena los
cuatro que dejan el codigo listo en el VPS y `update_remote` le suma migrar y
reiniciar, saltando el reinicio con un aviso si el servicio todavia no existe en
vez de fallar.

Que cuenta como atomica: una accion que alguien pediria sola, aunque por dentro
llame a media docena de funciones. Por eso `clone_repository` y
`ensure_remote_venv` dejaron de estar sueltas — nadie pide "solo clonar" ni
"solo crear el venv" — y por eso aparecio `push_repository`, que el script
original no tenia y sin la cual el despliegue publica el commit de otro.

Las credenciales de git para el push no las administra Consola: salen del
entorno (agente SSH para `git@github.com:...`, credential helper para `https://`).
"""

def _remote(ctx) -> ssh.Remote:
    return ssh.resolve_remote(ctx.config)


def _server_rel(ctx) -> str:
    return ctx.config.get('SERVER_DIR', 'server')


def _venv_path(ctx) -> str:
    return vps.remote_path(ctx.config, _server_rel(ctx), '.venv')


# --- codigo local ----------------------------------------------------------

def _ensure_git(ctx) -> None:
    """Git en el PATH y la carpeta abierta siendo un repo de verdad."""
    if not which_any(['git', 'git.exe']):
        raise TaskError('No se encontro Git en el PATH.')
    if not ctx.path('.git').exists():
        raise TaskError(f'La carpeta abierta no es un repositorio git: {ctx.root}')


def _current_branch(ctx) -> str:
    rama = ctx.capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if rama == 'HEAD':
        raise TaskError('El repo local esta en HEAD desacoplado: no hay rama que empujar.')
    return rama


def _head(ctx) -> str:
    return ctx.capture(['git', 'rev-parse', '--short', 'HEAD'])


def _already_pushed(ctx, upstream: str) -> bool:
    """Si el remoto ya tiene exactamente lo que tiene la rama local.

    El `fetch` de antes no es decorativo: sin el, un push hecho desde otra
    maquina no se ve y el paso anunciaria trabajo pendiente que ya no existe.
    """
    ctx.run(['git', 'fetch', '--quiet'], check=False, echo=False)
    local = ctx.capture(['git', 'rev-parse', 'HEAD'], check=False)
    remoto = ctx.capture(['git', 'rev-parse', upstream], check=False)
    return bool(local) and local == remoto


def push_repository(ctx) -> str:
    """Empuja la rama local a su remoto. Es la mitad del despliegue que faltaba.

    El VPS hace `git pull` de GitHub, no de esta maquina: sin este paso,
    "actualizar remoto" publica el ultimo commit que alguien subio a mano y el
    codigo de la carpeta abierta puede diferir del que corre en el servidor sin
    que nada lo avise.

    Empuja y nada mas: no commitea. Que entra en un commit y con que mensaje es
    una decision del trabajo, no del despliegue — un `git add -A` automatico se
    lleva puesto lo que estaba a medias. Si hay cambios sin commitear lo avisa
    con la lista a la vista, pero no corta: `git push` nunca sube trabajo sin
    commitear, y decidir empujar de todos modos es del que aprieta el boton.

    Vive en este modulo, y no en uno de git aparte, porque es exactamente la
    mitad local del mismo paso que `sync_repository` completa del otro lado.
    """
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    sucio = ctx.capture(['git', 'status', '--porcelain'], check=False)

    if sucio:
        ctx.warn(
            f'El repo local tiene cambios sin commitear (no se empujan):\n{sucio}')

    upstream = ctx.capture(
        ['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'], check=False)

    if not upstream:
        ctx.info(f'La rama {rama} todavia no tiene upstream: se crea en origin.')
        ctx.run(['git', 'push', '-u', 'origin', rama])
    elif _already_pushed(ctx, upstream):
        ctx.ok(f'{rama} ya esta al dia con {upstream}: no hay nada que empujar.')
        return _head(ctx)
    else:
        ctx.run(['git', 'push'])

    revision = _head(ctx)
    ctx.ok(f'{rama} empujada en {revision}.')
    return revision


# --- codigo en el VPS ------------------------------------------------------

def _remote_state(remote: ssh.Remote, destino: str) -> tuple[bool, str]:
    """Si el repo ya esta clonado en el VPS y que tiene sin commitear, en UNA
    sola conexion.

    Antes eran dos (`ssh.path_exists` y despues `git status`). En Windows el
    multiplexado esta desactivado (`core/ssh.py::_control_args`), asi que cada
    `ssh` abre un handshake nuevo: agrupar las preguntas que se contestan juntas
    no es microoptimizacion, es una oportunidad menos de quedarse esperando
    contra el timeout de 30s.
    """
    salida = ssh.capture(
        remote,
        f'if [ -d {ssh.quote(destino + "/.git")} ]; then echo CLONADO; '
        f'cd {ssh.quote(destino)} && git status --porcelain; else echo VACIO; fi',
        check=False)
    lineas = salida.splitlines()
    if not lineas or lineas[0].strip() != 'CLONADO':
        return False, ''
    return True, '\n'.join(lineas[1:]).strip()


def sync_repository(ctx, discard_changes: bool = False) -> None:
    """Actualiza el repo del VPS.

    `discard_changes` elige que hacer si el VPS tiene cambios sin commitear:
    False pregunta (dialogo, con la lista de archivos a la vista), True los
    descarta sin preguntar. Es un parametro y no una constante porque las dos
    respuestas son legitimas segun el VPS, y el script original obligaba a
    editar la cabecera para cambiar de una a otra.

    Dos conexiones SSH: una para preguntar en que estado esta el repo, otra para
    dejarlo al dia. Eran cinco, y la unica decision que obliga a cortar en dos es
    la pregunta al usuario — todo lo que va antes se contesta junto, y todo lo
    que va despues se aplica junto.
    """
    remote = _remote(ctx)
    destino = vps.deploy_root(ctx.config)
    clonado, sucio = _remote_state(remote, destino)

    if not clonado:
        # Primera corrida: clonar ya deja el repo en origin/HEAD, no hay nada
        # que traer despues. "Solo clonar" no es un boton aparte — nadie lo pide
        # dos veces.
        url = ctx.config.require('GIT_REPO_URL')
        vps.ensure_deploy_dir(ctx, remote, ctx.config)
        ssh.run(ctx, remote, f'git clone {ssh.quote(url)} {ssh.quote(destino)}')
        ctx.ok(f'Repo clonado en {destino}.')
        return

    limpiar = ''
    if sucio:
        ctx.warn(f'El repo del VPS tiene cambios sin commitear:\n{sucio}')
        if not discard_changes and not ctx.confirm(
                'Descartar esos cambios y actualizar igual?', danger=True):
            raise TaskError('Actualizacion cancelada: el VPS tiene cambios sin commitear.')
        limpiar = 'git reset --hard && git clean -fd && '

    # Descartar, traer y posicionarse van en el mismo comando: es un solo tramo
    # sin decision en el medio. `git reset --hard "@{u}"` ya imprime
    # "HEAD is now at <sha> <mensaje>", asi que la revision queda en el log sin
    # gastar otra conexion en un `git rev-parse` puramente decorativo — que era,
    # justamente, el comando que se colgaba.
    ssh.run(ctx, remote,
            f'cd {ssh.quote(destino)} && {limpiar}'
            'git fetch --all && git reset --hard "@{u}"')
    ctx.ok('Repo del VPS actualizado.')


def _ensure_venv(ctx) -> str:
    """Crea el virtualenv del servidor en el VPS si falta.

    Tampoco es una atomica: un venv vacio no le sirve a nadie, se crea para
    instalar algo dentro. Es el primer tramo de `install_remote_deps`.
    """
    remote = _remote(ctx)
    venv = _venv_path(ctx)
    if ssh.path_exists(remote, f'{venv}/bin/python'):
        ctx.info(f'El venv del VPS ya existe: {venv}')
        return venv
    ssh.run(ctx, remote, f'python3 -m venv {ssh.quote(venv)}')
    ctx.ok(f'venv creado: {venv}')
    return venv


def install_remote_deps(ctx) -> None:
    """Deja el entorno Python del VPS listo: crea el venv si falta e instala
    `requirements.txt` adentro.

    Los dos tramos van juntos porque la accion que se pide es "que el servidor
    tenga sus dependencias"; crear el venv es su primer paso, no otro boton.
    """
    remote = _remote(ctx)
    venv = _ensure_venv(ctx)
    requisitos = vps.remote_path(ctx.config, _server_rel(ctx), 'requirements.txt')
    if not ssh.path_exists(remote, requisitos):
        raise TaskError(f'No existe {requisitos} en el VPS.')
    ssh.run(ctx, remote, f'{ssh.quote(venv + "/bin/pip")} install -q -r {ssh.quote(requisitos)}')
    ctx.ok('Dependencias del VPS instaladas.')


def upload_secret_files(ctx) -> list[str]:
    """Sube los archivos que nunca viajan por git: `.env`, certificados, credenciales.

    Las rutas salen de `SECRET_FILES`, en Configuracion, relativas a la raiz del
    repo. Vivian en un campo del panel repetido en los cuatro botones del
    deploy, cada uno con su copia guardada; que archivos secretos tiene un
    proyecto no es una decision de quien aprieta el boton, es una propiedad de
    la carpeta.

    No hay lista por defecto: el script original se equivocaba en las dos puntas
    — tres nombres fijos en la cabecera mas un `rglob('.env')` que barria el
    repo entero y mandaba a produccion el `.env.example` y el de los tests.

    Es el paso que mas se pide suelto ("solo recopiar los certificados"), y por
    eso tiene boton propio en vez de vivir dentro de la actualizacion completa.
    """
    remote = _remote(ctx)
    elegidos = envfile.split_list(ctx.config.get('SECRET_FILES'))
    if not elegidos:
        ctx.warn('No hay archivos que copiar: escribe sus rutas en '
                 '"Archivos a copiar", en Configuracion.')
        return []

    subidos: list[str] = []
    for rel in elegidos:
        local = ctx.path(rel)
        if not local.is_file():
            ctx.warn(f'No existe localmente, se saltea: {rel}')
            continue
        subidos.append(ssh.upload(ctx, remote, local, vps.remote_path(ctx.config, rel),
                                  chmod='600'))

    if not subidos:
        ctx.warn(f'Ninguno de los {len(elegidos)} archivo(s) elegidos existe en el repo.')
    else:
        ctx.ok(f'{len(subidos)} de {len(elegidos)} archivo(s) subidos.')
    return subidos


def restart_service(ctx) -> str:
    """Reinicia el servicio del proyecto. Avisa y sigue si todavia no existe."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    estado = vps.service_state(remote, servicio)
    if estado == 'missing':
        ctx.warn(f'El servicio {servicio} todavia no existe: corre "Instalar servicio" primero.')
        return estado
    vps.systemctl(ctx, remote, 'restart', servicio)
    ctx.ok(f'Servicio {servicio} reiniciado.')
    return vps.service_state(remote, servicio)


# --- systemd ---------------------------------------------------------------

def write_systemd_unit(ctx, host: str = '0.0.0.0', port: int = 443) -> str:
    """Escribe el archivo `.service` en el VPS y recarga systemd. No lo arranca."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    server = _server_rel(ctx)
    python = f'{_venv_path(ctx)}/bin/python'
    app = ctx.config.get('UVICORN_APP', 'app.main:app')

    cert = vps.remote_path(ctx.config, ctx.config.get('CERT_FILE_PATH', f'{server}/certs/cert.pem'))
    key = vps.remote_path(ctx.config, ctx.config.get('KEY_FILE_PATH', f'{server}/certs/key.pem'))
    tls = f' --ssl-certfile {cert} --ssl-keyfile {key}' if ssh.path_exists(remote, cert) else ''

    unidad = vps.render_unit(
        description=f'Servidor de {servicio}',
        user=remote.user,
        working_dir=vps.remote_path(ctx.config, server),
        exec_start=f'{python} -m uvicorn {app} --host {host} --port {port}{tls}',
    )
    return vps.write_unit(ctx, remote, servicio, unidad)


def systemd_action(ctx, action: str = 'status') -> int:
    """Una accion de systemd sobre el servicio del proyecto."""
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    if vps.service_state(remote, servicio) == 'missing' and action not in ('daemon-reload',):
        raise TaskError(f'El servicio {servicio} no existe todavia en el VPS.')
    return vps.systemctl(ctx, remote, action, servicio, check=action not in ('status', 'is-active', 'is-enabled'))


def view_logs(ctx, lines: int = 200, follow: bool = True, since: str = '',
              priority: str = '', grep: str = '') -> int:
    """Sigue el journal del servicio con los filtros pedidos.

    Es capacidad hermana de `systemd_action`, no un valor suyo: los filtros no
    tienen sentido para start/stop (PLAN.md 1).
    """
    remote = _remote(ctx)
    servicio = vps.service_name(ctx.config)
    comando = vps.journal_command(servicio, lines=lines, follow=follow,
                                  since=since, priority=priority, grep=grep)
    return ssh.run(ctx, remote, comando, check=False)


# --- compuestas ------------------------------------------------------------

def install_systemd(ctx, host: str = '0.0.0.0', port: int = 443, *,
                    write: bool = True, enable: bool = True, start: bool = True) -> None:
    """Compuesta: escribir la unidad y reusar `systemd_action` para habilitarla.

    No reimplementa `enable` ni `start`: llama a la misma atomica que ya tiene
    su propio boton (PLAN.md 7, caso 7).
    """
    if write:
        ctx.step('Unidad systemd')
        write_systemd_unit(ctx, host, port)
    if enable:
        ctx.step('Habilitar al arranque')
        systemd_action(ctx, 'enable')
    if start:
        ctx.step('Arrancar')
        systemd_action(ctx, 'restart')
    ctx.note(f'Servicio {vps.service_name(ctx.config)} instalado.')


def publish_code(
    ctx,
    *,
    push: bool = False,
    pull: bool = True,
    deps: bool = True,
    upload: bool = True,
    discard_changes: bool = False,
) -> None:
    """Compuesta: push local -> codigo -> dependencias -> secretos.

    Deja el VPS con el codigo que corresponde y todo lo que necesita para
    arrancar, sin tocar nada que ya este corriendo. Los dos pasos que faltan
    para el despliegue completo —migrar y reiniciar— son justamente los que un
    VPS recien creado no puede hacer: migrar seria contra una base que todavia
    no existe, y reiniciar contra un servicio que todavia no esta instalado.

    Por eso existe aparte y no como cuatro casillas desmarcadas de
    `update_remote`: la usan los dos, `update_remote` agregandole esos dos
    pasos y `bootstrap_vps` tal cual.

    `push` arranca marcado: el VPS clona de GitHub y no de esta maquina, asi
    que desplegar sin empujar publica el commit de otro. Es el unico paso que
    sale de esta maquina antes de tocar el VPS, y no commitea nada — si hay
    cambios sin commitear, avisa y sigue.

    `deps` es condicional a proposito: si el repo no cambio, reinstalar es
    tiempo perdido, pero se pide igual tras tocar `requirements.txt`.
    """
    if push:
        ctx.step('Empujar el repo local a GitHub')
        push_repository(ctx)
    if pull:
        ctx.step('Actualizar el repo en el VPS')
        sync_repository(ctx, discard_changes)
    if deps:
        ctx.step('Instalar dependencias en el VPS')
        install_remote_deps(ctx)
    if upload:
        ctx.step('Copiar los archivos que no viajan por git')
        upload_secret_files(ctx)


def update_remote(
    ctx,
    *,
    push: bool = False,
    pull: bool = True,
    deps: bool = True,
    upload: bool = True,
    migrate: bool = True,
    restart: bool = True,
    discard_changes: bool = False,
) -> None:
    """Compuesta: `publish_code` -> migrar -> reiniciar.

    Seis pasos, uno por accion reconocible del dominio. El venv ya no es uno de
    ellos: se crea dentro de las dependencias, que es lo unico para lo que se
    crea.

    Los cuatro primeros no se reescriben aca: son `publish_code`, y sus cuatro
    banderas se le reenvian enteras. El panel sigue mostrando las seis casillas
    planas — la compuesta de adentro no se ve desde afuera y no tiene por que.

    El paso de migraciones solo **aplica** las que llegaron con el codigo
    (`alembic upgrade head`). El script original llamaba a `migrate_db.py`, que
    ademas las *generaba* contra la base del VPS: eso autogenera revisiones en
    produccion a partir de un modelo que quiza ni se commiteo, y deja al
    servidor con migraciones que el repo no tiene. Las revisiones se escriben en
    local (boton Migrar de Base de datos), se commitean y se despliegan; aca solo
    se corren.
    """
    from . import database as db_tasks

    publish_code(ctx, push=push, pull=pull, deps=deps, upload=upload,
                 discard_changes=discard_changes)
    if migrate:
        ctx.step('Ejecutar migraciones')
        db_tasks.apply_migrations(ctx, scope='remoto')
    if restart:
        ctx.step('Reiniciar el servicio')
        restart_service(ctx)
    ctx.note('Actualizacion del remoto completada.')


def bind_all() -> None:
    registry.bind('upload_secret_files', upload_secret_files)
    registry.bind('systemd_action', systemd_action)
    registry.bind('view_logs', view_logs)
    registry.bind('install_systemd', install_systemd)
    registry.bind('publish_code', publish_code)
    registry.bind('update_remote', update_remote)
