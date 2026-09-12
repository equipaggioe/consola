from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Setting:
    """Una clave de `.consola/config.env`, declarada una sola vez.

    Dos consumidores (PLAN.md §9): el formulario de Configuracion y la
    validacion previa que marca en ambar lo que le falta a una accion.
    """
    key: str
    group: str
    label: str = ''
    secret: bool = False
    default: str = ''
    placeholder: str = ''
    kind: str = 'text'  # 'text' | 'list'. 'list' es un campo multilinea: una
                        # entrada por renglon, guardadas separadas por comas.
    scope: str = 'repo'  # 'repo' = va a `.consola/config.env`, porque el valor
                        # es del proyecto. 'machine' = va a QSettings, porque el
                        # valor es de ESTA maquina y escribirlo en cada repo
                        # seria escribir nueve veces lo mismo
                        # (`ui/params_store.py::machine_env`).
    required_by: tuple[str, ...] = field(default_factory=tuple)
    # Acciones que USAN la clave pero corren igual sin ella. Aparece en el panel
    # de configuracion filtrado de esas acciones, y no bloquea su boton. La
    # distincion importa: `serve_backend` nunca lee `API_URL` —quien la lee es
    # `compile_apk`, y ese ya la pide por paso— asi que exigirla dejaba el
    # Backend en ambar por una clave que jamas iba a mirar (docs/launchers.md 3).
    used_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def display(self) -> str:
        return self.label or self.key


# Claves VPS que necesita cualquier operacion que alcance el servidor.
_VPS_REACH = ('ssh_login', 'health_check', 'run_command', 'run_setup_scripts',
              'update_remote', 'upload_to_vps', 'install_software', 'setup_ssh_key',
              'setup_github_ssh', 'configure_coturn', 'configure_caddy',
              'bootstrap_vps', 'view_logs',
              'systemd_action', 'configure_service', 'clean_vps', 'revoke_ssh')

_DB_REMOTE = ('bootstrap_db', 'teardown_db', 'migrate_db', 'rebuild_db',
              'reinit_migrations', 'backup_db', 'ssh_tunnel', 'inspect_db')

