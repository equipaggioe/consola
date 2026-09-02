from __future__ import annotations
import os
from dataclasses import replace
from pathlib import Path

from . import android, cache, targets
from .errors import TaskError
from .registry import registry, Capability, AxisDef, Step

# Marca de agua del campo "Archivos a copiar". Es un ejemplo del formato, no un
# default: que archivos secretos tiene un repo lo sabe quien lo configura, y
# dejar una lista puesta haria que el primer deploy intentara copiar rutas que
# quiza no existen en este proyecto.
UPLOAD_FILES_HINT = 'server/.env\nserver/certs/cert.pem\nserver/certs/key.pem'

# Multilinea: una ruta por renglon. Una lista de secretos son tres o cuatro
# rutas largas, y en una sola linea no se ve donde termina una y empieza otra.
# Las comas se siguen aceptando al leerlo (`envfile.split_list`).
_FILES_AXIS = lambda: AxisDef('files', [''], 'field', label='Archivos a copiar',
                              placeholder=UPLOAD_FILES_HINT, multiline=True)

_VPS_KEYS = {'VPS_IP', 'VPS_USER', 'VPS_KEY_NAME', 'VPS_DEPLOY_DIR'}


def for_project(cap: Capability, root: Path | str | None) -> Capability:
    """La capacidad tal como se ve con este repo abierto.

    Los ejes descubiertos (PLAN.md 2.4) no pueden declararse en `load_catalog()`:
    el catalogo se arma una vez al arrancar y el repo cambia con el selector.
    Aca se les llenan los valores mirando el repo, justo antes de dibujar el
    panel — en `navetta` el eje de SPA da tres, en un repo con solo `panel/` da
    una, y un subproyecto nuevo aparece sin tocar el catalogo.

    Devuelve la misma capacidad cuando no hay nada que descubrir, asi que no
    cuesta nada llamarla para todas.
    """
    if not root or not any(a.is_discovered for a in cap.axes):
        return cap
    # `Project.path` es un str; el descubrimiento trabaja con rutas.
    carpeta = Path(root)
    if not carpeta.is_dir():
        return cap
    resueltos = [replace(a, values=targets.names_of(carpeta, a.discover)) if a.is_discovered else a
                 for a in cap.axes]
    return replace(cap, axes=resueltos)


# --- catalogos de la maquina ----------------------------------------------
# Un eje `discover` se llena mirando el repo abierto (`core/targets.py`). Estos
# se llenan preguntandole al SDK: que dispositivos existen, que maquinas
# virtuales hay publicadas, cuales estan instaladas, que AVD hay creados. Son la
# misma idea de PLAN.md 2.4 aplicada a la maquina en vez de a la carpeta — y por
# eso viven aca, al lado de `for_project`, y no en el catalogo de botones.

ANDROID_DEVICES = 'android_devices'            # catalogo de dispositivos
ANDROID_IMAGES = 'android_images'              # catalogo de maquinas publicadas
ANDROID_IMAGES_INSTALLED = 'android_installed'  # maquinas ya instaladas
ANDROID_AVDS = 'android_avds'                  # AVD ya creados
ANDROID_RUNNING = 'android_running'            # emuladores vivos ahora mismo

# Lo instalado y lo creado cambian mientras Consola esta abierta, asi que se
# cachean por un minuto y nada mas: alcanza para no repetir la consulta al abrir
# tres pestanas seguidas, y no alcanza para mentir despues de una instalacion.
# Los dos catalogos grandes usan el mes por defecto de `core/cache.py`.
_FRESCO = 60.0


