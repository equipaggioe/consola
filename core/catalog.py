from __future__ import annotations
from .registry import registry, Capability, AxisDef, Step

_VPS_KEYS = {'VPS_IP', 'VPS_USER', 'VPS_KEY_NAME', 'VPS_DEPLOY_DIR'}

# Etiquetas visibles de los ejes de 'clean_artifacts'; `ui/task_adapters.py`
# las traduce de vuelta a las claves que entiende `core/tasks/utils.py`.
FAMILY_AXIS_VALUES = ['Python', 'Gradle/Android', 'Flutter', 'Volcados de crash']
HEAVY_AXIS_VALUES = ['node_modules', '.venv', 'build/dist', '.dart_tool']

# El paso nucleo va en su orden real, entre el bump y la subida.
BUILD_APK_STEPS = [
    Step('bump_version', 'Bump versión'),
    Step('apk_build', 'Compilar APK', optional=False),
    Step('upload_to_vps', 'Subir al VPS', default=False, requires_env=_VPS_KEYS),
]

BUILD_VITE_STEPS = [
    Step('bump_version', 'Bump versión'),
    Step('vite_build', 'Build Vite', optional=False),
    Step('upload_to_vps', 'Subir al VPS', default=False, requires_env=_VPS_KEYS),
]

BUILD_BINARY_STEPS = [
    Step('bump_version', 'Bump versión'),
    Step('binary_build', 'Compilar binario', optional=False),
    Step('upload_to_vps', 'Subir al VPS', default=False, requires_env=_VPS_KEYS),
]