SETTINGS: tuple[Setting, ...] = (
    # --- Server ---
    # No la exige nadie: el build del APK la pide por paso (`BUILD_APK_STEPS`) y
    # `run_mobile` cae en la URL del backend de esta sesion si esta vacia.
    Setting('API_URL', 'Server', 'URL publica de la API',
            placeholder='https://ejemplo.net:443',
            used_by=('backend', 'run_mobile', 'build_apk')),

    # --- Cloudflare ---
    Setting('CF_API_TOKEN', 'Cloudflare', 'API token', secret=True,
            required_by=('update_cloudflare',)),
    Setting('CF_DOMAIN_NAME', 'Cloudflare', 'Dominio',
            required_by=('update_cloudflare',)),
    Setting('CF_RECORD_NAME', 'Cloudflare', 'Registro DNS',
            required_by=('update_cloudflare',)),

    # --- VPS ---
    Setting('VPS_IP', 'VPS', 'IP del servidor', required_by=_VPS_REACH),
    Setting('ROOT_USER', 'VPS', 'Usuario root', default='root',
            required_by=('setup_ssh_key', 'install_software', 'bootstrap_vps')),
    Setting('VPS_USER', 'VPS', 'Usuario de despliegue', required_by=_VPS_REACH),
    Setting('VPS_KEY_NAME', 'VPS', 'Nombre de la llave SSH', required_by=_VPS_REACH),
    Setting('VPS_PYTHON', 'VPS', 'Python del VPS', default='server/.venv/bin/python',
            required_by=('update_remote', 'configure_service')),
    Setting('VPS_DEPLOY_DIR', 'VPS', 'Directorio de despliegue',
            required_by=('update_remote', 'upload_to_vps')),
    # El nombre con el que se llega al VPS desde afuera: el realm de coturn y la
    # direccion del sitio de Caddy son el mismo dato, no dos. Su default sale de
    # lo que ya esta cargado —el registro DNS de Cloudflare, si no el dominio, si
    # no la IP— y el panel lo muestra resuelto, igual que el usuario de
    # despliegue muestra el nombre del repo.
    Setting('PUBLIC_HOST', 'VPS', 'Nombre publico del VPS',
            used_by=('configure_coturn', 'configure_caddy')),
    # Los archivos que nunca viajan por git. Era un eje repetido en los cuatro
    # botones del deploy, con su propio valor guardado en cada uno: cambiar la
    # lista obligaba a escribirla cuatro veces y nada avisaba cuando dos
    # discrepaban. Que archivos secretos tiene un repo no es una decision de
    # quien aprieta el boton, es una propiedad del proyecto — o sea,
    # configuracion.
    #
    # `kind='list'` la dibuja multilinea, una ruta por renglon. En el archivo va
    # separada por comas, que es lo unico que entra en un renglon de .env;
    # `envfile.split_list` acepta las dos formas al leerla.
    Setting('SECRET_FILES', 'VPS', 'Archivos a copiar', kind='list',
            placeholder='server/.env, server/certs/cert.pem, server/certs/key.pem',
            used_by=('publish_code', 'update_remote', 'upload_secret_files',
                     'bootstrap_vps')),
    Setting('DB_NAME', 'VPS', 'Base de datos', required_by=_DB_REMOTE),
    Setting('DB_PASSWORD', 'VPS', 'Password de la base', secret=True, required_by=_DB_REMOTE),
    # El secreto con el que el backend firma las credenciales efimeras de TURN.
    # No lo escribe una persona: `configure_coturn` lo genera la primera vez y
    # lo deja aca. Esta declarado igual porque el backend tiene que leer EL
    # MISMO valor que quedo en /etc/turnserver.conf, y sin una casa el boton lo
    # regeneraba en cada corrida — cada reconfiguracion tiraba abajo las
    # llamadas sin decir por que. `used_by` y no `required_by`: vacio significa
    # "todavia no se genero", no "falta un dato".
    Setting('TURN_SECRET', 'VPS', 'Secreto TURN', secret=True,
            placeholder='se genera solo al configurar coturn',
            used_by=('configure_coturn',)),
    # Los puertos del TURN son datos y no parametros por la misma razon que el
    # secreto: el backend tiene que anunciar en sus `turn:` URLs exactamente los
    # que quedaron en /etc/turnserver.conf. El rango de relay va en una sola
    # clave porque es un solo dato —coturn pide un puerto por sesion de medios
    # viva— y partirlo en dos claves permitiria guardarlas cruzadas.
    Setting('TURN_PORT', 'VPS', 'Puerto TURN', default='3478',
            used_by=('configure_coturn',)),
    Setting('TURN_RELAY_RANGE', 'VPS', 'Rango de relay', default='49160-49360',
            used_by=('configure_coturn',)),
    Setting('PG_SUPERUSER', 'VPS', 'Superusuario Postgres', default='postgres',
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),
    Setting('PG_PASSWORD', 'VPS', 'Password del superusuario', secret=True,
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),
    # Configuracion y no parametro de la corrida: que extensiones necesita el
    # esquema es una propiedad del proyecto, igual que `SECRET_FILES`. No sale
    # de ningun catalogo de Postgres —`pg_available_extensions` dice lo que se
    # PUEDE crear (cientos con contrib) y `pg_extension` lo que YA esta creado—
    # ni de las migraciones, que con `--autogenerate` nunca escriben un
    # `CREATE EXTENSION`. Se declara.
    #
    # El default es `postgis` porque es el unico grupo de `vps.PACKAGE_GROUPS`
    # que es una extension y no un servicio: instalar el paquete la deja
    # disponible, y crearla en la base es este paso aparte. Si el paquete no
    # esta, `enable_extensions` avisa y sigue en vez de romper el bootstrap.
    Setting('DB_EXTENSIONS', 'VPS', 'Extensiones de Postgres', kind='list',
            default='postgis', placeholder='postgis, pg_trgm, unaccent',
            used_by=('bootstrap_db', 'enable_extensions', 'bootstrap_vps')),

    # --- Web ---
    # La tabla de ruteo del reverse proxy: un renglon por regla, en orden, gana
    # la primera que matchea. Es la misma forma que tienen por dentro los
    # `handle` de Caddy, los `rewrites` de Vercel y los `paths` de un Ingress, y
    # esta aca —y no en `params.json`— porque es estructura del despliegue: esas
    # rutas serian las mismas si el Caddyfile se escribiera a mano.
    #
    # `<patron> <destino>`, con tres destinos posibles:
    #   backend            -> al `BACKEND_HOST:BACKEND_PORT` del repo
    #   spa <nombre>       -> el build de esa SPA (recorta el prefijo)
    #   static <ruta>      -> una carpeta del VPS (recorta el prefijo); `$CLAVE`
    #                         al empezar se resuelve contra esta configuracion
    # El patron `*` es el catch-all y va ultimo. Sin comas en ningun valor: son
    # el separador con el que se guarda la lista.
    Setting('CADDY_ROUTES', 'Web', 'Rutas del proxy', kind='list',
            placeholder='/api/* backend\n/admin/* spa backoffice\n* spa pwa',
            required_by=('configure_caddy',)),
    # La unica cabecera de seguridad que cambia entre proyectos. Las otras tres
    # —HSTS, nosniff, Referrer-Policy— tienen un solo valor sensato y las escribe
    # `configure_caddy` sin preguntar: son de las que se olvidan, no de las que
    # se eligen. Vacia significa no emitir CSP, que es lo que corresponde
    # mientras el sitio todavia no la tenga pensada.
    Setting('CSP', 'Web', 'Content-Security-Policy',
            placeholder="default-src 'self'", used_by=('configure_caddy',)),
    # La raiz de los archivos que sube la gente. No viaja por git y no la crea
    # Consola: existe antes, con el dueno y los permisos que decida quien
    # administra el VPS. Aca solo se nombra, para que una regla `static` pueda
    # apuntarle con `$STORAGE_ROOT/...`.
    Setting('STORAGE_ROOT', 'Web', 'Raiz de archivos subidos',
            placeholder='/srv/almacenamiento', used_by=('configure_caddy',)),

    # --- GitHub ---
    Setting('GIT_REPO_URL', 'GitHub', 'URL del repositorio',
            placeholder='git@github.com:usuario/repo.git',
            required_by=('update_remote', 'setup_github_ssh', 'bootstrap_vps')),
    Setting('GITHUB_TOKEN', 'GitHub', 'Token', secret=True,
            required_by=('setup_github_ssh', 'revoke_github_ssh')),
    Setting('GITHUB_KEY_TITLE', 'GitHub', 'Titulo de la llave',
            required_by=('setup_github_ssh', 'revoke_github_ssh')),

    # --- Systemd ---
    Setting('SERVER_DIR', 'Systemd', 'Carpeta del server', default='server',
            required_by=('configure_service',)),
    # Donde escucha el backend DENTRO del VPS. Lo escribe `write_systemd_unit` y
    # lo lee `configure_caddy` para saber a donde mandan las reglas `backend`:
    # es un dato de a dos, y tenerlo en cada boton por separado seria dejar que
    # un lado quede apuntando a donde el otro ya no escucha.
    #
    # El default es loopback y no 0.0.0.0:443 —lo que estaba clavado en la
    # funcion— porque Caddy viene en `DEFAULT_GROUPS`: el backend de este
    # catalogo corre detras de Caddy, y ahi el 443 lo toma Caddy.
    Setting('BACKEND_HOST', 'Systemd', 'Escucha del backend', default='127.0.0.1',
            used_by=('configure_service', 'configure_caddy')),
    Setting('BACKEND_PORT', 'Systemd', 'Puerto del backend', default='8000',
            used_by=('configure_service', 'configure_caddy')),
    Setting('CERT_FILE_PATH', 'Systemd', 'Certificado', default='server/certs/cert.pem',
            required_by=('configure_service', 'backend')),
    Setting('KEY_FILE_PATH', 'Systemd', 'Llave privada', default='server/certs/key.pem',
            required_by=('configure_service', 'backend')),
    Setting('UVICORN_APP', 'Systemd', 'Entrypoint uvicorn', default='app.main:app',
            required_by=('configure_service', 'backend')),

    # --- Maquina ---
    # El `PYINSTALLER_BIN` del script original, y por el mismo motivo: `pip
    # install pyinstaller` deja el ejecutable en el Scripts del usuario, que en
    # Windows no siempre esta en el PATH. No bloquea el boton — vacio, se busca
    # primero en el venv de la app y despues en el PATH.
    #
    # `scope='machine'`: donde quedo instalado un ejecutable es de la maquina,
    # no del proyecto. En `config.env` habia que escribir la misma ruta en cada
    # repo, y nueve copias de un dato son ocho oportunidades de que discrepen.
    Setting('PYINSTALLER_BIN', 'Máquina', 'Ruta de PyInstaller', scope='machine',
            placeholder='se busca en el venv de la app y en el PATH',
            used_by=('build_binary',)),
)

