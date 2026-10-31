from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Setting:
    """Una clave de `.consola/config.env`, declarada una sola vez.

    Dos consumidores (ADR-0017): el formulario de Configuracion y la
    validacion previa que marca en ambar lo que le falta a una accion.
    """
    key: str
    group: str
    label: str = ''
    secret: bool = False
    default: str = ''
    default_hint: str = ''  # El default, escrito a mano, para cuando no hay un
                        # `default` que poner: lo que pasa con el campo vacio no
                        # es un valor que se guarde, sino donde lo deja otro (la
                        # carpeta de build de cada framework). Se muestra de
                        # marca de agua igual que un default resuelto, asi que
                        # solo entra aca lo que de verdad se va a usar: una
                        # explicacion de que va en el campo se leeria como un
                        # valor ya cargado.
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
    # `compile_flutter`, y ese ya la pide por paso— asi que exigirla dejaba el
    # Backend en ambar por una clave que jamas iba a mirar (docs/arquitectura/13_configuracion_y_persistencia.md).
    used_by: tuple[str, ...] = field(default_factory=tuple)

    @property
    def display(self) -> str:
        return self.label or self.key


# Claves VPS que necesita cualquier operacion que alcance el servidor.
_VPS_REACH = ('ssh_login', 'health_check', 'run_command',
              'upload_to_vps', 'install_software', 'setup_ssh_key', 'view_logs',
              'systemd_action', 'clean_vps', 'revoke_ssh')

# Solo las de base sin eje `scope`: las que lo tienen declaran sus claves en el
# eje (`core/catalog.py::_SCOPE_AXIS`), porque dependen del ambito elegido. El
# tunel va siempre al VPS; las otras cuatro, siempre a la base local (ADR-0060).
_DB_FIXED = ('ssh_tunnel', 'bootstrap_db', 'migrate_db', 'backup_db', 'restore_db')

