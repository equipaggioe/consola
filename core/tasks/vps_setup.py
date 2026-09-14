from __future__ import annotations
import secrets

from .. import envfile, github, ssh, targets, vps
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
    '/bin/ln',              # symlink de /etc/caddy/Caddyfile al del repo
    '/bin/mkdir',           # crear las carpetas del despliegue
    '/bin/chown',           # dueno de archivos y carpetas
    '/bin/chmod',           # permisos
    '/bin/rm',              # borrar la unidad al limpiar el VPS
)

REMOTE_KEY = '~/.ssh/id_ed25519'
TURN_PORT = 3478
TURN_TLS_PORT = 5349
RELAY_RANGE = (49160, 49360)
CADDYFILE = '/etc/caddy/Caddyfile'
CADDY_DROPIN_DIR = '/etc/systemd/system/caddy.service.d'
CADDY_DROPIN = f'{CADDY_DROPIN_DIR}/override.conf'


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


# --- atomicas de comunicaciones --------------------------------------------

def _turn_secret(ctx) -> str:
    """El secreto con el que el backend firma las credenciales efimeras.

    Se genera una vez y queda en `.consola/config.env`. Antes salia de
    `secrets.token_hex` en cada corrida y solo se avisaba "guardalo": cada vez
    que alguien reconfiguraba coturn, el servidor pasaba a exigir un secreto que
    el backend ya no tenia, y las llamadas se caian sin que nada lo dijera.
    """
    secreto = ctx.config.get('TURN_SECRET')
    if secreto:
        ctx.info('Se reusa el TURN_SECRET de la configuracion del repo.')
        return secreto
    secreto = secrets.token_hex(24)
    envfile.upsert_value(envfile.config_path(str(ctx.root)), 'TURN_SECRET', secreto)
    ctx.ok('TURN_SECRET generado y guardado en .consola/config.env.')
    return secreto


def _relay_range(config) -> tuple[int, int]:
    """El rango de relay de `TURN_RELAY_RANGE`, en una clave y no en dos.

    Se valida aca y no en el eje porque ya no es un eje: el panel de
    configuracion guarda texto, y `49360-49160` tiene que fallar diciendo que
    esta invertido y no dejar a coturn sin arrancar.
    """
    crudo = config.get('TURN_RELAY_RANGE', f'{RELAY_RANGE[0]}-{RELAY_RANGE[1]}')
    partes = crudo.replace(':', '-').split('-')
    if len(partes) != 2 or not all(p.strip().isdigit() for p in partes):
        raise TaskError(f'TURN_RELAY_RANGE no es un rango: {crudo} (se espera 49160-49360).')
    desde, hasta = int(partes[0]), int(partes[1])
    if desde >= hasta:
        raise TaskError(f'El rango de relay esta invertido: {crudo}.')
    return desde, hasta


