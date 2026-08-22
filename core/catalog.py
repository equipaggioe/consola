from __future__ import annotations
from .registry import registry, Capability, AxisDef

def load_catalog() -> None:
    # Launchers group
    registry.register(Capability(id='backend', name='Backend', group='Launchers', section='Servidor', kind='live', icon='▶', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='serve_vite', name='Servir SPA Vite', group='Launchers', section='Frontend', kind='live', icon='🌐', axes=[AxisDef('target', ['panel', 'backoffice', 'landing'], 'buttons')], stub=True))
    registry.register(Capability(id='run_mobile', name='App móvil', group='Launchers', section='Móvil', kind='live', icon='📲', axes=[AxisDef('framework', ['Flutter', 'Flet'], 'buttons')], stub=True))
    registry.register(Capability(id='terminal', name='Terminal', group='Launchers', section='Dev', kind='live', icon='⌨️', stub=True))

    # Builders group
    registry.register(Capability(id='build_apk', name='Build APK', group='Builders', section='Build APK', kind='once', icon='📦', composed_of=['bump_version', 'upload_to_vps'], axes=[AxisDef('bump_mode', ['patch', 'minor', 'major'], 'field'), AxisDef('copy_to_vps', ['local', 'con subida'], 'scope')], stub=True))
    registry.register(Capability(id='build_vite', name='Build Vite', group='Builders', section='Build Vite', kind='once', icon='🏗️', composed_of=['bump_version', 'upload_to_vps'], axes=[AxisDef('target', ['panel', 'backoffice', 'landing'], 'buttons'), AxisDef('copy_to_vps', ['local', 'con subida'], 'scope')], stub=True))
    registry.register(Capability(id='build_binary', name='Build binario', group='Builders', section='Build binario', kind='once', icon='⚡', composed_of=['bump_version', 'upload_to_vps'], stub=True))
    registry.register(Capability(id='promote_app', name='Promote app', group='Builders', section='Promote', kind='destructive', icon='⬆️', stub=True))

    # Emulators group
    registry.register(Capability(id='start_emulator', name='Arrancar emulador', group='Emulators', section='Emulador', kind='live', icon='📲', axes=[AxisDef('preset', ['pixel_4', 'pixel_8', 'resizable'], 'buttons')], stub=True))
    registry.register(Capability(id='avd_manager', name='Gestor de AVD', group='Emulators', section='Gestión', kind='view', icon='🔧', stub=True))
    registry.register(Capability(id='purge_avds', name='Purgar AVDs', group='Emulators', section='Limpieza', kind='destructive', icon='🗑️', stub=True))
    registry.register(Capability(id='purge_images', name='Purgar imágenes', group='Emulators', section='Limpieza', kind='destructive', icon='🗑️', stub=True))

    # VPS · ops group
    registry.register(Capability(id='ssh_login', name='Sesión SSH', group='VPS · ops', section='Conexión', kind='interactive', icon='🔑', stub=True))
    registry.register(Capability(id='health_check', name='Health check', group='VPS · ops', section='Diagnóstico', kind='once', icon='❤️', stub=True))
    registry.register(Capability(id='run_command', name='Comando remoto', group='VPS · ops', section='Diagnóstico', kind='once', icon='💻', stub=True))
    registry.register(Capability(id='run_setup_scripts', name='Correr setup remoto', group='VPS · ops', section='Setup', kind='once', icon='📜', composed_of=['run_remote_script'], axes=[AxisDef('where', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='revoke_ssh', name='Revocar SSH', group='VPS · ops', section='Seguridad', kind='destructive', icon='🔓', stub=True))
    registry.register(Capability(id='revoke_github_ssh', name='Revocar GitHub SSH', group='VPS · ops', section='Seguridad', kind='destructive', icon='🔓', composed_of=['remove_remote_ssh_key_files', 'revoke_github_key'], stub=True))
    registry.register(Capability(id='clean_vps', name='Limpiar VPS', group='VPS · ops', section='Limpieza', kind='destructive', icon='💣', composed_of=['remove_systemd_service', 'drop_database', 'remove_deployed_repo', 'revoke_github_key', 'uninstall_packages', 'remove_vps_user'], stub=True))

    # VPS · server group
    registry.register(Capability(id='systemd_action', name='Acción systemd', group='VPS · server', section='Servicio', kind='once', icon='⚙️', axes=[AxisDef('action', ['start', 'stop', 'restart', 'status'], 'buttons', danger={'stop'}), AxisDef('action_ext', ['enable', 'disable', 'reload', 'is-active', 'is-enabled'], 'menu')], stub=True))
    registry.register(Capability(id='view_logs', name='Ver logs', group='VPS · server', section='Logs', kind='live', icon='📋', axes=[AxisDef('follow', ['sí', 'no'], 'field')], stub=True))
    registry.register(Capability(id='install_systemd', name='Instalar servicio', group='VPS · server', section='Servicio', kind='once', icon='📥', composed_of=['write_systemd_unit', 'systemd_action'], stub=True))
    registry.register(Capability(id='update_remote', name='Actualizar remoto', group='VPS · server', section='Deploy', kind='live', icon='🔄', composed_of=['git_sync_remote', 'ensure_remote_venv', 'install_remote_deps', 'upload_files', 'generate_migration', 'restart_service'], stub=True))

    # VPS · setup group
    registry.register(Capability(id='install_software', name='Software base', group='VPS · setup', section='Paquetes', kind='once', icon='📦', stub=True))
    registry.register(Capability(id='refresh_known_host', name='Refrescar known_host', group='VPS · setup', section='SSH', kind='once', icon='🔄', stub=True))
    registry.register(Capability(id='setup_ssh_key', name='Configurar SSH', group='VPS · setup', section='SSH', kind='once', icon='🔑', composed_of=['ensure_remote_user', 'configure_sudo', 'ensure_keypair', 'install_pubkey', 'test_ssh_login'], stub=True))
    registry.register(Capability(id='setup_github_ssh', name='Configurar GitHub SSH', group='VPS · setup', section='GitHub', kind='once', icon='🐙', composed_of=['generate_remote_keypair', 'register_github_key', 'test_github_ssh'], stub=True))
    registry.register(Capability(id='install_coturn', name='Instalar coturn', group='VPS · setup', section='Comunicaciones', kind='once', icon='📡', stub=True))
    registry.register(Capability(id='bootstrap_vps', name='Bootstrap VPS', group='VPS · setup', section='Bootstrap', kind='once', icon='🚀', composed_of=['refresh_known_host', 'setup_ssh_key', 'install_software', 'setup_github_ssh', 'update_remote', 'bootstrap_db', 'rebuild_db', 'install_systemd'], stub=True))

    # Base de datos group
    registry.register(Capability(id='bootstrap_db', name='Bootstrap DB', group='Base de datos', section='Ciclo de vida', kind='once', icon='🏗️', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='teardown_db', name='Teardown DB', group='Base de datos', section='Ciclo de vida', kind='destructive', icon='💥', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='migrate_db', name='Migrar', group='Base de datos', section='Migraciones', kind='once', icon='📐', axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='rebuild_db', name='Reconstruir DB', group='Base de datos', section='Ciclo de vida', kind='destructive', icon='🔁', composed_of=['run_seeders', 'run_mock_seeders'], axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    registry.register(Capability(id='run_seeders', name='Seeders base', group='Base de datos', section='Datos', kind='once', icon='🌱', stub=True))
    registry.register(Capability(id='run_mock_seeders', name='Seeders mock', group='Base de datos', section='Datos', kind='once', icon='🎭', stub=True))
    registry.register(Capability(id='backup_db', name='Backup DB', group='Base de datos', section='Backup', kind='once', icon='💾', stub=True))
    registry.register(Capability(id='ssh_tunnel', name='Túnel Postgres', group='Base de datos', section='Conexión', kind='background', icon='🔗', stub=True))
    registry.register(Capability(id='inspect_db', name='Inspeccionar', group='Base de datos', section='Diagnóstico', kind='once', icon='🔍', stub=True))

    # Utils group
    registry.register(Capability(id='clean_artifacts', name='Limpiar artefactos', group='Utils', section='Limpieza', kind='destructive', icon='🧹', axes=[AxisDef('dry_run', ['simulacro', 'borrar'], 'scope')], stub=True))
    registry.register(Capability(id='install_android_sdk', name='SDK Android', group='Utils', section='SDKs', kind='once', icon='🤖', stub=True))
    registry.register(Capability(id='install_flutter_sdk', name='SDK Flutter', group='Utils', section='SDKs', kind='once', icon='🦋', stub=True))
    registry.register(Capability(id='update_cloudflare', name='Actualizar Cloudflare', group='Utils', section='DNS', kind='once', icon='☁️', stub=True))
    registry.register(Capability(id='sync_common_files', name='Sync archivos comunes', group='Utils', section='Sync', kind='destructive', icon='🔄', axes=[AxisDef('mode', ['simulacro', 'aplicar'], 'scope')], stub=True))

    # Hidden atomic capabilities
    registry.register(Capability(id='bump_version', name='Bump versión', group='Builders', section='Versión', kind='once', icon='🏷️', stub=True))
    registry.register(Capability(id='upload_to_vps', name='Subir al VPS', group='VPS · ops', section='Subir artefacto', kind='once', icon='📤', stub=True))
