from __future__ import annotations

import re

from .envfile import Config, split_list
from .errors import TaskError
from .ssh import Remote, capture, quote, reachable, run, succeeds

SUDO = 'sudo -n'


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


def remote_path(config: Config, *parts: str) -> str:
    """Ruta remota que respeta la misma jerarquia relativa que el repo local."""
    tail = '/'.join(p.strip('/').replace('\\', '/') for p in parts if p)
    root = deploy_root(config)
    return f'{root}/{tail}' if tail else root


def remote_python(config: Config) -> str:
    """Interprete del venv del server, dentro del repo desplegado."""
    return remote_path(config, config.require('VPS_PYTHON'))


# --- systemd ---------------------------------------------------------------

def service_name(config: Config) -> str:
    """La unidad del repo cuando declara una sola. Es el nombre historico."""
    return repo_name(config)


# --- los servicios del repo ------------------------------------------------
#
# Un repo puede tener mas de un proceso largo: una API y un enviador de avisos,
# un servidor y un consumidor de cola. Para systemd son dos unidades y no hay
# nada que las distinga salvo su comando, asi que la tabla tiene filas
# «<sufijo> <tipo> <destino>», donde el tipo dice como se arma el comando.
#
# Tabla vacia = un solo servicio, llamado como el repo y corriendo `UVICORN_APP`.
# Es exactamente lo que habia antes de que la tabla existiera.

SERVICE_KINDS = ('uvicorn', 'python', 'command')
_SUFFIX = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')


class Service:
    """Una fila de `SERVICES` ya interpretada."""

    __slots__ = ('suffix', 'kind', 'target')

    def __init__(self, suffix: str, kind: str, target: str):
        self.suffix, self.kind, self.target = suffix, kind, target


def parse_services(lineas: list[str]) -> list[Service]:
    """Interpreta la tabla. Sin efectos, para poder probarla sin un VPS.

    Corta en la primera fila que no entiende, por el mismo motivo que
    `parse_routes`: un servicio que se ignora en silencio no falla al escribir,
    falla cuando alguien busca por que no corre nada.
    """
    servicios: list[Service] = []
    for linea in lineas:
        sufijo, _, resto = linea.strip().partition(' ')
        tipo, _, destino = resto.strip().partition(' ')
        destino = destino.strip()
        if not tipo or not destino:
            raise TaskError(f'Servicio mal formado: «{linea}». Va «<sufijo> <tipo> <destino>».')
        if not _SUFFIX.match(sufijo):
            raise TaskError(f'«{sufijo}» no sirve como sufijo de unidad: minusculas, numeros '
                            'y guiones, como «api» o «push».')
        if tipo not in SERVICE_KINDS:
            raise TaskError(f'Tipo desconocido «{tipo}» en «{linea}». Los tipos son: '
                            'uvicorn <app>, python <argumentos>, command <linea entera>.')
        servicios.append(Service(sufijo, tipo, destino))
    if len({s.suffix for s in servicios}) != len(servicios):
        raise TaskError('Hay dos servicios con el mismo sufijo: cada uno es una unidad '
                        'distinta y no pueden llamarse igual.')
    return servicios


def services(config: Config) -> list[Service]:
    """Los servicios del repo. Sin tabla, el unico de siempre."""
    tabla = parse_services(split_list(config.get('SERVICES')))
    if tabla:
        return tabla
    return [Service('', 'uvicorn', config.get('UVICORN_APP') or 'app.main:app')]


def unit_name(config: Config, service: Service) -> str:
    """`<repo>` cuando el repo declara uno solo, `<repo>-<sufijo>` cuando declara varios.

    El nombre sin sufijo es el que ya existe en los VPS desplegados: un repo que
    nunca declaro la tabla no tiene que ver su unidad renombrada por un cambio
    de Consola.
    """
    base = service_name(config)
    return f'{base}-{service.suffix}' if service.suffix else base