def configure_coturn(ctx, tls: bool = False, *, enable: bool = True,
                     start: bool = True) -> str:
    """Configura el servidor TURN para llamadas detras de NAT simetrico.

    El realm y los puertos salen de `config.env` y no del panel de parametros:
    el backend tiene que anunciar en sus `turn:` URLs exactamente lo que quedo
    en /etc/turnserver.conf, asi que son datos del despliegue y no una eleccion
    de la corrida.

    Reiniciar el servicio con la configuracion que ya tiene, o mirar su estado,
    tampoco son parametros de este boton: son `systemd_action` y `view_logs` con
    el eje `service` puesto en coturn, que son los mismos botones que ya
    existian para el servicio del proyecto. Lo que si es casilla es dejar la
    configuracion escrita SIN aplicarla, que es la ventana de mantenimiento:
    `start=False` la deja en /etc/turnserver.conf y avisa que coturn sigue con
    la vieja (`vps_server.bring_up_service`).
    """
    remote = ssh.resolve_remote(ctx.config)
    vps.require_package(remote, 'coturn', 'Coturn')

    dominio = ctx.config.get('PUBLIC_HOST') or remote.host
    port = ctx.config.port('TURN_PORT', TURN_PORT)
    relay_min, relay_max = _relay_range(ctx.config)
    secreto = _turn_secret(ctx)
    ctx.guard(secreto)

    lineas = [
        f'listening-port={port}',
        'fingerprint',
        'use-auth-secret',
        f'static-auth-secret={secreto}',
        f'realm={dominio}',
        f'min-port={relay_min}',
        f'max-port={relay_max}',
        f'external-ip={remote.host}',
        'no-cli',
    ]

    # El certificado es el mismo que ya sube el despliegue, no uno propio de
    # coturn: pedir un segundo par para el mismo dominio seria pedir dos veces
    # lo mismo. Si todavia no esta en el VPS se sigue sin TLS y se dice — dejar
    # `cert=` apuntando a un archivo que no existe deja el servicio sin arrancar.
    if tls:
        cert = vps.remote_path(ctx.config, ctx.config.get('CERT_FILE_PATH', 'server/certs/cert.pem'))
        key = vps.remote_path(ctx.config, ctx.config.get('KEY_FILE_PATH', 'server/certs/key.pem'))
        if ssh.path_exists(remote, cert) and ssh.path_exists(remote, key):
            lineas += [f'tls-listening-port={TURN_TLS_PORT}', f'cert={cert}', f'pkey={key}']
        else:
            ctx.warn(f'No hay certificado en el VPS ({cert}): coturn queda sin TLS.')
            tls = False

    conf = '\n'.join(lineas) + '\n'
    cambio = vps.write_config(ctx, remote, '/etc/turnserver.conf', conf)
    ssh.run(ctx, remote, 'sudo -n sed -i "s/^#TURNSERVER_ENABLED=1/TURNSERVER_ENABLED=1/" /etc/default/coturn',
            check=False)

    puertos = [f'{port}/tcp', f'{port}/udp', f'{relay_min}:{relay_max}/udp']
    if tls:
        puertos.append(f'{TURN_TLS_PORT}/tcp')
    vps.open_ports(ctx, remote, puertos)

    # Habilitar, reiniciar y comprobar es el mismo cierre que el de los otros
    # dos botones de configurar un servicio, y pasa por `systemd_action` — la
    # atomica que ya tiene boton propio — en vez de repetir aca su `systemctl`.
    from . import vps_server
    vps_server.bring_up_service(ctx, 'coturn', enable=enable, start=start, changed=cambio)

    ctx.ok(f'coturn escuchando en {remote.host}:{port} (realm {dominio}).')
    esquema = 'turns' if tls else 'turn'
    publicado = TURN_TLS_PORT if tls else port
    ctx.info(f'URLs para el backend: {esquema}:{dominio}:{publicado}?transport=udp, '
             f'{esquema}:{dominio}:{publicado}?transport=tcp')
    return secreto


# --- atomicas de web -------------------------------------------------------

# Las tres cabeceras que `configure_caddy` escribe siempre. No son un dato del
# repo: cada una tiene un solo valor sensato para un sitio HTTPS, y son
# justamente de las que uno se olvida. La cuarta —la CSP— si cambia entre
# proyectos y sale de `config.env`.
SECURITY_HEADERS = (
    ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains'),
    ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'strict-origin-when-cross-origin'),
)

def _spa_root(ctx, name: str) -> str:
    """La carpeta que Caddy sirve para esa SPA, del lado del VPS.

    Sale de la misma ruta relativa que usa la subida del build
    (`upload_to_vps`), asi que no hay una segunda convencion que mantener
    sincronizada con la primera.
    """
    spa = targets.find(ctx.root, targets.SPA_VITE, name)
    rel = spa.path.relative_to(ctx.root).as_posix()
    salida = next((c for c in ('dist', 'build') if (spa.path / c).is_dir()), 'dist')
    return vps.remote_path(ctx.config, rel, salida)


def _route_target(ctx, route: vps.Route) -> str:
    """A donde manda una regla: la direccion de un `proxy`, la carpeta del VPS de las otras dos."""
    if route.kind == 'spa':
        return _spa_root(ctx, route.target)
    return vps.resolve_target(ctx.config, route)


def _caddyfile(*, domain: str, routes: list[vps.Route], destinos: dict[str, str],
               csp: str) -> str:
    """El Caddyfile entero, en una funcion sin efectos: es lo unico que se prueba.

    Cada regla es un `handle`, en el orden en que vino: gana la primera que
    matchea, que es la semantica de Caddy y la razon por la que el orden de
    `CADDY_ROUTES` es informacion y no presentacion.
    """
    cuerpo = ['\tencode zstd gzip']

    cabeceras = [f'\t\t{nombre} "{valor}"' for nombre, valor in SECURITY_HEADERS]
    if csp:
        cabeceras.append(f'\t\tContent-Security-Policy "{csp}"')
    cuerpo.append('\theader {\n' + '\n'.join(cabeceras) + '\n\t}')

    for route in routes:
        # El catch-all es `handle` sin patron; el resto lleva el suyo.
        cabeza = 'handle' if route.catch_all else f'handle {route.pattern}'
        if route.kind == 'proxy':
            lineas = [f'\t\treverse_proxy {destinos[route.pattern]}']
        else:
            lineas = [f'\t\troot * {destinos[route.pattern]}']
            # Recortar el prefijo es lo que hace que el build no necesite una
            # carpeta `admin/` en disco: el prefijo vive solo en las URLs. El
            # catch-all no tiene prefijo que recortar, y `proxy` nunca recorta
            # —las rutas del server incluyen su `/api`—.
            if not route.catch_all:
                lineas.append(f'\t\turi strip_prefix {route.prefix}')
            if route.kind == 'spa':
                lineas.append('\t\ttry_files {path} /index.html')
            lineas.append('\t\tfile_server')
        cuerpo.append(f'\t{cabeza} {{\n' + '\n'.join(lineas) + '\n\t}')

    return f'{domain} {{\n' + '\n\n'.join(cuerpo) + '\n}\n'