def machine_values(source: str, *, refresh: bool = False) -> tuple[list[str], dict[str, str]]:
    """Los valores de un eje de maquina, con sus etiquetas legibles.

    Devuelve `([], {})` cuando el SDK no esta instalado en vez de fallar: un eje
    vacio ya se explica solo en el panel ("no hay ... en esta maquina"), y una
    excepcion aca dejaria sin dibujar toda la pestana.
    """
    try:
        sdk = android.resolve_sdk()
        if source == ANDROID_DEVICES:
            catalogo = android.device_catalog(sdk, refresh=refresh)
            return [d.id for d in catalogo], {d.id: d.label for d in catalogo}
        if source == ANDROID_IMAGES:
            catalogo = android.image_catalog(sdk, refresh=refresh)
            return [i.package for i in catalogo], {i.package: i.label for i in catalogo}
        if source == ANDROID_IMAGES_INSTALLED:
            paquetes = cache.cached('android-installed', lambda: android.list_images(sdk),
                                    max_age=_FRESCO, refresh=refresh)
            imagenes = sorted((android.parse_image(p) for p in paquetes), key=lambda i: i.order)
            return [i.package for i in imagenes], {i.package: i.label for i in imagenes}
        if source == ANDROID_AVDS:
            nombres = cache.cached('android-avds', lambda: android.list_avds(sdk),
                                   max_age=_FRESCO, refresh=refresh)
            return list(nombres), {}
        if source == ANDROID_RUNNING:
            # Nunca cacheado: es estado, no catalogo. Una respuesta vieja aca
            # ofreceria apagar un emulador que ya no existe.
            vivos = android.running(sdk)
            return list(vivos), {s: f'{n or "?"}  ({s})' for s, n in vivos.items()}
    except TaskError:
        return [], {}
    return [], {}


def forget_machine_cache() -> None:
    """Olvida lo que cambia al instalar, crear o borrar. La llama la UI cuando
    termina una tarea de maquina: el proximo panel ve el estado nuevo."""
    cache.forget('android-installed')
    cache.forget('android-avds')


def for_machine(cap: Capability, *, refresh: bool = False) -> Capability:
    """La capacidad tal como se ve en ESTA maquina.

    Hermana de `for_project`: misma mecanica, otra fuente. Se llama despues,
    asi una capacidad puede tener ejes de las dos clases.
    """
    if not any(a.is_from_machine for a in cap.axes):
        return cap
    resueltos = []
    for eje in cap.axes:
        if not eje.is_from_machine:
            resueltos.append(eje)
            continue
        values, labels = machine_values(eje.source, refresh=refresh)
        resueltos.append(replace(eje, values=values, labels=labels))
    return replace(cap, axes=resueltos)

# Valores por defecto de los SDK. Viven aca, con el resto de la forma de los
# botones, y `core/tasks/utils.py` los importa para usar el mismo cuando se le
# llama sin parametros: asi el panel y la funcion no pueden discrepar.
# En Linux se usan las rutas convencionales bajo el home; en Windows, las
# unidades que ya usaban los scripts.
ANDROID_DIR_DEFAULT = r'D:\Android' if os.name == 'nt' else '~/Android/Sdk'
FLUTTER_DIR_DEFAULT = r'D:\flutter' if os.name == 'nt' else '~/flutter'
API_LEVEL_DEFAULT = '36'
BUILD_TOOLS_DEFAULT = '36.0.0'

ANDROID_PACKAGE_AXES = [
    AxisDef('components', ['platform-tools', 'emulator', 'build-tools', 'platform'],
            'checks', select='many', label='Componentes'),
    AxisDef('api_level', [API_LEVEL_DEFAULT], 'field', label='API level'),
    AxisDef('build_tools', [BUILD_TOOLS_DEFAULT], 'field', label='Build-tools'),
]

# Etiquetas visibles de los ejes de 'clean_artifacts'; `ui/task_adapters.py`
# las traduce de vuelta a las claves que entiende `core/tasks/utils.py`.
FAMILY_AXIS_VALUES = ['Python', 'Gradle/Android', 'Flutter', 'Volcados de crash']
HEAVY_AXIS_VALUES = ['node_modules', '.venv', 'build/dist', '.dart_tool']

# Orden de lectura: primero el componente SemVer de menos a mas peso... salvo
# que la costumbre es al reves. Se muestran mayor->menor y `build` (que stackea
# con cualquiera) queda antes de `none`. El default real es `patch`.
BUMP_MODES = ['major', 'minor', 'patch', 'build', 'none']
_BUMP_AXIS = lambda: AxisDef('bump_mode', BUMP_MODES, 'scope', label='Bump',
                             combine={'build'}, default='patch')

