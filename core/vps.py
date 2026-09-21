from __future__ import annotations

import difflib
import re

from .envfile import Config, split_list
from .errors import TaskError
from .ssh import Remote, capture, quote, reachable, run, succeeds

SUDO = 'sudo -n'


# --- tabla de rutas publicas -----------------------------------------------
#
# Vive aca y no en `core/tasks/vps_setup.py`, que es quien escribe el Caddyfile,
# porque la misma tabla la lee el build: si una SPA se publica bajo `/admin`,
# Vite tiene que compilarla con ese `base` o sus assets se piden en la raiz.
# Ese es todo el motivo por el que la ruta de cada SPA es un dato y no un eje —
# dos botones distintos tienen que leer exactamente el mismo valor.
#
# La tabla dice bajo que ruta se publica cada cosa. NO dice quien la sirve: un
# repo puede publicar su SPA en `/terminal` porque un proxy la mapea ahi o
# porque su propio backend la montó ahi, y al build le da igual cual de las dos.
# Por eso la clave es `PUBLIC_ROUTES` y no `CADDY_ROUTES`: Caddy es UN
# consumidor de la tabla, no su dueño. Haberlas confundido hacia que un repo sin
# proxy no tuviera donde declarar su ruta publica, y sus builds salian apuntando
# a la raiz.

# `$CLAVE` en una tabla de la configuracion, para no repetir un valor que ya
# esta cargado en otra clave (`$BACKEND_HOST:$BACKEND_PORT`).
_REF = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')


def expand_refs(config: Config, texto: str, donde: str) -> str:
    """`texto` con cada `$CLAVE` reemplazada por su valor; `donde` nombra la fila en el error."""
    def valor(ref: re.Match) -> str:
        clave = ref.group(1)
        resuelto = config.get(clave).strip()
        if not resuelto:
            raise TaskError(f'«{donde}» usa ${clave}, y esa clave esta vacia en Configuracion.')
        return resuelto.rstrip('/')
    return _REF.sub(valor, texto)


ROUTE_KINDS = ('proxy', 'spa', 'static')


class Route:
    """Una fila de `PUBLIC_ROUTES` ya interpretada."""

    __slots__ = ('pattern', 'kind', 'target')

    def __init__(self, pattern: str, kind: str, target: str):
        self.pattern, self.kind, self.target = pattern, kind, target

    @property
    def catch_all(self) -> bool:
        return self.pattern == '*'

    @property
    def prefix(self) -> str:
        """El prefijo que Caddy tiene que recortar: `/admin/*` -> `/admin`."""
        return self.pattern[:-2] if self.pattern.endswith('/*') else self.pattern


def parse_routes(lineas: list[str]) -> list[Route]:
    """Interpreta la tabla. Sin efectos, para poder probarla contra un Caddyfile real.

    Corta en la primera fila que no entiende en vez de saltearla: una regla que
    se ignora en silencio no falla al escribir, falla en produccion cuando el
    trafico que tenia que ir al backend cae en el catch-all de la SPA.
    """
    rutas: list[Route] = []
    for linea in lineas:
        partes = linea.split()
        if len(partes) != 3:
            raise TaskError(f'Regla mal formada: «{linea}». Va «<patron> <tipo> <destino>».')
        patron, tipo, destino = partes
        if not (patron == '*' or patron.startswith('/')):
            raise TaskError(f'Patron invalido en «{linea}»: empieza con / o es *.')
        if tipo not in ROUTE_KINDS:
            raise TaskError(f'Tipo desconocido «{tipo}» en «{linea}». Los tipos son: '
                            'proxy <host:puerto>, spa <carpeta>, static <ruta>.')
        rutas.append(Route(patron, tipo, destino))
    if not rutas:
        raise TaskError('La tabla de rutas esta vacia: sin reglas no hay nada que servir.')
    if any(r.catch_all for r in rutas[:-1]):
        raise TaskError('El catch-all «*» tiene que ser la ultima regla: lo que va '
                        'despues nunca se alcanza.')
    return rutas


def routes(config: Config) -> list[Route]:
    return parse_routes(route_lines(config))


def route_lines(config: Config) -> list[str]:
    """Las filas crudas de la tabla, sin interpretar.

    `CADDY_ROUTES` es el nombre viejo de la misma clave y se sigue leyendo: los
    repos que ya la tenian escrita no se quedan sin tabla por un renombre.
    """
    return (split_list(config.get('PUBLIC_ROUTES'))
            or split_list(config.get('CADDY_ROUTES')))