CADDY_REFERENCE = 'Caddyfile.generado'


def _save_reference(ctx, conf: str) -> None:
    """Deja en el repo local una copia legible del Caddyfile que se acaba de escribir.

    El vivo es `/etc/caddy/Caddyfile` en el VPS y no hay otro: tener un Caddyfile
    en la raiz del repo termina en que alguien lo enlaza y el proxy pasa a
    depender del arbol de git. Pero mirar la configuracion del proxy sin entrar
    por SSH es razonable, asi que la copia va a `.consola/`, que esta gitignorado
    — es una referencia, no una fuente, y nadie la puede confundir con la otra.

    Se escribe local porque el build tambien se hace local y despues se copia al
    VPS: lo que Consola le deja al repo tiene que estar de este lado.
    """
    destino = ctx.root / envfile.CONSOLA_DIR / CADDY_REFERENCE
    destino.parent.mkdir(parents=True, exist_ok=True)
    encabezado = (f'# Copia de referencia. El que usa Caddy es {CADDYFILE} en el VPS.\n'
                  f'# Lo genera Consola desde CADDY_ROUTES: editar esto no cambia nada.\n\n')
    destino.write_text(encabezado + conf, encoding='utf-8', newline='\n')
    ctx.info(f'Copia de referencia: {destino}')


def configure_caddy(ctx, *, enable: bool = True, start: bool = True) -> str:
    """Escribe el Caddyfile del VPS a partir de `CADDY_ROUTES` y deja Caddy sirviendo.

    Caddy queda adelante de todo: toma el 80 y el 443, saca y renueva el
    certificado solo y reparte segun la tabla de ruteo. Esa tabla es un dato del
    despliegue —las mismas rutas existirian si el archivo se escribiera a mano—
    asi que vive en `config.env` y no en los parametros del boton. Antes se
    deducia de la forma del repo, con el nombre de cada carpeta como prefijo de
    URL, y no habia forma de decir «esta va en la raiz y esta otra en /admin».

    `start=False` escribe el Caddyfile y no lo aplica. Aca es donde mas se pide:
    reiniciar Caddy corta el 80 y el 443 de TODO el VPS por un instante, no solo
    de una app. El archivo que queda ya paso por `caddy validate`, asi que lo
    que espera a la ventana de mantenimiento es una configuracion valida.
    """
    remote = ssh.resolve_remote(ctx.config)
    vps.require_package(remote, 'caddy', 'Caddy')

    dominio = ctx.config.get('PUBLIC_HOST')
    if not dominio:
        raise TaskError('Falta PUBLIC_HOST: cargalo en Configuración, o el dominio '
                        'de Cloudflare del que se deriva.')

    rutas = vps.routes(ctx.config)
    destinos = {r.pattern: _route_target(ctx, r) for r in rutas}
    # Las carpetas de las SPA las crea la subida del build; las de `static` son
    # de quien administra el VPS y Consola no las inventa. Servir una carpeta
    # que no existe no hace fallar a Caddy: devuelve 404 y hay que ir a buscar
    # por que.
    for route in rutas:
        if route.kind == 'static' and not ssh.succeeds(remote, f'test -d {ssh.quote(destinos[route.pattern])}'):
            raise TaskError(f'{destinos[route.pattern]} no existe en el VPS, y la regla '
                            f'«{route.pattern}» lo sirve. Crealo antes de correr esto.')

    conf = _caddyfile(domain=dominio, routes=rutas, destinos=destinos,
                      csp=ctx.config.get('CSP').strip())
    _save_reference(ctx, conf)

    ssh.run(ctx, remote, f'{vps.SUDO} mkdir -p /etc/caddy')
    # Si /etc/caddy/Caddyfile es un symlink, `tee` escribe A TRAVES de el: asi se
    # perdio una vez el Caddyfile versionado dentro del clon de produccion, que
    # es a donde apuntaba. Consola es la dueña del archivo, asi que rompe el
    # enlace y escribe uno propio — pero deja en el log lo que habia del otro
    # lado, que es lo unico que quedaba de aquel.
    enlace = ssh.capture(remote, f'readlink {CADDYFILE}', check=False)
    if enlace:
        ctx.warn(f'{CADDYFILE} era un symlink a {enlace}. Consola escribe un archivo '
                 'propio; ese queda intacto y sin usar.')
        ssh.run(ctx, remote, f'{vps.SUDO} rm -f {CADDYFILE}')

    cambio = vps.write_config(ctx, remote, CADDYFILE, conf)
    # `caddy validate` antes de recargar: un Caddyfile con un error de sintaxis
    # deja el servicio caido, y con el se cae todo lo que publica el VPS. El que
    # no cambio ya paso por aca cuando se escribio.
    if cambio:
        ssh.run(ctx, remote, f'caddy validate --adapter caddyfile --config {CADDYFILE}')

    vps.open_ports(ctx, remote, ['80/tcp', '443/tcp', '443/udp'])
    from . import vps_server
    vps_server.bring_up_service(ctx, 'caddy', enable=enable, start=start, changed=cambio)

    for route in rutas:
        donde = f'https://{dominio}' + ('' if route.catch_all else route.prefix)
        ctx.ok(f'{donde} -> {route.kind} {destinos[route.pattern]}')
    return CADDYFILE


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
        ctx.step('access')
        ensure_deploy_access(ctx)
    if sudo:
        ctx.step('sudo')
        configure_sudo(ctx, sudo_mode)
    if verify:
        ctx.step('verify')
        remote = ssh.resolve_remote(ctx.config)
        if ssh.reachable(remote):
            ctx.ok(f'Login sin contrasena funcionando: {remote.target}')
        else:
            ctx.error(f'No se pudo entrar como {remote.target} con la llave.')