SETTINGS: tuple[Setting, ...] = (
    # --- Server ---
    # La exige el build de Flutter, que la compila adentro de la app. `run_mobile`
    # cae en la URL del backend de esta sesion si esta vacia.
    Setting('API_URL', 'Server', 'URL publica de la API', required_by=('build_flutter',),
            used_by=('backend', 'run_mobile')),

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
            required_by=('setup_ssh_key', 'install_software')),
    Setting('VPS_USER', 'VPS', 'Usuario de despliegue',
            required_by=_VPS_REACH),
    Setting('VPS_KEY_NAME', 'VPS', 'Nombre de la llave SSH', required_by=_VPS_REACH),
    # Los dos los lee el ambito remoto de la base (`core/runner.py`), que corre
    # el Python del repo desplegado.
    Setting('VPS_PYTHON', 'VPS', 'Python del VPS', default='server/.venv/bin/python',
            used_by=('rebuild_db', 'run_seeders', 'run_mock_seeders')),
    Setting('VPS_DEPLOY_DIR', 'VPS', 'Directorio de despliegue',
            required_by=('upload_to_vps',)),
    # Vacio, el rol es el mismo usuario de despliegue (`Config._dynamic_default`).
    Setting('DB_USER', 'VPS', 'Rol de la base', required_by=_DB_FIXED),
    Setting('DB_NAME', 'VPS', 'Base de datos', required_by=_DB_FIXED),
    Setting('DB_PASSWORD', 'VPS', 'Password de la base', secret=True, required_by=_DB_FIXED),
    # Donde caen los volcados de `backup_db` y de donde los lee `restore_db`.
    # Relativa se resuelve contra la raiz del repo; absoluta se usa tal cual, que
    # es lo que permite sacarlos de adentro del repo — `.backups/` no esta en
    # ningun `.gitignore` por defecto, y un volcado con datos reales queda listo
    # para comitearse sin que nadie avise.
    #
    # `used_by` y no `required_by`: las dos tienen `default`, y una clave con
    # default nunca cuenta como faltante (`Config.get`), asi que exigirlas no
    # dejaria ningun boton en ambar. Lo que hace `used_by` es que aparezcan en el
    # panel de configuracion filtrado de estos dos botones.
    Setting('BACKUP_DIR', 'VPS', 'Carpeta de respaldos', default='.backups',
            used_by=('backup_db', 'restore_db')),
    # Cuantos volcados sobreviven a la rotacion. Es configuracion y no un eje por
    # el mismo criterio que `DB_EXTENSIONS`: es un dato que la tarea lee, no una
    # decision de la corrida. Cuantos respaldos conserva un proyecto no cambia
    # entre dos veces que se aprieta el boton.
    Setting('BACKUP_KEEP', 'VPS', 'Respaldos a conservar', default='7',
            used_by=('backup_db',)),
    Setting('PG_SUPERUSER', 'VPS', 'Superusuario Postgres', default='postgres',
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),
    Setting('PG_PASSWORD', 'VPS', 'Password del superusuario', secret=True,
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),
    # Configuracion y no parametro de la corrida: que extensiones necesita el
    # esquema es una propiedad del proyecto. No sale
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
            default='postgis',
            used_by=('bootstrap_db', 'enable_extensions')),

    # --- Web ---
    # Bajo que ruta se publica cada cosa: un renglon por regla, en orden, gana la
    # primera que matchea. La lee el build para saber con que `base` compilar
    # cada SPA (`vps.spa_base`).
    #
    # `<patron> <tipo> <destino>`, siempre los tres: `proxy <host:puerto>`,
    # `spa <carpeta>` o `static <ruta>`. El patron `*` es el catch-all y va
    # ultimo. Sin comas en ningun valor: son el separador con el que se guarda
    # la lista.
    Setting('PUBLIC_ROUTES', 'Web', 'Rutas publicas', kind='list',
            used_by=('build_vite', 'build_flutter')),

    # --- GitHub ---
    # De ahi sale el nombre del repo en el VPS (`vps.repo_name`), que nombra sus
    # unidades systemd.
    Setting('GIT_REPO_URL', 'GitHub', 'URL del repositorio',
            used_by=('systemd_action', 'view_logs', 'health_check')),
    # Las pide la casilla «Revocar llave de GitHub» de `clean_vps`.
    Setting('GITHUB_TOKEN', 'GitHub', 'Token', secret=True, used_by=('clean_vps',)),
    Setting('GITHUB_KEY_TITLE', 'GitHub', 'Titulo de la llave', used_by=('clean_vps',)),

    # --- Systemd ---
    Setting('SERVER_DIR', 'Systemd', 'Carpeta del server', default='server',
            used_by=('sync_server_env',)),
    # `SERVICES` da los valores del eje `service` (`vps.managed_services`): una
    # tabla «<sufijo> <tipo> <destino>», y cada unidad se llama
    # `<repo>-<sufijo>`. Vacia, hay un solo servicio, llamado como el repo, que
    # corre `UVICORN_APP`.
    Setting('UVICORN_APP', 'Systemd', 'Entrypoint uvicorn', default='app.main:app',
            used_by=('systemd_action', 'view_logs')),
    Setting('SERVICES', 'Systemd', 'Servicios del repo', kind='list',
            used_by=('systemd_action', 'view_logs')),

    # --- Builds ---
    # Donde queda cada build de `build_flutter`, relativo a la carpeta de la app.
    # Vacia, donde lo deja el framework: la marca de agua dice cual es. Con valor,
    # el build se copia ahi. Sin `used_by`: las reclama la casilla de cada
    # plataforma (`AxisDef.uses_env` del catalogo), y solo se muestran las de
    # las plataformas marcadas.
    *(Setting(f'BUILD_OUT_{clave}', 'Builds', f'Carpeta del build {nombre}',
              default_hint=defecto)
      for clave, nombre, defecto in (
          ('APK', 'APK', 'build/app/outputs/flutter-apk · en Flet: build/apk'),
          ('AAB', 'AAB', 'build/app/outputs/bundle/release · en Flet: build/aab'),
          ('WEB', 'web', 'build/web'),
          ('WINDOWS', 'Windows', 'build/windows/x64/runner/Release · en Flet: build/windows'),
          ('LINUX', 'Linux', 'build/linux/x64/release/bundle · en Flet: build/linux'),
          ('MACOS', 'macOS', 'build/macos/Build/Products/Release · en Flet: build/macos'),
          ('IPA', 'iOS', 'build/ios/ipa · en Flet: build/ipa'),
      )),

    # --- Marca ---
    # El logo es del repo y Consola lo rasteriza para cada app y para el
    # ejecutable. Sin default: un repo sin logo no tiene iconos que generar.
    # Por convencion los tres SVG viven en `brand/` (ADR-0056).
    Setting('BRAND_ICON', 'Marca', 'Logo (SVG)', required_by=('generate_icons',),
            used_by=('build_binary',)),
    # La capa de adelante del icono adaptativo de Android: el mismo logo, con el
    # margen que exige el recorte del sistema. Solo la pide la app Flutter cuyo
    # pubspec declara `adaptive_icon_foreground`, y ahi falta es error.
    Setting('BRAND_ICON_FOREGROUND', 'Marca', 'Capa frontal Android (SVG)',
            used_by=('generate_icons',)),
    # El icono maskable de una PWA: fondo a sangre y el logo dentro del circulo
    # central del 80 %, que es lo que Android no recorta. Solo lo pide la SPA
    # cuyo manifest declara un icono `maskable`.
    Setting('BRAND_ICON_MASKABLE', 'Marca', 'Ícono maskable de PWA (SVG)',
            used_by=('generate_icons',)),

    # --- Capturas ---
    # La camara es un script del repo (Playwright, `flutter drive`): Consola lo
    # corre y no pregunta que hace por dentro. Sin default: ningun repo tiene
    # camara hasta que la escribe.
    Setting('SHOTS_CMD', 'Capturas', 'Comando para capturas',
            required_by=('shoot_screens',)),
    Setting('SHOTS_RAW', 'Capturas', 'Carpeta de capturas crudas', default='demo/capturas',
            used_by=('shoot_screens', 'render_shots', 'screenshots')),
    Setting('SHOTS_PUBLISH', 'Capturas', 'Carpeta de la landing',
            default='landing/static/capturas',
            used_by=('render_shots', 'screenshots')),
    # Todo destino que no es la landing (tiendas, manual, redes, press kit): una
    # carpeta por destino, con su manifiesto. Son entregables, no del sitio.
    Setting('SHOTS_DIST', 'Capturas', 'Carpeta de los demás destinos',
            default='demo/publicables',
            used_by=('render_shots', 'screenshots')),

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
            used_by=('build_binary',)),
)

GROUP_ORDER = ('Server', 'Cloudflare', 'VPS', 'Web', 'GitHub', 'Systemd', 'Builds', 'Marca', 'Capturas', 'Máquina')

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