def resolve_target(config: Config, route: Route) -> str:
    """El destino de una regla con cada `$CLAVE` reemplazada por su valor."""
    fila = f'{route.pattern} {route.kind} {route.target}'
    return expand_refs(config, route.target, fila).rstrip('/')


# --- carpetas del servicio -------------------------------------------------
#
# Las que el servicio necesita fuera del repo —datos que suben los usuarios,
# exportaciones— con el permiso de cada una. Fuera del repo porque el deploy
# corre `git clean`, y lo que viva adentro esta a un flag de borrarse.

_MODE = re.compile(r'^[0-7]{3,4}$')


def service_dirs(config: Config) -> list[tuple[str, str]]:
    """`SERVICE_DIRS` interpretada: `(ruta, modo)` por fila, con `$CLAVE` resuelta."""
    carpetas = []
    for linea in split_list(config.get('SERVICE_DIRS')):
        partes = linea.split()
        if len(partes) != 2:
            raise TaskError(f'Carpeta mal formada: «{linea}». Va «<ruta> <modo>».')
        ruta = expand_refs(config, partes[0], linea).rstrip('/')
        modo = partes[1]
        if not ruta.startswith('/'):
            raise TaskError(f'«{linea}»: la ruta tiene que ser absoluta.')
        if not _MODE.match(modo):
            raise TaskError(f'«{linea}»: el modo va en octal, como 755 o 750.')
        carpetas.append((ruta, modo))
    return carpetas


def tmpfiles_path(service: str) -> str:
    return f'/etc/tmpfiles.d/{service}.conf'


def render_tmpfiles(carpetas: list[tuple[str, str]], user: str) -> str:
    """El `tmpfiles.d` que crea las carpetas y les deja dueno y modo.

    `d` crea lo que falta y corrige dueno y modo de lo que ya esta, sin tocar el
    contenido; el `-` final es sin limpieza por antiguedad.
    """
    return ''.join(f'd {ruta} {modo} {user} {user} -\n' for ruta, modo in carpetas)


def uses_proxy(config: Config) -> bool:
    """Si algo se interpone entre internet y el backend de este repo.

    La respuesta es "la tabla tiene alguna regla `proxy`", y no "la tabla existe".
    Una regla `proxy` es, por definicion, alguien adelante que reenvia al
    backend; si no hay ninguna, el backend contesta por si mismo aunque el repo
    publique diez SPA bajo diez rutas distintas.

    Antes esto era `hay tabla`, y de ahi salia que un repo sin proxy tampoco
    tenia rutas publicas. Son dos preguntas: esta contesta quien escucha, y
    `spa_base` contesta bajo que ruta se publica cada app.
    """
    try:
        tabla = routes(config)
    except TaskError:
        return False
    return any(route.kind == 'proxy' for route in tabla)


def declares_routes(config: Config) -> bool:
    """Si el repo declaro su tabla. Sin ella no hay ninguna ruta publica escrita."""
    return bool(route_lines(config))


def spa_base(config: Config, name: str) -> str | None:
    """Bajo que ruta se publica esa SPA: `/admin`, vacio si va en la raiz del
    dominio, o `None` si este repo no usa reverse proxy.

    `None` y `''` eran el mismo valor y son dos cosas distintas. Un repo que no
    declaro tabla no dijo bajo que ruta publica nada, y no hay ningun valor que
    escribirle: devolver `''` ahi le dejaba adentro un `base.generated.js` que
    nadie importa.

    Con tabla, una SPA que no esta en ella si vale `''`: lo que no tiene regla
    propia cuelga de la raiz.

    Lo que se pregunta es si hay tabla, no si hay proxy. Quien sirva la ruta
    —un proxy o el backend del propio repo— no cambia donde va a pedir sus
    assets el navegador, que es lo unico que el build necesita saber.
    """
    if not declares_routes(config):
        return None
    for route in routes(config):
        if route.kind == 'spa' and route.target == name:
            return '' if route.catch_all else route.prefix
    return ''

# Los paquetes que el despliegue da por dados, agrupados por lo que significan
# para quien elige (no por como se llaman en apt: `python` son tres paquetes).
# Vive aca y no en `core/tasks/vps_setup.py` porque `core/catalog.py` dibuja el
# eje con estas mismas claves y no puede importar de la capa de tareas.
PACKAGE_GROUPS: dict[str, list[str]] = {
    'python': ['python3', 'python3-venv', 'python3-pip'],
    'git': ['git'],
    'postgresql': ['postgresql', 'postgresql-contrib'],
    'postgis': ['postgis', 'postgresql-postgis-scripts'],
    'caddy': ['caddy'],
    'ufw': ['ufw'],
    'redis': ['redis-server'],
    'coturn': ['coturn'],
}