def setup_github_ssh(ctx, *, generate: bool = True, register: bool = True,
                     verify: bool = True) -> None:
    """Compuesta: llave del VPS -> registro en GitHub -> prueba."""
    if generate:
        ctx.step('generate')
        generate_remote_keypair(ctx)
    if register:
        ctx.step('register')
        register_github_key(ctx)
    if verify:
        ctx.step('verify')
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
    duplicar sus ejes: un parametro que el bootstrap no reenvia queda clavado
    en su default y el eje del boton suelto no sirve de nada aca — el mismo
    agujero que tenia `sudo_mode` antes de docs/atomicas.md 4.6, una capa mas
    arriba.

    El paso de codigo llama a `publish_code` y no a `update_remote`: una
    compuesta puede reusar otra solo si quiere todos sus pasos, y aca sobraban
    los dos que tocan lo que ya esta corriendo. `update_remote` traia
    `migrate=True` por default, o sea `alembic upgrade` contra una base que el
    paso siguiente todavia no creo.

    El paso de base es una sola llamada a `bootstrap_db`. Antes eran dos
    —`bootstrap_db(migrate=False)` seguido de `rebuild_db`— porque el bootstrap
    terminaba en un esquema vacio y hacia falta la destructiva para sembrarlo.
    Ahora `bootstrap_db` llega hasta los seeders, y `rebuild_db` aca solo
    agregaba un `drop_tables` sobre una base recien creada.
    """
    from . import database as db_tasks
    from . import vps_server

    if known_host:
        ctx.step('known_host')
        refresh_known_host(ctx)
    if ssh_key:
        ctx.step('ssh_key')
        setup_ssh_key(ctx.child('setup_ssh_key'), sudo_mode)
    if software:
        ctx.step('software')
        install_base_software(ctx, groups)
    if github_ssh:
        ctx.step('github_ssh')
        setup_github_ssh(ctx.child('setup_github_ssh'))
    if deploy:
        ctx.step('deploy')
        vps_server.publish_code(ctx.child('publish_code'))
    if database:
        ctx.step('database')
        db_tasks.bootstrap_db(ctx.child('bootstrap_db'), scope='remoto')
    if service:
        ctx.step('service')
        vps_server.configure_service(ctx.child('configure_service'))
    ctx.note('Bootstrap completo del VPS.')


def bind_all() -> None:
    registry.bind('refresh_known_host', refresh_known_host)
    registry.bind('setup_ssh_key', setup_ssh_key)
    registry.bind('setup_github_ssh', setup_github_ssh)
    registry.bind('install_software', install_base_software)
    registry.bind('configure_coturn', configure_coturn)
    registry.bind('configure_caddy', configure_caddy)
    registry.bind('bootstrap_vps', bootstrap_vps)
