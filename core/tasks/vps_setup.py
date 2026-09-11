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


def _require_package(remote: ssh.Remote, package: str, group: str) -> None:
    """Corta si el paquete no esta, en vez de instalarlo por su cuenta.

    Instalar es `install_base_software` y el paquete es uno de sus grupos, igual
    que `postgresql`: estos botones son el `bootstrap_db` de su servicio — la
    configuracion, no la instalacion. Que un boton de configurar corriera su
    propio `apt-get install` era la unica parte del catalogo donde la misma
    accion vivia en dos lugares (docs/atomicas.md 4.6).
    """
    if ssh.succeeds(remote, f'dpkg -s {ssh.quote(package)}'):
        return
    raise TaskError(f'{package} no esta instalado en el VPS. '
                    f'Corre "Software base" con el grupo "{group}" marcado.')


def _open_ports(ctx, remote: ssh.Remote, ports: list[str]) -> None:
    """Abre puertos en ufw si ufw manda; si no, los dice.

    Callar cuando ufw no esta activo no es "no hacer nada": el firewall puede
    estar en el panel del proveedor, y ahi los puertos siguen cerrados.
    """
    if not ssh.succeeds(remote, 'sudo -n ufw status | grep -q active'):
        ctx.warn(f'ufw no esta activo: abre {", ".join(ports)} donde corresponda.')
        return
    for puerto in ports:
        ssh.run(ctx, remote, f'sudo -n ufw allow {puerto}', check=False)
    ctx.ok(f'Puertos abiertos en ufw: {", ".join(ports)}')


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


def configure_coturn(ctx, tls: bool = False) -> str:
    """Configura el servidor TURN para llamadas detras de NAT simetrico.

    El realm y los puertos salen de `config.env` y no del panel de parametros:
    el backend tiene que anunciar en sus `turn:` URLs exactamente lo que quedo
    en /etc/turnserver.conf, asi que son datos del despliegue y no una eleccion
    de la corrida.

    Reiniciar el servicio o mirar su estado tampoco son parametros de este
    boton: son `systemd_action` y `view_logs` con el eje `service` puesto en
    coturn, que son los mismos botones que ya existian para el servicio del
    proyecto.
    """
    remote = ssh.resolve_remote(ctx.config)
    _require_package(remote, 'coturn', 'Coturn')

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
    ssh.run(ctx, remote, f'sudo -n tee /etc/turnserver.conf > /dev/null <<"TURN_CONF"\n{conf}TURN_CONF')
    ssh.run(ctx, remote, 'sudo -n sed -i "s/^#TURNSERVER_ENABLED=1/TURNSERVER_ENABLED=1/" /etc/default/coturn',
            check=False)

    puertos = [f'{port}/tcp', f'{port}/udp', f'{relay_min}:{relay_max}/udp']
    if tls:
        puertos.append(f'{TURN_TLS_PORT}/tcp')
    _open_ports(ctx, remote, puertos)

    vps.systemctl(ctx, remote, 'enable', 'coturn')
    vps.systemctl(ctx, remote, 'restart', 'coturn')
    estado = vps.service_state(remote, 'coturn')
    if estado != 'active':
        raise TaskError(f'coturn quedo en estado {estado}. Mira sus logs con Ver logs → Coturn.')

    ctx.ok(f'coturn escuchando en {remote.host}:{port} (realm {dominio}).')
    esquema = 'turns' if tls else 'turn'
    publicado = TURN_TLS_PORT if tls else port
    ctx.info(f'URLs para el backend: {esquema}:{dominio}:{publicado}?transport=udp, '
             f'{esquema}:{dominio}:{publicado}?transport=tcp')
    return secreto


# --- atomicas de web -------------------------------------------------------

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


def _spa_lines(root: str, indent: str) -> str:
    cuerpo = [f'root * {root}', 'try_files {path} /index.html', 'file_server']
    return '\n'.join(f'{indent}{linea}' for linea in cuerpo)


def _caddyfile(*, domain: str, apps: list[tuple[str, str]], upstream: str, api: str,
               routing: str) -> str:
    """El Caddyfile entero, en una funcion sin efectos: es lo unico que se prueba.

    Una sola SPA se sirve en la raiz —del dominio o del subdominio, segun el
    ruteo— porque un repo con una sola app no tiene de que distinguirla. Con dos
    o mas, cada una lleva su nombre: el mismo que ya la identifica en el eje de
    Build Vite.
    """
    if not apps and not api:
        raise TaskError('Sin apps y sin ruta de API no hay nada que servir.')

    if routing == 'subdominio':
        if not apps:
            return (f'{domain} {{\n    encode zstd gzip\n'
                    f'    reverse_proxy {upstream}\n}}\n')
        bloques = []
        if api:
            bloques.append(f'{api}.{domain} {{\n    encode zstd gzip\n'
                           f'    reverse_proxy {upstream}\n}}')
        for nombre, root in apps:
            host = domain if len(apps) == 1 else f'{nombre}.{domain}'
            bloques.append(f'{host} {{\n    encode zstd gzip\n{_spa_lines(root, "    ")}\n}}')
        return '\n\n'.join(bloques) + '\n'

    if not apps:
        return (f'{domain} {{\n    encode zstd gzip\n'
                f'    reverse_proxy {upstream}\n}}\n')

    cuerpo = ['    encode zstd gzip']
    if api:
        cuerpo.append(f'    handle /{api}/* {{\n        reverse_proxy {upstream}\n    }}')
    for nombre, root in apps:
        if len(apps) == 1:
            cuerpo.append(f'    handle {{\n{_spa_lines(root, "        ")}\n    }}')
        else:
            cuerpo.append(f'    handle_path /{nombre}/* {{\n{_spa_lines(root, "        ")}\n    }}')
    return f'{domain} {{\n' + '\n\n'.join(cuerpo) + '\n}\n'