# Los que arrancan marcados: lo que necesita un backend Python detras de Caddy.
# No es una categoria ("base" vs "opcional"), es un default — por eso viaja como
# `AxisDef.defaults` y no como dos ejes separados.
DEFAULT_GROUPS = ['python', 'git', 'postgresql', 'caddy', 'ufw']


# --- rutas del despliegue --------------------------------------------------

def repo_name(config: Config) -> str:
    """Nombre del repo tal como queda en el VPS.

    Se deriva de GIT_REPO_URL, que es la unica fuente que coincide con lo que
    `git clone` va a crear del otro lado; el nombre de la carpeta local puede
    no coincidir y por eso no se usa como default silencioso.
    """
    url = config.get('GIT_REPO_URL')
    if url:
        return url.rstrip('/').rsplit('/', 1)[-1].removesuffix('.git')
    if config.repo_name:
        return config.repo_name
    raise TaskError('No se puede deducir el nombre del repo: falta GIT_REPO_URL.')


def deploy_root(config: Config) -> str:
    """Carpeta del repo en el VPS: `<VPS_DEPLOY_DIR>/<repo>`."""
    base = config.require('VPS_DEPLOY_DIR').rstrip('/')
    return f'{base}/{repo_name(config)}'


def ensure_deploy_dir(ctx, remote: Remote, config: Config) -> str:
    """Deja la carpeta del despliegue creada y a nombre del usuario que clona.

    `VPS_DEPLOY_DIR` suele apuntar a un lugar del sistema (`/srv`, `/opt`) que
    es de root. Un `mkdir -p` del padre no alcanza y ademas no falla —el padre
    ya existe—, asi que el problema recien aparecia en el `git clone`, con un
    "Permission denied" que no dice que lo que faltaba era el dueno.

    Por eso la carpeta se crea aca con sudo y se le pasa al usuario de
    despliegue: `git clone` acepta un directorio vacio como destino.
    """
    destino = deploy_root(config)
    if succeeds(remote, f'test -w {quote(destino)}'):
        return destino

    user = config.get('VPS_USER') or remote.user
    run(ctx, remote,
        f'{SUDO} mkdir -p {quote(destino)} && '
        f'{SUDO} chown {quote(user)}:{quote(user)} {quote(destino)}',
        check=False)
    if not succeeds(remote, f'test -w {quote(destino)}'):
        raise TaskError(
            f'{destino} no se pudo crear a nombre de {user}: el directorio padre '
            f'es de root y sudo sin contrasena no respondio. Corre "Configurar '
            f'sudo" para el usuario de despliegue, o crea la carpeta a mano.')
    ctx.ok(f'Carpeta de despliegue lista: {destino} (dueno {user}).')
    return destino


def remote_path(config: Config, *parts: str) -> str:
    """Ruta remota que respeta la misma jerarquia relativa que el repo local."""
    tail = '/'.join(p.strip('/').replace('\\', '/') for p in parts if p)
    root = deploy_root(config)
    return f'{root}/{tail}' if tail else root


def remote_python(config: Config) -> str:
    """Interprete del venv del server, dentro del repo desplegado."""
    return remote_path(config, config.require('VPS_PYTHON'))


def backend_listen(config: Config) -> tuple[str, int]:
    """Donde escucha el backend DENTRO del VPS.

    Lo usa `write_systemd_unit`, que es quien lo pone a escuchar. Estaba clavado
    en su firma (`host='0.0.0.0', port=443`) sin eje que lo ofreciera, asi que
    no habia forma de moverlo. Las reglas `proxy` de `PUBLIC_ROUTES` apuntan aca
    con `$BACKEND_HOST:$BACKEND_PORT`.

    Sin fallback propio: el default de `BACKEND_HOST` depende de si el repo
    tiene proxy y lo resuelve el esquema (`envfile.Config._dynamic_default`).
    Repetir aca un `127.0.0.1` era el mismo valor decidido en dos lugares.
    """
    return config.get('BACKEND_HOST'), config.port('BACKEND_PORT', 8000)


def is_loopback(host: str) -> bool:
    return host in ('127.0.0.1', 'localhost', '::1')


