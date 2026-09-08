from __future__ import annotations
from typing import Callable

"""
El puente entre lo que marca el panel de parametros y lo que espera la
funcion real de `core/tasks/`.

Existe porque las dos puntas cambian por razones distintas: el catalogo
elige como se llama un eje para quien lo lee (`'Gradle/Android'`), y la
funcion elige como se llama su parametro para quien programa
(`families=['gradle']`). Sin este archivo esa traduccion viviria a mano
en `TabPanel._run`, mezclada con el resto del cableado de la consola.

Cada entrada de `ADAPTERS` es la senal de que esa capacidad ya dejo de ser
un stub: `TabPanel._run` corre de verdad la que tiene adaptador aca, y sigue
simulando las que no. Conectar el siguiente boton es agregar su adaptador.
"""

# Etiqueta tal como aparece en `catalog.FAMILY_AXIS_VALUES` / `HEAVY_AXIS_VALUES`
# -> clave que entiende `core.tasks.utils.find_artifacts`. Explicito a mano:
# un reorden de las listas del catalogo no debe desalinear esto.
_FAMILY_LABEL_TO_KEY = {
    'Python': 'python',
    'Gradle/Android': 'gradle',
    'Flutter': 'flutter',
    'Volcados de crash': 'crash',
}
_HEAVY_LABEL_TO_KEY = {
    'node_modules': 'node_modules',
    '.venv': 'venv',
    'build/dist': 'build',
    '.dart_tool': 'dart_tool',
}


def _clean_artifacts_kwargs(payload: dict) -> dict:
    families = [_FAMILY_LABEL_TO_KEY[v] for v in payload['variants'].get('families', [])
               if v in _FAMILY_LABEL_TO_KEY]
    heavy = [_HEAVY_LABEL_TO_KEY[v] for v in payload['variants'].get('heavy', [])
            if v in _HEAVY_LABEL_TO_KEY]
    apply = payload['options'].get('dry_run') == 'borrar'
    return {'apply': apply, 'families': families, 'heavy': heavy}


def _field(payload: dict, name: str) -> str:
    return (payload.get('fields') or {}).get(name, '')


def _option(payload: dict, name: str) -> str:
    return (payload.get('options') or {}).get(name, '')


def _pick(payload: dict, name: str) -> str:
    """El id elegido en una lista larga con busqueda (`expand='pick'`).

    Viaja aparte de `options` porque no es lo mismo: una opcion es una de tres
    marcas visibles, esto es un id de catalogo — `pixel_4`,
    `system-images;android-36;google_apis;x86_64` — que el panel muestra con su
    etiqueta legible y guarda por su valor real.
    """
    return (payload.get('picks') or {}).get(name, '')


def _install_dir_kwargs(payload: dict) -> dict:
    """El unico parametro de una instalacion de SDK: donde va.

    Vacio no es un error: cada funcion cae en el valor por defecto del
    catalogo, que es justo lo que el campo mostraba antes de vaciarlo.
    """
    return {'install_dir': _field(payload, 'install_dir')}


def _android_packages_kwargs(payload: dict) -> dict:
    """Los componentes se marcan con su nombre real, asi que no hay que traducir:
    a diferencia de las familias de artefactos, `platform-tools` se llama igual
    en el panel que en sdkmanager."""
    return {
        'components': list(payload['variants'].get('components', [])),
        'api_level': _field(payload, 'api_level'),
        'build_tools': _field(payload, 'build_tools'),
    }


def _android_sdk_kwargs(payload: dict) -> dict:
    """La compuesta recibe lo de las tres atomicas mas los pasos activos."""
    return {
        **_install_dir_kwargs(payload),
        **_android_packages_kwargs(payload),
        'steps': list(payload.get('steps') or []),
    }


def _build_apk_kwargs(payload: dict) -> dict:
    """Los tres pasos del panel son tres booleanos de la compuesta.

    'Compilar APK' desmarcado no se filtra aca: viaja como `build=False`, que
    es el modo re-subida de la funcion. Traducirlo a "no hagas nada" seria
    perder justamente la variante por la que ese paso es desmarcable.
    """
    steps = set(payload.get('steps') or [])
    return {
        # El eje se llama `app` para quien lo lee y `directory` para quien
        # programa: es justo la traduccion que este archivo existe para hacer.
        # Vacio significa "la unica que haya", que es lo que resuelve `pick()`.
        'directory': _option(payload, 'app'),
        'bump_mode': _bump_mode(payload),
        'bump': 'bump_version' in steps,
        'build': 'apk_build' in steps,
        'upload': 'upload_to_vps' in steps,
    }