GROUP_ORDER = ('Server', 'Cloudflare', 'VPS', 'Web', 'GitHub', 'Systemd', 'Máquina')

# Los seguros del repo (`PROTECT_*`) NO estan aca y no son un `Setting`: no son
# un dato que una tarea consuma —ningun paso lee uno— sino una decision de la
# consola sobre este repo, y viven con las demas en `.consola/params.json`
# (`ui/security_panel.py`, `ui/params_store.py::load_protection`).


def repo_settings() -> tuple[Setting, ...]:
    """Las que se escriben en `.consola/config.env`. Es lo que regenera el
    archivo (`core/envfile.py`): una clave de maquina ahi seria un dato del
    proyecto que no es del proyecto."""
    return tuple(s for s in SETTINGS if s.scope == 'repo')


def machine_settings() -> tuple[Setting, ...]:
    return tuple(s for s in SETTINGS if s.scope == 'machine')


def settings_by_group() -> dict[str, list[Setting]]:
    groups: dict[str, list[Setting]] = {g: [] for g in GROUP_ORDER}
    for s in SETTINGS:
        groups.setdefault(s.group, []).append(s)
    return {g: items for g, items in groups.items() if items}


def get_setting(key: str) -> Setting | None:
    for s in SETTINGS:
        if s.key == key:
            return s
    return None


def required_keys_for(capability_id: str) -> list[str]:
    """Sin estas, la accion no puede correr: su boton queda en ambar."""
    return [s.key for s in SETTINGS if capability_id in s.required_by]


def relevant_keys_for(capability_id: str) -> list[str]:
    """Las que la accion puede llegar a mirar, obligatorias o no.

    Es lo que filtra el panel de configuracion: que `API_URL` no bloquee al
    Backend no quiere decir que no sea el lugar donde uno la busca cuando
    tiene esa pestana abierta.
    """
    return [s.key for s in SETTINGS
            if capability_id in s.required_by or capability_id in s.used_by]