# --- cuentas y paquetes ----------------------------------------------------

def user_exists(remote: Remote, user: str) -> bool:
    return succeeds(remote, f'id -u {quote(user)}')


def install_packages(ctx, remote: Remote, packages: list[str]) -> None:
    """Instala paquetes con apt, sin preguntas y sin reinstalar lo que ya esta."""
    faltan = [p for p in packages if not succeeds(remote, f'dpkg -s {quote(p)}')]
    ya_estaban = [p for p in packages if p not in faltan]
    if ya_estaban:
        ctx.ok(f'Ya estaban instalados: {", ".join(ya_estaban)}')
    if not faltan:
        return

    ctx.info(f'Instalando: {", ".join(faltan)}')
    lista = ' '.join(quote(p) for p in faltan)
    run(ctx, remote, f'{SUDO} DEBIAN_FRONTEND=noninteractive apt-get update -qq')
    run(ctx, remote, f'{SUDO} DEBIAN_FRONTEND=noninteractive apt-get install -y {lista}')


def require_package(remote: Remote, package: str, group: str) -> None:
    """Corta si el paquete no esta, en vez de instalarlo por su cuenta.

    Instalar es `install_base_software` y el paquete es uno de sus grupos, igual
    que `postgresql`: los botones de configurar son el `bootstrap_db` de su
    servicio — la configuracion, no la instalacion. Que un boton de configurar
    corriera su propio `apt-get install` era la unica parte del catalogo donde
    la misma accion vivia en dos lugares (docs/atomicas.md 4.6).

    Vive aca y no en `core/tasks/vps_setup.py`, donde nacio, porque la misma
    pregunta —¿esta puesto lo que este boton da por dado?— se la hacen los tres
    botones de configurar un servicio, y uno de ellos esta en el otro modulo.
    """
    if succeeds(remote, f'dpkg -s {quote(package)}'):
        return
    raise TaskError(f'{package} no esta instalado en el VPS. '
                    f'Corre "Software base" con el grupo "{group}" marcado.')


def open_ports(ctx, remote: Remote, ports: list[str]) -> None:
    """Abre puertos en ufw si ufw manda; si no, los dice.

    Callar cuando ufw no esta activo no es "no hacer nada": el firewall puede
    estar en el panel del proveedor, y ahi los puertos siguen cerrados.
    """
    if not succeeds(remote, f'{SUDO} ufw status | grep -q active'):
        ctx.warn(f'ufw no esta activo: abre {", ".join(ports)} donde corresponda.')
        return
    for puerto in ports:
        run(ctx, remote, f'{SUDO} ufw allow {puerto}', check=False)
    ctx.ok(f'Puertos abiertos en ufw: {", ".join(ports)}')


# --- systemd ---------------------------------------------------------------

def service_name(config: Config) -> str:
    return repo_name(config)


def unit_path(service: str) -> str:
    return f'/etc/systemd/system/{service}.service'


# Los servicios systemd que Consola administra en el VPS. `proyecto` es el
# unico cuyo nombre sale del repo abierto; los otros dos son paquetes con
# nombre fijo, y son servicios de Consola porque Consola los configura
# (`configure_coturn`, `configure_caddy`). Reiniciarlos o leerles el journal no
# pide botones nuevos: pide que los que ya existen sepan a cual apuntar.
MANAGED_SERVICES = ('proyecto', 'coturn', 'caddy')
SERVICE_LABELS = {'proyecto': 'Servidor', 'coturn': 'Coturn', 'caddy': 'Caddy'}


def resolve_service(config: Config, which: str = 'proyecto') -> str:
    """El nombre real de la unidad detras del valor del eje `service`."""
    if not which or which == 'proyecto':
        return service_name(config)
    if which not in MANAGED_SERVICES:
        raise TaskError(f'Servicio desconocido: {which}')
    return which


def installed_services(remote: Remote, config: Config) -> list[str]:
    """Cuales de los tres servicios existen en ESTE VPS, en una sola consulta.

    El eje de `systemd_action` ofrecia los tres siempre, y en un VPS sin coturn
    elegirlo terminaba en un error que se podia haber evitado antes de apretar.
    Preguntar es una vuelta de SSH, asi que se pregunta por los tres juntos y el
    resultado se cachea (`core/catalog.py`), no una consulta por servicio.

    Devuelve la lista entera si no se puede preguntar: un VPS todavia sin llave
    o apagado no deberia dejar el boton sin valores que ofrecer.
    """
    nombres = {resolve_service(config, s): s for s in MANAGED_SERVICES}
    if not reachable(remote):
        return list(MANAGED_SERVICES)
    lista = ' '.join(quote(n) for n in nombres)
    salida = capture(
        remote, f'for s in {lista}; do systemctl cat "$s" >/dev/null 2>&1 && echo "$s"; done',
        check=False)
    return [nombres[linea] for linea in salida.split() if linea in nombres]