def _build_vite_kwargs(payload: dict) -> dict:
    """Homologo de `_build_apk_kwargs`, con la unica diferencia entre los dos
    builders: las SPA se marcan (eje `many`), asi que lo que viaja es la lista
    de apps y no una sola.

    La lista vacia no se filtra ni se corrige: significa "la unica SPA que
    haya", que es lo mismo que el `directory` vacio del APK y lo que resuelve
    `targets.pick()`. En un repo con una sola SPA el eje ni siquiera se dibuja.
    """
    steps = set(payload.get('steps') or [])
    return {
        # El eje se llama `target` en el panel y `directories` en la funcion.
        'directories': list((payload.get('variants') or {}).get('target') or []),
        'bump_mode': _bump_mode(payload),
        'bump': 'bump_version' in steps,
        'build': 'vite_build' in steps,
        'upload': 'upload_to_vps' in steps,
    }


def _build_binary_kwargs(payload: dict) -> dict:
    """El tercer builder. Mismos pasos que los otros dos, mas los campos que
    PyInstaller necesita y ninguna otra punta traduce.

    Los tres campos viajan vacios cuando estan vacios, sin corregirlos: vacio
    significa "deducilo" — el entrypoint sale de la app Python del repo, el
    nombre de la carpeta de esa app, y sin icono se empaqueta con el de
    PyInstaller. Es el mismo criterio que el `directory` vacio del APK.

    Los dos segmentados si se traducen aca, que es para lo que existe este
    archivo: 'carpeta' y 'ventana' son como se leen, `onefile=False` y
    `windowed=True` son como se programan.
    """
    steps = set(payload.get('steps') or [])
    return {
        'entrypoint': _field(payload, 'entrypoint'),
        'name': _field(payload, 'name'),
        'icon': _field(payload, 'icon'),
        'onefile': _option(payload, 'packaging') != 'carpeta',
        'windowed': _option(payload, 'window') == 'ventana',
        'bump_mode': _bump_mode(payload),
        'bump': 'bump_version' in steps,
        'build': 'binary_build' in steps,
        'checksum': 'binary_checksum' in steps,
        'upload': 'upload_to_vps' in steps,
    }


def _bump_mode(payload: dict) -> str:
    """El eje `bump_mode` combina: un componente SemVer excluyente + `build`
    opcional. Llega como lista (`['patch', 'build']`) y se arma la cadena que
    entiende `versioning.bump`: `patch+build`, `build`, `none`, ..."""
    sel = (payload.get('options') or {}).get('bump_mode') or ['patch']
    if isinstance(sel, str):
        sel = [sel]
    base = next((v for v in sel if v != 'build'), 'patch')
    return f'{base}+build' if 'build' in sel else base


def _publish_code_kwargs(payload: dict) -> dict:
    """Los cuatro pasos del panel son los cuatro booleanos de la compuesta.

    No hay `files`: la lista de secretos es la clave `SECRET_FILES` y la lee
    `upload_secret_files` de la configuracion del repo, no del panel.
    """
    steps = set(payload.get('steps') or [])
    return {
        # 'preguntar' deja que la tarea abra el dialogo cuando el VPS tenga
        # cambios sin commitear; 'descartar' se los salta y hace el reset.
        'discard_changes': _option(payload, 'vps_dirty') == 'descartar',
        'push':   'push_repo'      in steps,
        'pull':   'git_pull'       in steps,
        'deps':   'install_deps'   in steps,
        'upload': 'upload_secrets' in steps,
    }


def _update_remote_kwargs(payload: dict) -> dict:
    """Los seis del despliegue: los cuatro de `publish_code` mas los dos que
    tocan lo que ya esta corriendo. Se derivan del mismo lector por la misma
    razon por la que `UPDATE_REMOTE_STEPS` se deriva de `PUBLISH_CODE_STEPS`:
    los cuatro ids son los mismos y no tienen por que leerse dos veces."""
    steps = set(payload.get('steps') or [])
    return {
        **_publish_code_kwargs(payload),
        'migrate': 'apply_migrations' in steps,
        'restart': 'restart_service'  in steps,
    }


