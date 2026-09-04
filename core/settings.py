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
    kind: str = 'text'  # 'text' | 'bool'. Un booleano se dibuja como
                        # interruptor y no como campo (`ui/env_panel.py`):
                        # escribir '1' a mano en una casilla de seguridad es
                        # pedir que se escriba mal.
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
              'setup_github_ssh', 'install_coturn', 'bootstrap_vps', 'view_logs',
              'systemd_action', 'install_systemd', 'clean_vps', 'revoke_ssh')

_DB_REMOTE = ('bootstrap_db', 'teardown_db', 'migrate_db', 'rebuild_db',
              'backup_db', 'ssh_tunnel', 'inspect_db')

def _protection_settings() -> tuple[Setting, ...]:
    """Un interruptor por tipo de objetivo (`core/protection.py`).

    Se derivan de ahi en vez de escribirse a mano para que anadir un objetivo
    nuevo sea una sola linea: la clave, su default y que acciones lo tocan
    salen todos de la misma tabla.

    `used_by` y nunca `required_by`: el seguro decide COMO se corre la accion,
    no si puede correr. Puesto en `required_by` dejaria el boton en ambar por
    una clave de seguridad, que es justo al reves de lo que se quiere.
    """
    from .protection import TARGETS, RULES

    salida = []
    for target in TARGETS:
        tocan = tuple(sorted(cap_id for cap_id, rule in RULES.items()
                             if target.id in rule.always
                             or any(target.id in extra
                                    for mapa in rule.when.values()
                                    for extra in mapa.values())))
        salida.append(Setting(
            target.key, 'Seguridad', target.setting_label, kind='bool',
            default='1' if target.protected_by_default else '0',
            placeholder=target.why,
            used_by=tocan,
        ))
    return tuple(salida)


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
            required_by=('update_remote', 'install_systemd')),
    Setting('VPS_DEPLOY_DIR', 'VPS', 'Directorio de despliegue',
            required_by=('update_remote', 'upload_to_vps')),
    Setting('DB_NAME', 'VPS', 'Base de datos', required_by=_DB_REMOTE),
    Setting('DB_PASSWORD', 'VPS', 'Password de la base', secret=True, required_by=_DB_REMOTE),
    Setting('PG_SUPERUSER', 'VPS', 'Superusuario Postgres', default='postgres',
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),
    Setting('PG_PASSWORD', 'VPS', 'Password del superusuario', secret=True,
            required_by=('bootstrap_db', 'teardown_db', 'rebuild_db')),

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
            required_by=('install_systemd',)),
    Setting('CERT_FILE_PATH', 'Systemd', 'Certificado', default='server/certs/cert.pem',
            required_by=('install_systemd', 'backend')),
    Setting('KEY_FILE_PATH', 'Systemd', 'Llave privada', default='server/certs/key.pem',
            required_by=('install_systemd', 'backend')),
    Setting('UVICORN_APP', 'Systemd', 'Entrypoint uvicorn', default='app.main:app',
            required_by=('install_systemd', 'backend')),

    # --- Builders ---
    # El `PYINSTALLER_BIN` del script original, y por el mismo motivo: `pip
    # install pyinstaller` deja el ejecutable en el Scripts del usuario, que en
    # Windows no siempre esta en el PATH. No bloquea el boton — vacio, se busca
    # primero en el venv de la app y despues en el PATH.
    Setting('PYINSTALLER_BIN', 'Builders', 'Ruta de PyInstaller',
            placeholder='se busca en el venv de la app y en el PATH',
            used_by=('build_binary',)),
) + _protection_settings()

GROUP_ORDER = ('Seguridad', 'Server', 'Cloudflare', 'VPS', 'GitHub', 'Systemd', 'Builders')


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