def service_exists(remote: Remote, service: str) -> bool:
    """Si el archivo de unidad que escribe Consola esta en su lugar.

    Es la pregunta que se hacen escribir y borrar la unidad del proyecto, no la
    de "systemd conoce este servicio": para eso esta `unit_installed`.
    """
    return succeeds(remote, f'test -f {quote(unit_path(service))}')


def unit_installed(remote: Remote, service: str) -> bool:
    """Si systemd conoce la unidad, este donde este su archivo.

    `service_exists` mira /etc/systemd/system, que es donde Consola escribe la
    del proyecto. Las de un paquete apt —coturn, caddy— viven en
    /lib/systemd/system, y con aquella pregunta daban `missing` estando
    instaladas y corriendo.
    """
    return succeeds(remote, f'systemctl cat {quote(service)}')


def service_state(remote: Remote, service: str) -> str:
    """`missing` | `active` | `inactive` | `failed`.

    Los scripts asumian que el servicio existia y morian con un error de
    systemctl; aca la distincion permite saltear el paso con un aviso.
    """
    if not unit_installed(remote, service):
        return 'missing'
    return capture(remote, f'systemctl is-active {quote(service)}', check=False).strip() or 'inactive'


def systemctl(ctx, remote: Remote, action: str, service: str, *, check: bool = True) -> int:
    """Una accion de systemd sobre el servicio del proyecto.

    Es la atomica que reusan `configure_service` y `update_remote` en vez de
    reimplementar `enable`/`start` cada uno por su lado (PLAN.md 7, caso 7).
    `configure_coturn` y `configure_caddy` tambien, desde que los tres cierran
    por `vps_server.bring_up_service`.
    """
    if action not in ALL_ACTIONS:
        raise TaskError(f'Accion de systemd desconocida: {action}')
    if action == 'daemon-reload':
        return run(ctx, remote, f'{SUDO} systemctl daemon-reload', check=check)
    return run(ctx, remote, f'{SUDO} systemctl {action} {quote(service)}', check=check)


BUTTON_ACTIONS = ('start', 'stop', 'restart', 'status')
MENU_ACTIONS = ('enable', 'disable', 'reload', 'is-active', 'is-enabled', 'daemon-reload')
ALL_ACTIONS = BUTTON_ACTIONS + MENU_ACTIONS


def render_unit(
    *,
    description: str,
    user: str,
    working_dir: str,
    exec_start: str,
    environment: dict[str, str] | None = None,
) -> str:
    """Texto de la unidad systemd. Se arma aca y se sube; no se edita a mano en el VPS."""
    env_lines = ''.join(
        f'Environment="{k}={v}"\n' for k, v in (environment or {}).items()
    )
    return (
        '[Unit]\n'
        f'Description={description}\n'
        'After=network.target postgresql.service\n'
        '\n'
        '[Service]\n'
        'Type=simple\n'
        f'User={user}\n'
        f'WorkingDirectory={working_dir}\n'
        f'{env_lines}'
        f'ExecStart={exec_start}\n'
        'Restart=always\n'
        'RestartSec=3\n'
        '\n'
        '[Install]\n'
        'WantedBy=multi-user.target\n'
    )


def write_config(ctx, remote: Remote, path: str, content: str) -> bool:
    """Escribe un archivo de configuracion del VPS solo si cambia. Dice si cambio.

    Los tres botones que configuran un servicio eran los unicos escritores de
    Consola que sobrescribian a ciegas: escribian siempre y reiniciaban siempre,
    aunque el archivo saliera identico al que ya estaba. El resto ya cumple la
    regla (`core/files.py::compare`, PLAN.md 7.5): se muestra que va a cambiar
    antes de tocar nada.

    El `cat` va sin sudo porque los tres archivos son legibles, y no por sudo:
    `SUDO_SPECIFIC` no lista `cat`. Si no se pudiera leer vuelve vacio y el
    archivo se escribe igual, que es lo que pasaba siempre.
    """
    # `ssh.capture` devuelve la salida ya sin bordes, asi que el lado nuevo se
    # compara igual: si no, el `\n` final lo daria siempre por distinto.
    actual = capture(remote, f'cat {quote(path)}', check=False)
    nuevo = content.strip()
    if actual == nuevo:
        ctx.info(f'Sin cambios: {path}')
        return False

    for linea in difflib.unified_diff(actual.splitlines(), nuevo.splitlines(),
                                      fromfile=f'{path} (ahora)',
                                      tofile=f'{path} (nuevo)', lineterm=''):
        ctx.info(linea)
    heredoc = f'{SUDO} tee {quote(path)} > /dev/null <<"CONSOLA_CONF"\n{content}CONSOLA_CONF'
    run(ctx, remote, heredoc)
    ctx.ok(f'Escrito: {path}')
    return True