def _variant(payload: dict, name: str) -> str:
    """El unico valor marcado de un eje `many` que la interfaz ya repartio.

    Un launcher con `fanout` recibe su payload con un solo valor en el eje
    (`ui/tab_panel.py::_run_fanout` abre una pestana por cada uno), asi que aca
    no hay una lista que recorrer: hay uno, o ninguno cuando el repo tiene una
    sola app y el eje ni se dibujo.
    """
    valores = (payload.get('variants') or {}).get(name) or []
    return valores[0] if valores else ''


def _backend_kwargs(payload: dict) -> dict:
    """El segmentado local/remoto viaja tal cual: `core.database` usa esas dos
    mismas palabras como valores del ambito (`db.LOCAL` / `db.REMOTE`)."""
    return {'scope': _option(payload, 'scope') or 'local'}


def _serve_vite_kwargs(payload: dict) -> dict:
    """Una SPA por pestana. Vacio significa "la unica que haya" (`targets.pick`)."""
    return {'target': _variant(payload, 'target')}


def _run_mobile_kwargs(payload: dict) -> dict:
    """El eje se llama `app` para quien lo lee y `target` para quien programa."""
    return {'target': _option(payload, 'app')}


def _terminal_kwargs(payload: dict) -> dict:
    return {
        'target': _option(payload, 'app'),
        'auto_login': _option(payload, 'auto_login') == 'sí',
    }


def _create_avd_kwargs(payload: dict) -> dict:
    """Dos catalogos y un nombre opcional.

    El nombre vacio no se filtra: es el caso normal, y la funcion lo deriva del
    dispositivo y la API (`pixel_4_api36`).
    """
    return {
        'device': _pick(payload, 'device'),
        'image': _pick(payload, 'image'),
        'name': _field(payload, 'name'),
    }


def _launch_emulator_kwargs(payload: dict) -> dict:
    """`-wipe-data` es una opcion de arranque, no un paso: borra los datos del
    AVD antes de levantarlo y no tiene sentido pedirla sin arrancar."""
    return {
        'avd': _pick(payload, 'avd'),
        'wipe': _option(payload, 'boot') == 'borrar datos',
    }


def _purge_emulators_kwargs(payload: dict) -> dict:
    """Las dos listas se marcan con su id real, asi que no hay que traducir:
    a diferencia de las familias de artefactos, el nombre de un AVD es el
    mismo en el panel que en avdmanager."""
    variants = payload.get('variants') or {}
    return {
        'avds': list(variants.get('avds', [])),
        'images': list(variants.get('images', [])),
        'apply': _option(payload, 'dry_run') == 'borrar',
    }


# --- VPS - setup -----------------------------------------------------------

def _setup_ssh_kwargs(payload: dict) -> dict:
    """Los tres pasos del panel son los tres booleanos, y el eje es el modo de sudo.

    `sudo_mode` llega vacio solo si el eje no se dibujo (un preset viejo guardado
    antes de que existiera); en ese caso vale el mismo default que declara el
    catalogo, no un error.
    """
    steps = set(payload.get('steps') or [])
    return {
        'sudo_mode': _option(payload, 'sudo_mode') or 'all',
        'access': 'deploy_access' in steps,
        'sudo':   'sudo_rules'    in steps,
        'verify': 'verify_login'  in steps,
    }


def _setup_github_ssh_kwargs(payload: dict) -> dict:
    """Aca los ids de los pasos son los nombres de las atomicas: salen de
    `composed_of`, que en esta capacidad si nombra funciones reales."""
    steps = set(payload.get('steps') or [])
    return {
        'generate': 'generate_remote_keypair' in steps,
        'register': 'register_github_key'     in steps,
        'verify':   'test_github_ssh'         in steps,
    }


def _install_software_kwargs(payload: dict) -> dict:
    """Las casillas marcadas son la lista de grupos, tal cual.

    Los valores del eje son las claves de `vps.PACKAGE_GROUPS`, no etiquetas
    traducidas: no hay tabla que mantener como en `clean_artifacts`, y un grupo
    nuevo en `core/vps.py` aparece solo en el panel.

    Lista vacia no llega nunca (el eje no declara `allow_empty`, asi que el panel
    bloquea el boton), pero si llegara, `None` deja que la funcion caiga en
    `DEFAULT_GROUPS` en vez de instalar nada en silencio.
    """
    return {'groups': (payload['variants'].get('groups') or None)}