# Los servicios systemd que Consola administra en el VPS. `proyecto` es el
# unico cuyo nombre sale del repo abierto; los otros dos son paquetes con
# nombre fijo. Reiniciarlos o leerles el journal no pide botones nuevos: pide
# que los que ya existen sepan a cual apuntar.
PACKAGE_SERVICES = ('coturn', 'caddy')
PACKAGE_LABELS = {'coturn': 'Coturn', 'caddy': 'Caddy'}
# El valor historico del eje: "el servicio del repo", cuando el repo tiene uno
# solo. Se sigue aceptando porque es el default de `systemd_action` y
# `view_logs`, y porque un repo sin tabla no tiene otro nombre.
MAIN_SERVICE = 'proyecto'


def managed_services(config: Config) -> list[str]:
    """Los valores del eje `service` de ESTE repo.

    Los del repo primero —uno por fila de `SERVICES`, o `proyecto` si no hay
    tabla— y despues los dos paquetes.
    """
    try:
        propios = [s.suffix or MAIN_SERVICE for s in services(config)]
    except TaskError:
        propios = [MAIN_SERVICE]
    return propios + list(PACKAGE_SERVICES)


def service_labels(config: Config) -> dict[str, str]:
    """Como se llama cada valor del eje en la interfaz."""
    etiquetas = dict(PACKAGE_LABELS)
    try:
        tabla = services(config)
    except TaskError:
        tabla = []
    for servicio in tabla:
        if servicio.suffix:
            etiquetas[servicio.suffix] = servicio.suffix.replace('-', ' ').capitalize()
    etiquetas.setdefault(MAIN_SERVICE, 'Servidor')
    return etiquetas


def resolve_service(config: Config, which: str = MAIN_SERVICE) -> str:
    """El nombre real de la unidad detras del valor del eje `service`."""
    if which in PACKAGE_SERVICES:
        return which
    tabla = services(config)
    if not which or which == MAIN_SERVICE:
        # Sin tabla es el unico que hay; con tabla, el primero que se declaro.
        return unit_name(config, tabla[0])
    for servicio in tabla:
        if servicio.suffix == which:
            return unit_name(config, servicio)
    raise TaskError(f'Servicio desconocido: {which}')


def installed_services(remote: Remote, config: Config) -> list[str]:
    """Cuales de los servicios del eje existen en ESTE VPS, en una sola consulta.

    El eje de `systemd_action` ofrecia los tres siempre, y en un VPS sin coturn
    elegirlo terminaba en un error que se podia haber evitado antes de apretar.
    Preguntar es una vuelta de SSH, asi que se pregunta por los tres juntos y el
    resultado se cachea (`core/catalog.py`), no una consulta por servicio.

    Devuelve la lista entera si no se puede preguntar: un VPS todavia sin llave
    o apagado no deberia dejar el boton sin valores que ofrecer.
    """
    ejes = managed_services(config)
    nombres = {resolve_service(config, s): s for s in ejes}
    if not reachable(remote):
        return list(ejes)
    lista = ' '.join(quote(n) for n in nombres)
    salida = capture(
        remote, f'for s in {lista}; do systemctl cat "$s" >/dev/null 2>&1 && echo "$s"; done',
        check=False)
    return [nombres[linea] for linea in salida.split() if linea in nombres]


def unit_installed(remote: Remote, service: str) -> bool:
    """Si systemd conoce la unidad, este donde este su archivo.

    Las de un paquete apt —coturn, caddy— viven en /lib/systemd/system: mirar
    solo /etc/systemd/system las daba por `missing` estando instaladas y
    corriendo.
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
    """Una accion de systemd sobre un servicio del VPS."""
    if action not in ALL_ACTIONS:
        raise TaskError(f'Accion de systemd desconocida: {action}')
    if action == 'daemon-reload':
        return run(ctx, remote, f'{SUDO} systemctl daemon-reload', check=check)
    return run(ctx, remote, f'{SUDO} systemctl {action} {quote(service)}', check=check)


BUTTON_ACTIONS = ('start', 'stop', 'restart', 'status')
MENU_ACTIONS = ('enable', 'disable', 'reload', 'is-active', 'is-enabled', 'daemon-reload')
ALL_ACTIONS = BUTTON_ACTIONS + MENU_ACTIONS


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
    para start/stop y `logs` dejo de ser una accion de systemd (ADR-0023).
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