def configure_caddy(ctx, apps: list[str] | None = None, routing: str = 'subruta') -> str:
    """Escribe el Caddyfile del VPS y deja Caddy sirviendo.

    Caddy queda adelante de todo: toma el 80 y el 443, saca y renueva el
    certificado solo y reparte entre las SPA compiladas y el backend. A donde
    manda ese trafico no es un parametro de este boton: es
    `BACKEND_HOST`/`BACKEND_PORT`, el mismo dato con el que `write_systemd_unit`
    levanta el backend — dos copias de esa direccion es la forma segura de que
    un dia Caddy apunte a donde el backend ya no escucha.

    La lista vacia de apps significa "las SPA que tenga el repo"; ninguna SPA es
    tambien valido: es el VPS que solo publica la API.
    """
    remote = ssh.resolve_remote(ctx.config)
    _require_package(remote, 'caddy', 'Caddy')

    dominio = ctx.config.get('PUBLIC_HOST')
    if not dominio:
        raise TaskError('Falta PUBLIC_HOST: cargalo en Configuración, o el dominio '
                        'de Cloudflare del que se deriva.')
    if routing not in ('subruta', 'subdominio'):
        raise TaskError(f'Ruteo desconocido: {routing}')

    elegidas = list(apps or targets.names(ctx.root, targets.SPA_VITE))
    api = ctx.config.get('API_PATH', '/api').strip('/')
    upstream = vps.backend_address(ctx.config)
    servidas = [(nombre, _spa_root(ctx, nombre)) for nombre in elegidas]

    conf = _caddyfile(domain=dominio, apps=servidas, upstream=upstream, api=api, routing=routing)
    ssh.run(ctx, remote, 'sudo -n mkdir -p /etc/caddy && '
                         f'sudo -n tee {CADDYFILE} > /dev/null <<"CADDY_CONF"\n{conf}CADDY_CONF')
    # `caddy validate` antes de recargar: un Caddyfile con un error de sintaxis
    # deja el servicio caido, y con el se cae todo lo que publica el VPS.
    ssh.run(ctx, remote, f'caddy validate --adapter caddyfile --config {CADDYFILE}')

    _open_ports(ctx, remote, ['80/tcp', '443/tcp', '443/udp'])
    vps.systemctl(ctx, remote, 'enable', 'caddy')
    vps.systemctl(ctx, remote, 'restart', 'caddy')
    estado = vps.service_state(remote, 'caddy')
    if estado != 'active':
        raise TaskError(f'Caddy quedo en estado {estado}. Mira sus logs con Ver logs → Caddy.')

    for nombre, _ in servidas:
        if routing == 'subdominio':
            destino = f'https://{dominio}' if len(servidas) == 1 else f'https://{nombre}.{dominio}'
        else:
            destino = f'https://{dominio}' if len(servidas) == 1 else f'https://{dominio}/{nombre}/'
        ctx.ok(f'{nombre}: {destino}')
    if api and servidas:
        ctx.ok(f'API: https://{api}.{dominio}' if routing == 'subdominio'
               else f'API: https://{dominio}/{api}/')
        if routing == 'subruta':
            ctx.info(f'El prefijo /{api} llega al backend tal cual: las rutas del '
                     f'servidor tienen que empezar con /{api}.')
    elif not servidas:
        ctx.ok(f'Todo el dominio va al backend: https://{dominio}')
    if routing == 'subdominio' and len(servidas) > 1:
        ctx.warn('Cada subdominio necesita su propio registro DNS en Cloudflare.')
    if routing == 'subruta' and len(servidas) > 1:
        ctx.warn('Cada SPA se sirve bajo su nombre: su vite.config necesita '
                 "base: '/<nombre>/' o los assets van a dar a la raiz.")
    # La unidad systemd se escribe una vez y no se relee sola: un VPS armado
    # antes de que existiera `BACKEND_HOST` sigue con el backend en 0.0.0.0:443,
    # y ahi Caddy no puede tomar el 443. Se mira la unidad y se avisa solo si de
    # verdad discrepa, en vez de reescribir el servicio de otro boton o repetir
    # un aviso generico cuando ya esta bien.
    servicio = vps.service_name(ctx.config)
    host, port = vps.backend_listen(ctx.config)
    if vps.unit_installed(remote, servicio):
        unidad = ssh.capture(remote, f'cat {ssh.quote(vps.unit_path(servicio))}', check=False)
        if unidad and f'--host {host} --port {port}' not in unidad:
            ctx.warn(f'La unidad de {servicio} no escucha en {upstream}, que es a donde '
                     'manda Caddy: reescribila con Instalar servicio.')
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
        vps_server.install_systemd(ctx.child('install_systemd'))
    ctx.note('Bootstrap completo del VPS.')


def bind_all() -> None:
    registry.bind('refresh_known_host', refresh_known_host)
    registry.bind('setup_ssh_key', setup_ssh_key)
    registry.bind('setup_github_ssh', setup_github_ssh)
    registry.bind('install_software', install_base_software)
    registry.bind('configure_coturn', configure_coturn)
    registry.bind('configure_caddy', configure_caddy)
    registry.bind('bootstrap_vps', bootstrap_vps)
