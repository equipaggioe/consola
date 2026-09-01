from __future__ import annotations
from typing import Callable

from core.envfile import split_list

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


def _bump_mode(payload: dict) -> str:
    """El eje `bump_mode` combina: un componente SemVer excluyente + `build`
    opcional. Llega como lista (`['patch', 'build']`) y se arma la cadena que
    entiende `versioning.bump`: `patch+build`, `build`, `none`, ..."""
    sel = (payload.get('options') or {}).get('bump_mode') or ['patch']
    if isinstance(sel, str):
        sel = [sel]
    base = next((v for v in sel if v != 'build'), 'patch')
    return f'{base}+build' if 'build' in sel else base


def _files(payload: dict) -> list[str]:
    """El campo "Archivos a copiar" es una caja con una ruta por renglon.

    Se parte aca y no en la tarea porque es exactamente el trabajo de este
    archivo: el panel entrega texto tal como se escribio, y la funcion espera
    la lista de rutas que va a recorrer. `split_list` acepta tambien comas, asi
    que lo que alguien haya dejado escrito en una sola linea sigue valiendo.
    """
    return split_list(_field(payload, 'files'))


def _upload_secrets_kwargs(payload: dict) -> dict:
    return {'files': _files(payload)}


def _update_remote_kwargs(payload: dict) -> dict:
    """Los seis pasos del panel son los seis booleanos de la compuesta.

    `files` viaja aunque el paso de secretos este desmarcado: la compuesta lo
    ignora en ese caso, y asi el adaptador no tiene que saber en que orden se
    leen los pasos.
    """
    steps = set(payload.get('steps') or [])
    return {
        'files': _files(payload),
        'push':    'push_repo'        in steps,
        'pull':    'git_pull'         in steps,
        'deps':    'install_deps'     in steps,
        'upload':  'upload_secrets'   in steps,
        'migrate': 'apply_migrations' in steps,
        'restart': 'restart_service'  in steps,
    }


# capability_id -> payload (de ParamsPanel.payload()) -> kwargs de la funcion real
ADAPTERS: dict[str, Callable[[dict], dict]] = {
    'build_apk': _build_apk_kwargs,
    # Sin parametros: empuja la rama de la carpeta abierta y nada mas.
    'push_repository': lambda payload: {},
    'upload_secret_files': _upload_secrets_kwargs,
    'update_remote': _update_remote_kwargs,
    'clean_artifacts': _clean_artifacts_kwargs,
    'install_android_tools': _install_dir_kwargs,
    'install_android_packages': _android_packages_kwargs,
    'install_android_hypervisor': lambda payload: {},
    'install_android_sdk': _android_sdk_kwargs,
    'install_flutter_sdk': _install_dir_kwargs,
}