# El paso nucleo va en su orden real, entre el bump y la subida. A diferencia
# de los otros dos builders, 'Compilar APK' si se puede desmarcar: sin
# compilar, la capacidad sube el APK que ya esta en disco. Es el modo que el
# script original activaba con BUILD_APK=false, y la razon es economica —
# retomar un scp cortado no deberia costar diez minutos de build.
BUILD_APK_STEPS = [
    Step('bump_version', 'Bump versión'),
    Step('apk_build', 'Compilar APK', requires_env={'API_URL'}),
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

# Los seis pasos del despliegue, en el orden en que ocurren: primero se publica
# lo local, después el VPS lo trae. Las claves van por paso y no en el
# `required_by` de la capacidad (§4.2 de docs/atomicas.md): "solo recopiar los
# certificados" no tiene por qué quedar bloqueado por GIT_REPO_URL.
#
# 'push_repo' arranca desmarcado porque publica hacia afuera; el resto son
# operaciones sobre el servidor del proyecto y van marcadas.
UPDATE_REMOTE_STEPS = [
    Step('push_repo', 'Push del repo local', default=False),
    Step('git_pull', 'Pull en el VPS', requires_env={'GIT_REPO_URL', 'VPS_DEPLOY_DIR'}),
    Step('install_deps', 'Dependencias', requires_env={'VPS_PYTHON', 'SERVER_DIR'}),
    Step('upload_secrets', 'Archivos que no viajan por git'),
    Step('apply_migrations', 'Aplicar migraciones', requires_env={'DB_NAME', 'DB_PASSWORD'}),
    Step('restart_service', 'Reiniciar servicio'),
]


# Los tres launchers del arranque diario, como pasos de una compuesta que NO es
# una secuencia: se lanzan a la vez, cada uno en su pestana, y ninguno termina
# (docs/launchers.md 2.5). El orden de esta lista es el de despacho, y el unico
# que importa es que el backend salga primero: los otros dos esperan su endpoint.
DEV_ENV_STEPS = [
    Step('backend', 'Backend', optional=False),
    Step('serve_vite', 'SPA Vite'),
    Step('terminal', 'Terminal', default=False),
]


def load_catalog() -> None:
    """Declara la forma de cada boton.

    `description` es la linea que la UI muestra en el tooltip del rail y bajo el
    nombre de la accion: que hace, en presente y en una oracion. `level` solo se
    escribe cuando no se deduce solo: una compuesta que no publica sus pasos
    (`bootstrap_db`, `teardown_db`) tiene que declararse `level='C'` a mano,
    porque sin `steps` ni `composed_of` la UI la tomaria por atomica.
    """
    # Launchers group
    # Las secciones agrupan por lo que el launcher TE ENTREGA, que es lo mismo
    # que decide si su pestana tiene segunda vista: una URL se mira en un
    # navegador, un emulador se mira en su ventana (docs/launchers.md 2.4).
    #
    # `view='web'` no es un boton mas ni una capacidad aparte: es la segunda
    # vista de la pestana del propio launcher, apuntada al endpoint que la tarea
    # publica con `ctx.serve()`. Un boton "abrir navegador" en el rail seria una
    # capacidad que no ejecuta nada, no registra nada y no tiene parametros.
    registry.register(Capability(
        id='backend', name='Backend', group='Launchers', section='Servidor',
        kind='live', icon='▶', view='web',
        description='Levanta el servidor FastAPI del repo, local o contra el VPS.',
        axes=[AxisDef('scope', ['local', 'remoto'], 'scope')], stub=True))
    # `fanout='target'`: marcar panel + backoffice son dos dev servers vivos a la
    # vez, no dos pasos en fila. Un eje `many` se recorre en bucle cuando la
    # capacidad termina (`build_vite`) y se reparte en pestanas cuando no
    # (docs/launchers.md 2.1).
    registry.register(Capability(
        id='serve_vite', name='Servir SPA Vite', group='Launchers', section='Web',
        kind='live', icon='🌐', view='web', fanout='target',
        description='Arranca el dev server de Vite para las apps elegidas.',
        axes=[AxisDef('target', [], 'checks', select='many', label='Apps',
                      discover=(targets.SPA_VITE,))], stub=True))
    # No hay eje `framework`: elegir "Flutter o Flet" seria pedir que confirmen
    # algo que la carpeta ya contesta. Se elige la app; el framework viene con ella.
    # Tampoco tiene `view`: lo que entrega no es una URL, es una app en un
    # emulador, y esa ventana la dibuja Android.
    registry.register(Capability(
        id='run_mobile', name='App móvil', group='Launchers', section='Dispositivo',
        kind='live', icon='📲',
        description='Corre la app móvil en el emulador o dispositivo conectado.',
        axes=[AxisDef('app', [], 'scope', label='App móvil', discover=targets.MOBILE_APP)],
        stub=True))
    # La carpeta dejo de estar fija en el codigo: `python-app` es un tipo mas de
    # `core/targets.py`, descubierto como las SPA (PLAN.md 2.4).
    registry.register(Capability(
        id='terminal', name='Terminal', group='Launchers', section='Escritorio',
        kind='live', icon='⌨️',
        description='Arranca la app de terminal del repo, con recarga al cambiar sus fuentes.',
        axes=[AxisDef('app', [], 'scope', label='App', discover=(targets.PYTHON_APP,)),
              AxisDef('auto_login', ['no', 'sí'], 'scope', label='Auto-login de dev')],
        stub=True))
    # La compuesta concurrente del grupo. No tiene `func` ni adaptador: su
    # cuerpo es el despachador de `ui/tab_panel.py`, porque "una pestana por
    # paso, todas vivas a la vez" no significa nada dentro de `core/`
    # (docs/launchers.md 2.5). Por eso se declara `stub=False` a mano.
    registry.register(Capability(
        id='dev_env', name='Entorno de desarrollo', group='Launchers',
        section='Todo junto', kind='live', icon='🧪', level='C', concurrent=True,
        description='Levanta backend, SPA y terminal a la vez, cada uno en su pestaña.',
        steps=DEV_ENV_STEPS, composed_of=['backend', 'serve_vite', 'terminal'],
        stub=False))

    # Builders group
    # `app` se descubre: un valor por app móvil del repo, sea Flutter o Flet. El
    # framework no se pregunta aparte porque viaja dentro del target elegido.
    # `bump_mode` es una lista cerrada, no un texto: va como opción excluyente
    # (igual que `dry_run` en clean_artifacts) y no como campo escrito.
    registry.register(Capability(id='build_apk', name='Build APK', group='Builders', section='Build APK', kind='once', icon='📦', description='Sube la versión, compila el APK y opcionalmente lo publica en el VPS.', composed_of=['bump_version', 'upload_to_vps'], axes=[AxisDef('app', [], 'scope', label='App móvil', discover=targets.MOBILE_APP), _BUMP_AXIS()], steps=BUILD_APK_STEPS, stub=True))
    registry.register(Capability(id='build_vite', name='Build Vite', group='Builders', section='Build Vite', kind='once', icon='🏗️', description='Sube la versión, compila las SPA elegidas y opcionalmente las publica.', axes=[AxisDef('target', [], 'checks', select='many', label='Apps', discover=(targets.SPA_VITE,)), _BUMP_AXIS()], steps=BUILD_VITE_STEPS, stub=True))
    registry.register(Capability(id='build_binary', name='Build binario', group='Builders', section='Build binario', kind='once', icon='⚡', description='Sube la versión, compila el ejecutable y opcionalmente lo publica.', steps=BUILD_BINARY_STEPS, stub=True))
    registry.register(Capability(id='promote_app', name='Promote app', group='Builders', section='Promote', kind='destructive', icon='⬆️', description='Promueve el último artefacto subido al canal de producción.', stub=True))

    # Emulators group
    # Los cuatro botones son de la maquina, no del repo: un AVD sirve para
    # cualquier proyecto, igual que el SDK. Instalar la maquina virtual, crear
    # el AVD y arrancarlo dejaron de ser tres casillas de una compuesta y son
    # tres botones, porque cada uno tiene su propio catalogo de opciones: un
    # paso con opciones propias ya no entra en una casilla (docs/emuladores.md).
    registry.register(Capability(
        id='install_system_image', name='Instalar máquina', group='Emulators',
        section='Instalación', kind='once', icon='💿', scope='machine',
        description='Descarga del SDK la máquina virtual (system image) que va a correr el AVD.',
        axes=[AxisDef('image', [], 'pick', label='Máquina virtual',
                      source=ANDROID_IMAGES)],
        stub=True))
    registry.register(Capability(
        id='create_avd', name='Crear AVD', group='Emulators',
        section='Instalación', kind='once', icon='🧱', scope='machine',
        description='Crea el dispositivo virtual eligiéndolo del catálogo del SDK.',
        axes=[AxisDef('device', [], 'pick', label='Dispositivo',
                      source=ANDROID_DEVICES),
              AxisDef('image', [], 'pick', label='Máquina virtual (instaladas)',
                      source=ANDROID_IMAGES_INSTALLED),
              # Vacio a proposito: el nombre se deriva del dispositivo y la API
              # (`pixel_4_api36`). Solo se escribe cuando hace falta distinguir
              # dos AVD del mismo modelo.
              AxisDef('name', [''], 'field', label='Nombre del AVD',
                      placeholder='se deriva del dispositivo y la API')],
        stub=True))
    registry.register(Capability(
        id='launch_emulator', name='Emulador', group='Emulators',
        section='Emulador', kind='live', icon='📲', scope='machine',
        description='Arranca uno de los AVD ya creados. Se puede lanzar otro con uno corriendo.',
        axes=[AxisDef('avd', [], 'pick', label='AVD', source=ANDROID_AVDS),
              AxisDef('boot', ['normal', 'borrar datos'], 'scope', label='Arranque',
                      danger={'borrar datos'})],
        live_state=ANDROID_RUNNING,
        stub=True))
    # Un solo boton de limpieza para las dos cosas que ocupan disco: el AVD
    # pesa cientos de MB y la maquina virtual, varios GB. Borrar uno suelto es
    # marcar una casilla, no otro boton (docs/atomicas.md 1).
    registry.register(Capability(
        id='purge_emulators', name='Liberar disco', group='Emulators',
        section='Limpieza', kind='destructive', icon='🗑️', scope='machine',
        description='Borra AVD y máquinas virtuales; en simulacro solo los lista con su tamaño.',
        axes=[AxisDef('avds', [], 'checks', select='many', label='AVD',
                      source=ANDROID_AVDS, checked_by_default=False, allow_empty=True),
              AxisDef('images', [], 'checks', select='many', label='Máquinas virtuales',
                      source=ANDROID_IMAGES_INSTALLED, checked_by_default=False,
                      allow_empty=True),
              AxisDef('dry_run', ['simulacro', 'borrar'], 'scope')],
        stub=True))

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
    # La mitad local del despliegue: el VPS hace pull de GitHub, no de esta
    # maquina. Tiene boton propio porque empujar sin desplegar se pide solo.
    # Sin ejes: empuja la rama de la carpeta abierta a su remoto y se acabo. No
    # commitea (eso es trabajo, no despliegue) ni declara `required_by` de
    # ninguna clave: git ya sabe cual es su remoto.
    registry.register(Capability(
        id='push_repository', name='Push del repo', group='VPS · server', section='Deploy',
        kind='once', icon='⬆️',
        description='Empuja la rama local a su remoto. No commitea: si hay cambios pendientes, corta.',
        stub=True))
    # `composed_of` declaraba seis ids que no eran capacidades de nadie
    # (`git_sync_remote`, `upload_files`, `generate_migration`): nombres sueltos
    # que la UI alcanzaba a mostrar bonitos, pero que no apuntaban a ninguna
    # función ni permitían declarar claves por paso. Los reemplazan los `Step`
    # de arriba, que sí son los pasos que corre la compuesta.
    registry.register(Capability(
        id='update_remote', name='Actualizar remoto', group='VPS · server', section='Deploy',
        kind='live', icon='🔄',
        description='Despliega: publica el código, lo trae al VPS, instala, sube secretos y reinicia.',
        axes=[_FILES_AXIS(),
              # El `git reset --hard` del VPS es la unica parte destructiva del
              # despliegue, y hay dos formas legitimas de tratarla: 'preguntar'
              # abre el dialogo con la lista de archivos a la vista, 'descartar'
              # no pregunta. Lo segundo es lo que se quiere cuando el VPS es
              # descartable y el ruido lo genera el propio servicio; lo primero,
              # cuando alguien pudo haber tocado algo a mano ahi.
              AxisDef('vps_dirty', ['preguntar', 'descartar'], 'scope',
                      label='Si el VPS tiene cambios sin commitear',
                      danger={'descartar'})],
        steps=UPDATE_REMOTE_STEPS, stub=True))

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
    # Los SDK son de la maquina, no del repo abierto: `scope='machine'`. La
    # instalacion se parte en tres atomicas porque agregar paquetes es lo que
    # se repite (una API nueva, otro build-tools) y no tiene por que arrastrar
    # la descarga del SDK ni tocar el PATH.
    registry.register(Capability(
        id='install_android_tools', name='Herramientas Android', group='Utils',
        section='SDKs', kind='once', icon='🧰', scope='machine',
        description='Descarga las command-line tools del SDK y las deja en el entorno del usuario.',
        axes=[AxisDef('install_dir', [ANDROID_DIR_DEFAULT], 'field', label='Directorio')],
        stub=True))
    registry.register(Capability(
        id='install_android_packages', name='Paquetes del SDK', group='Utils',
        section='SDKs', kind='once', icon='📦', scope='machine',
        description='Acepta las licencias e instala en el SDK los paquetes que falten.',
        axes=list(ANDROID_PACKAGE_AXES), stub=True))
    registry.register(Capability(
        id='install_android_hypervisor', name='Aceleración del emulador', group='Utils',
        section='SDKs', kind='once', icon='⚡', scope='machine',
        description='Verifica la virtualización que el emulador necesita, y en Windows instala el driver.',
        stub=True))
    registry.register(Capability(
        id='install_android_sdk', name='SDK Android', group='Utils', section='SDKs',
        kind='once', icon='🤖', scope='machine',
        description='Instala el SDK de Android completo: herramientas, paquetes y aceleración.',
        composed_of=['install_android_tools', 'install_android_packages',
                     'install_android_hypervisor'],
        axes=[AxisDef('install_dir', [ANDROID_DIR_DEFAULT], 'field', label='Directorio'),
              *ANDROID_PACKAGE_AXES],
        stub=True))
    registry.register(Capability(
        id='install_flutter_sdk', name='SDK Flutter', group='Utils', section='SDKs',
        kind='once', icon='🦋', scope='machine',
        description='Descarga el canal stable de Flutter y lo deja en el entorno del usuario.',
        axes=[AxisDef('install_dir', [FLUTTER_DIR_DEFAULT], 'field', label='Directorio')],
        stub=True))
    registry.register(Capability(id='update_cloudflare', name='Actualizar Cloudflare', group='Utils', section='DNS', kind='once', icon='☁️', description='Apunta el registro DNS de Cloudflare a la IP pública actual.', stub=True))
    registry.register(Capability(id='sync_common_files', name='Sync archivos comunes', group='Utils', section='Sync', kind='destructive', icon='🔄', description='Copia los archivos compartidos a los otros repos; en simulacro solo compara.', axes=[AxisDef('mode', ['simulacro', 'aplicar'], 'scope')], stub=True))

    # Hidden atomic capabilities
    # Apagar no es un boton del rail: cerrar la pestana del emulador ya lo
    # apaga, y para los huerfanos —un emulador de una sesion anterior o
    # arrancado desde Android Studio— esta el ✕ de la cabecera de estado del
    # panel, que es donde se ven. Sigue siendo una capacidad porque la corre el
    # runner como cualquier otra, con su log en la consola.
    registry.register(Capability(
        id='stop_emulator', name='Apagar emulador', group='Emulators',
        section='Emulador', kind='once', icon='⏹', scope='machine',
        description='Apaga por adb el emulador indicado.', hidden=True, stub=True))
    registry.register(Capability(id='bump_version', name='Bump versión', group='Builders', section='Versión', kind='once', icon='🏷️', description='Sube el número de versión del repo.', hidden=True, stub=True))
    registry.register(Capability(id='upload_to_vps', name='Subir al VPS', group='VPS · ops', section='Subir artefacto', kind='once', icon='📤', description='Copia el artefacto compilado al VPS.', hidden=True, stub=True))
    # Visible, no oculta: "solo recopiar los certificados" es el paso que mas se
    # pide suelto de todo el despliegue.
    registry.register(Capability(
        id='upload_secret_files', name='Copiar secretos', group='VPS · server',
        section='Deploy', kind='once', icon='🔐',
        description='Copia al VPS los archivos que nunca viajan por git.',
        axes=[_FILES_AXIS()], stub=True))