# --- VPS - ops -------------------------------------------------------------

_CLEAN_VPS_STEPS = ('service', 'database', 'repo', 'github_key', 'packages', 'user')


def _clean_vps_kwargs(payload: dict) -> dict:
    """Un booleano por casilla, con los mismos ids que declara `CLEAN_VPS_STEPS`.

    Desmarcar todo no se traduce a "corre igual": la funcion recibe los seis en
    False y no toca nada, que es lo que pidio quien desmarco. La confirmacion
    tipeada de la IP vive dentro de `clean_vps`, no aca.
    """
    steps = set(payload.get('steps') or [])
    return {nombre: nombre in steps for nombre in _CLEAN_VPS_STEPS}


_BOOTSTRAP_STEPS = ('known_host', 'ssh_key', 'software', 'github_ssh',
                    'deploy', 'database', 'service')


def _bootstrap_vps_kwargs(payload: dict) -> dict:
    """La compuesta de compuestas: un booleano por paso, mas el modo de sudo y
    los paquetes que reenvia a las compuestas de adentro."""
    steps = set(payload.get('steps') or [])
    kwargs = {nombre: nombre in steps for nombre in _BOOTSTRAP_STEPS}
    kwargs['sudo_mode'] = _option(payload, 'sudo_mode') or 'all'
    kwargs['groups'] = payload['variants'].get('groups') or None
    return kwargs


# capability_id -> payload (de ParamsPanel.payload()) -> kwargs de la funcion real
ADAPTERS: dict[str, Callable[[dict], dict]] = {
    # Launchers. `dev_env` no esta aca a proposito: es una compuesta concurrente
    # y no llama a ninguna funcion de `core/tasks/` — la despacha `TabPanel`
    # abriendo una pestana por paso (docs/launchers.md 2.5).
    'backend': _backend_kwargs,
    'serve_vite': _serve_vite_kwargs,
    'run_mobile': _run_mobile_kwargs,
    'terminal': _terminal_kwargs,
    'build_apk': _build_apk_kwargs,
    'build_vite': _build_vite_kwargs,
    'build_binary': _build_binary_kwargs,
    # Sin parametros: las rutas salen de `SECRET_FILES` (Configuracion).
    'upload_secret_files': lambda payload: {},
    'publish_code': _publish_code_kwargs,
    'update_remote': _update_remote_kwargs,
    # VPS - setup. Los dos sin parametros no son un olvido: `refresh_known_host`
    # solo necesita VPS_IP y el realm de `install_coturn` sale de CF_DOMAIN_NAME
    # o del propio host. Si alguno gana un eje despues, gana adaptador con el.
    'refresh_known_host': lambda payload: {},
    'setup_ssh_key': _setup_ssh_kwargs,
    'setup_github_ssh': _setup_github_ssh_kwargs,
    'install_software': _install_software_kwargs,
    'install_coturn': lambda payload: {},
    'bootstrap_vps': _bootstrap_vps_kwargs,
    # Base de datos. Ninguna declara `steps=` en el catalogo (solo el eje
    # `scope`), asi que el mismo adaptador de `backend` alcanza: el resto de
    # los booleanos de cada funcion se quedan en su default (`True`).
    'bootstrap_db': _backend_kwargs,
    'rebuild_db': _backend_kwargs,
    # VPS - ops. La compuesta destructiva: seis casillas, seis booleanos.
    'clean_vps': _clean_vps_kwargs,
    'clean_artifacts': _clean_artifacts_kwargs,
    'install_android_tools': _install_dir_kwargs,
    'install_android_packages': _android_packages_kwargs,
    'install_android_hypervisor': lambda payload: {},
    'install_android_sdk': _android_sdk_kwargs,
    'install_flutter_sdk': _install_dir_kwargs,
    'install_system_image': lambda payload: {'image': _pick(payload, 'image')},
    'create_avd': _create_avd_kwargs,
    'launch_emulator': _launch_emulator_kwargs,
    'purge_emulators': _purge_emulators_kwargs,
    # No tiene panel: lo dispara el ✕ de la cabecera de estado, que pasa el
    # serial directo (`ui/tab_panel.py::_stop_live`).
    'stop_emulator': lambda payload: {'serial': _pick(payload, 'serial')},
}