def write_service_dirs(ctx, remote: Remote, service: str, user: str,
                       carpetas: list[tuple[str, str]]) -> bool:
    """Escribe el `tmpfiles.d` del servicio y lo aplica. Dice si el archivo cambio.

    Se aplica aunque no cambie: `systemd-tmpfiles --create` es idempotente, y
    asi tambien repone una carpeta que alguien borro a mano.
    """
    conf = tmpfiles_path(service)
    if not carpetas:
        if succeeds(remote, f'test -f {quote(conf)}'):
            run(ctx, remote, f'{SUDO} rm -f {quote(conf)}')
            ctx.warn(f'SERVICE_DIRS esta vacia: se borro {conf}. Las carpetas quedan donde estaban.')
        return False
    cambio = write_config(ctx, remote, conf, render_tmpfiles(carpetas, user))
    run(ctx, remote, f'{SUDO} systemd-tmpfiles --create {quote(conf)}')
    for ruta, modo in carpetas:
        ctx.ok(f'Carpeta lista: {ruta} ({modo}, dueno {user})')
    return cambio


def write_unit(ctx, remote: Remote, service: str, content: str) -> bool:
    """Escribe la unidad en el VPS y recarga systemd si cambio. No la habilita ni la arranca."""
    cambio = write_config(ctx, remote, unit_path(service), content)
    if cambio:
        run(ctx, remote, f'{SUDO} systemctl daemon-reload')
    return cambio


def journal_command(
    service: str,
    *,
    lines: int = 200,
    follow: bool = False,
    since: str = '',
    priority: str = '',
    grep: str = '',
) -> str:
    """Comando de `journalctl` con los filtros de la capacidad Ver logs.

    Es hermana de `systemctl`, no un valor suyo: los filtros no tienen sentido
    para start/stop y `logs` dejo de ser una accion de systemd (PLAN.md 1).
    """
    parts = [f'{SUDO} journalctl -u {quote(service)}', f'-n {int(lines)}']
    if follow:
        parts.append('-f')
    if since:
        parts.append(f'--since {quote(since)}')
    if priority:
        parts.append(f'-p {quote(priority)}')
    if grep:
        parts.append(f'--grep {quote(grep)}')
    parts.append('--no-pager')
    return ' '.join(parts)


# --- postgres del VPS ------------------------------------------------------

def postgres_port(remote: Remote) -> int:
    """Puerto real de Postgres en el VPS, preguntandoselo al propio servidor."""
    raw = capture(remote, f'{SUDO} -u postgres psql -tAc "SHOW port;"').strip()
    if not raw.isdigit():
        raise TaskError(f'Respuesta inesperada al pedir el puerto de Postgres: {raw!r}')
    return int(raw)


def health(remote: Remote, service: str) -> dict[str, str]:
    """Resumen de un vistazo para el chequeo de salud: acceso, servicio, disco y memoria.

    `acceso` va primero y corta. Las otras cuatro consultas usan `check=False`,
    asi que con el SSH caido devolvian vacio y `service_state` caia en 'missing':
    el resumen anunciaba un servidor destruido cuando la verdad era que no se
    llegaba a la maquina, y mandaba a arreglar lo que no estaba roto.
    """
    if not reachable(remote):
        return {'acceso': f'SIN ACCESO SSH a {remote.target}'}
    return {
        'acceso': f'ok ({remote.target})',
        'servicio': service_state(remote, service),
        'uptime': capture(remote, 'uptime -p', check=False),
        'disco': capture(remote, "df -h / | awk 'NR==2 {print $5\" usado de \"$2}'", check=False),
        'memoria': capture(remote, "free -h | awk 'NR==2 {print $3\" / \"$2}'", check=False),
    }