def load_catalog() -> None:
    """Declara la forma de cada boton.

    `description` es la linea que la UI muestra en el tooltip del rail y bajo el
    nombre de la accion: que hace, en presente y en una oracion. `level` solo se
    escribe cuando no se deduce solo: una compuesta que no publica sus pasos
    (`bootstrap_db`, `start_emulator`) tiene que declararse `level='C'` a mano,
    porque sin `steps` ni `composed_of` la UI la tomaria por atomica.
    """
    # Launchers group
    registry.register(Capability(id='backend', name='Backend', group='Launchers', section='Servidor', kind='live', icon='▶', description='Levanta el servidor FastAPI del repo, local o contra el VPS.', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='serve_vite', name='Servir SPA Vite', group='Launchers', section='Frontend', kind='live', icon='🌐', description='Arranca el dev server de Vite para las apps elegidas.', axes=[AxisDef('target', ['panel', 'backoffice', 'landing'], 'checks', select='many', label='Apps')], stub=True))
    registry.register(Capability(id='run_mobile', name='App móvil', group='Launchers', section='Móvil', kind='live', icon='📲', description='Corre la app móvil en el emulador o dispositivo conectado.', axes=[AxisDef('framework', ['Flutter', 'Flet'], 'checks', select='many', label='Frameworks')], stub=True))
    registry.register(Capability(id='terminal', name='Terminal', group='Launchers', section='Dev', kind='live', icon='⌨️', description='Abre una terminal ya parada en la raíz del repo activo.', stub=True))

    # Builders group
    registry.register(Capability(id='build_apk', name='Build APK', group='Builders', section='Build APK', kind='once', icon='📦', description='Sube la versión, compila el APK y opcionalmente lo publica en el VPS.', axes=[AxisDef('bump_mode', ['patch', 'minor', 'major'], 'field', label='Bump')], steps=BUILD_APK_STEPS, stub=True))
    registry.register(Capability(id='build_vite', name='Build Vite', group='Builders', section='Build Vite', kind='once', icon='🏗️', description='Sube la versión, compila las SPA elegidas y opcionalmente las publica.', axes=[AxisDef('target', ['panel', 'backoffice', 'landing'], 'checks', select='many', label='Apps'), AxisDef('bump_mode', ['patch', 'minor', 'major'], 'field', label='Bump')], steps=BUILD_VITE_STEPS, stub=True))
    registry.register(Capability(id='build_binary', name='Build binario', group='Builders', section='Build binario', kind='once', icon='⚡', description='Sube la versión, compila el ejecutable y opcionalmente lo publica.', steps=BUILD_BINARY_STEPS, stub=True))
    registry.register(Capability(id='promote_app', name='Promote app', group='Builders', section='Promote', kind='destructive', icon='⬆️', description='Promueve el último artefacto subido al canal de producción.', stub=True))

    # Emulators group
    registry.register(Capability(id='start_emulator', name='Arrancar emulador', group='Emulators', section='Emulador', kind='live', icon='📲', description='Instala la imagen, crea el AVD si falta y arranca el emulador.', level='C', axes=[AxisDef('preset', ['pixel_4', 'pixel_8', 'resizable'], 'checks', select='many', label='Perfiles')], stub=True))
    registry.register(Capability(id='avd_manager', name='Gestor de AVD', group='Emulators', section='Gestión', kind='view', icon='🔧', description='Lista los AVD y las imágenes de sistema instaladas, sin tocar nada.', stub=True))
    registry.register(Capability(id='purge_avds', name='Purgar AVDs', group='Emulators', section='Limpieza', kind='destructive', icon='🗑️', description='Borra los AVD creados para liberar disco.', level='C', stub=True))
    registry.register(Capability(id='purge_images', name='Purgar imágenes', group='Emulators', section='Limpieza', kind='destructive', icon='🗑️', description='Borra las imágenes de sistema descargadas del SDK.', level='C', stub=True))

    # VPS · ops group
    registry.register(Capability(id='ssh_login', name='Sesión SSH', group='VPS · ops', section='Conexión', kind='interactive', icon='🔑', description='Abre una sesión SSH interactiva contra el VPS del repo.', stub=True))
    registry.register(Capability(id='health_check', name='Health check', group='VPS · ops', section='Diagnóstico', kind='once', icon='❤️', description='Comprueba que el VPS responde y el servicio está arriba.', stub=True))
    registry.register(Capability(id='run_command', name='Comando remoto', group='VPS · ops', section='Diagnóstico', kind='once', icon='💻', description='Corre un comando suelto en el VPS y trae su salida.', stub=True))
    registry.register(Capability(id='run_setup_scripts', name='Correr setup remoto', group='VPS · ops', section='Setup', kind='once', icon='📜', description='Ejecuta los scripts de setup del repo, en la máquina local o en el VPS.', composed_of=['run_remote_script'], axes=[AxisDef('where', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='revoke_ssh', name='Revocar SSH', group='VPS · ops', section='Seguridad', kind='destructive', icon='🔓', description='Quita del VPS la clave pública con la que entra esta máquina.', stub=True))
    registry.register(Capability(id='revoke_github_ssh', name='Revocar GitHub SSH', group='VPS · ops', section='Seguridad', kind='destructive', icon='🔓', description='Borra la deploy key del VPS y la da de baja en GitHub.', composed_of=['remove_remote_ssh_key_files', 'revoke_github_key'], stub=True))
    registry.register(Capability(id='clean_vps', name='Limpiar VPS', group='VPS · ops', section='Limpieza', kind='destructive', icon='💣', description='Deja el VPS como estaba: servicio, base, repo, claves, paquetes y usuario.', composed_of=['remove_systemd_service', 'drop_database', 'remove_deployed_repo', 'revoke_github_key', 'uninstall_packages', 'remove_vps_user'], stub=True))

    # VPS · server group
    registry.register(Capability(id='systemd_action', name='Acción systemd', group='VPS · server', section='Servicio', kind='once', icon='⚙️', description='Manda una acción al servicio systemd del repo en el VPS.', axes=[AxisDef('action', ['start', 'stop', 'restart', 'status'], 'buttons', danger={'stop'}), AxisDef('action_ext', ['enable', 'disable', 'reload', 'is-active', 'is-enabled'], 'menu')], stub=True))
    registry.register(Capability(id='view_logs', name='Ver logs', group='VPS · server', section='Logs', kind='live', icon='📋', description='Muestra el journal del servicio, de una o siguiéndolo en vivo.', axes=[AxisDef('follow', ['sí', 'no'], 'field')], stub=True))
    registry.register(Capability(id='install_systemd', name='Instalar servicio', group='VPS · server', section='Servicio', kind='once', icon='📥', description='Escribe la unidad systemd del repo y la deja corriendo.', composed_of=['write_systemd_unit', 'systemd_action'], stub=True))
    registry.register(Capability(id='update_remote', name='Actualizar remoto', group='VPS · server', section='Deploy', kind='live', icon='🔄', description='Despliega: trae el código, actualiza venv y deps, sube secretos y reinicia.', composed_of=['git_sync_remote', 'ensure_remote_venv', 'install_remote_deps', 'upload_files', 'generate_migration', 'restart_service'], stub=True))

    # VPS · setup group
    registry.register(Capability(id='install_software', name='Software base', group='VPS · setup', section='Paquetes', kind='once', icon='📦', description='Instala en el VPS los paquetes base que el despliegue da por dados.', stub=True))
    registry.register(Capability(id='refresh_known_host', name='Refrescar known_host', group='VPS · setup', section='SSH', kind='once', icon='🔄', description='Renueva la huella del VPS en known_hosts tras recrear la máquina.', stub=True))
    registry.register(Capability(id='setup_ssh_key', name='Configurar SSH', group='VPS · setup', section='SSH', kind='once', icon='🔑', description='Crea el usuario remoto con sudo e instala la clave con la que se entra.', composed_of=['ensure_remote_user', 'configure_sudo', 'ensure_keypair', 'install_pubkey', 'test_ssh_login'], stub=True))
    registry.register(Capability(id='setup_github_ssh', name='Configurar GitHub SSH', group='VPS · setup', section='GitHub', kind='once', icon='🐙', description='Genera la deploy key en el VPS y la registra en GitHub.', composed_of=['generate_remote_keypair', 'register_github_key', 'test_github_ssh'], stub=True))
    registry.register(Capability(id='install_coturn', name='Instalar coturn', group='VPS · setup', section='Comunicaciones', kind='once', icon='📡', description='Instala y configura el servidor TURN para las llamadas.', stub=True))
    registry.register(Capability(id='bootstrap_vps', name='Bootstrap VPS', group='VPS · setup', section='Bootstrap', kind='once', icon='🚀', description='De VPS recién creado a servicio corriendo: SSH, software, deploy, base y systemd.', composed_of=['refresh_known_host', 'setup_ssh_key', 'install_software', 'setup_github_ssh', 'update_remote', 'bootstrap_db', 'rebuild_db', 'install_systemd'], stub=True))

    # Base de datos group
    registry.register(Capability(id='bootstrap_db', name='Bootstrap DB', group='Base de datos', section='Ciclo de vida', kind='once', icon='🏗️', description='Crea rol, base, privilegios y extensiones desde cero.', level='C', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='teardown_db', name='Teardown DB', group='Base de datos', section='Ciclo de vida', kind='destructive', icon='💥', description='Borra la base y su rol: deshace lo que hizo Bootstrap DB.', level='C', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='migrate_db', name='Migrar', group='Base de datos', section='Migraciones', kind='once', icon='📐', description='Genera la migración pendiente y la aplica.', level='C', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='rebuild_db', name='Reconstruir DB', group='Base de datos', section='Ciclo de vida', kind='destructive', icon='🔁', description='Vacía las tablas, rehace migraciones y particiones, y vuelve a sembrar.', composed_of=['run_seeders', 'run_mock_seeders'], axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='run_seeders', name='Seeders base', group='Base de datos', section='Datos', kind='once', icon='🌱', description='Carga los datos mínimos que la app necesita para arrancar.', stub=True))
    registry.register(Capability(id='run_mock_seeders', name='Seeders mock', group='Base de datos', section='Datos', kind='once', icon='🎭', description='Carga datos de prueba encima de los datos base.', stub=True))
    registry.register(Capability(id='backup_db', name='Backup DB', group='Base de datos', section='Backup', kind='once', icon='💾', description='Vuelca la base a un archivo y rota los respaldos viejos.', stub=True))
    registry.register(Capability(id='ssh_tunnel', name='Túnel Postgres', group='Base de datos', section='Conexión', kind='background', icon='🔗', description='Abre un túnel SSH al Postgres del VPS para conectarse en local.', stub=True))
    registry.register(Capability(id='inspect_db', name='Inspeccionar', group='Base de datos', section='Diagnóstico', kind='once', icon='🔍', description='Muestra tablas, filas y tamaño de la base, sin modificarla.', stub=True))

    # Utils group
    registry.register(Capability(
        id='clean_artifacts', name='Limpiar artefactos', group='Utils', section='Limpieza',
        kind='destructive', icon='🧹',
        description='Borra cachés y basura de build del repo; en simulacro solo los lista.',
        axes=[
            AxisDef('families', FAMILY_AXIS_VALUES, 'checks', select='many', label='Qué borrar'),
            AxisDef('heavy', HEAVY_AXIS_VALUES, 'checks', select='many', label='Pesados',
                    checked_by_default=False, allow_empty=True),
            AxisDef('dry_run', ['simulacro', 'borrar'], 'scope'),
        ],
        stub=True))
    registry.register(Capability(id='install_android_sdk', name='SDK Android', group='Utils', section='SDKs', kind='once', icon='🤖', description='Descarga e instala el SDK de Android en esta máquina.', stub=True))
    registry.register(Capability(id='install_flutter_sdk', name='SDK Flutter', group='Utils', section='SDKs', kind='once', icon='🦋', description='Descarga e instala el SDK de Flutter en esta máquina.', stub=True))
    registry.register(Capability(id='update_cloudflare', name='Actualizar Cloudflare', group='Utils', section='DNS', kind='once', icon='☁️', description='Apunta el registro DNS de Cloudflare a la IP pública actual.', stub=True))
    registry.register(Capability(id='sync_common_files', name='Sync archivos comunes', group='Utils', section='Sync', kind='destructive', icon='🔄', description='Copia los archivos compartidos a los otros repos; en simulacro solo compara.', axes=[AxisDef('mode', ['simulacro', 'aplicar'], 'scope')], stub=True))

    # Hidden atomic capabilities
    registry.register(Capability(id='bump_version', name='Bump versión', group='Builders', section='Versión', kind='once', icon='🏷️', description='Sube el número de versión del repo.', hidden=True, stub=True))
    registry.register(Capability(id='upload_to_vps', name='Subir al VPS', group='VPS · ops', section='Subir artefacto', kind='once', icon='📤', description='Copia el artefacto compilado al VPS.', hidden=True, stub=True))
