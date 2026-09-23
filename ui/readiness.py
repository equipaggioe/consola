from __future__ import annotations

from core.catalog import applicable_ids, for_project
from core.registry import registry
from core import targets
from core.settings import required_keys_for
from core import envfile
from ui import params_store


def missing_keys(capability, env: dict[str, str], repo_path: str) -> list[str]:
    """Que le falta a una accion para poder correr sin abrir la pestana.

    Correr de una (el boton ▶ del buscador) usa los
    parametros guardados para ese boton en ese repo, asi que se mira
    exactamente lo que esos parametros van a correr: los pasos apagados no
    pueden reclamar claves. Sin nada guardado se cuentan todos los pasos, que
    es lo que correria por defecto.

    La pregunta final se la hace a un `Config`, igual que
    `ui/params_panel.py::_missing_keys`: una clave con default fijo
    (`SERVER_DIR='server'`) o dinamico (`VPS_USER` -> nombre del repo) se
    resuelve sola al correr, y mirando el texto crudo del campo el ▶ la
    marcaba como faltante mientras el panel la daba por buena.
    """
    active = params_store.stored_steps(repo_path, capability.id)
    # Los pasos que este repo no tiene (las migraciones de un repo sin Alembic)
    # tampoco reclaman claves: no se dibujan ni corren.
    capability = for_project(capability, repo_path)
    needed = set(required_keys_for(capability.id))
    state = params_store.load(repo_path, capability.id) or {}
    for axis in capability.axes:
        if axis.requires_env:
            needed |= axis.keys_for(_chosen(axis, state))
    for step in registry.resolve_steps(capability):
        if active is not None and step.optional and step.id not in active:
            continue
        needed |= step.requires_env
        needed |= set(required_keys_for(step.id))
    config = envfile.Config(env, repo_name=envfile.repo_name_of(repo_path))
    return [k for k in needed if not config.get(k)]


def _chosen(axis, state: dict) -> list[str]:
    """Los valores del eje que correrian: los guardados o, sin nada, los de por defecto."""
    saved = (state.get('variants' if axis.is_multi else 'options') or {}).get(axis.name)
    if saved is not None:
        return list(saved) if isinstance(saved, list) else [saved]
    if axis.is_multi:
        return [v for v in axis.values if axis.starts_checked(v)]
    return [axis.initial]


def ready_ids(project) -> set[str]:
    """Ids de las acciones que pueden correr ya sobre `project`, con su
    `.consola/config.env` guardado y sus parametros guardados.

    La muestra el ▶ de cada fila del buscador de la barra de menu.

    Sin repo abierto no hay nada listo, ni siquiera las acciones que no piden
    ninguna clave: no hay sobre que correrlas. Contarlas dejaba el menu con 22
    acciones marcadas como listas mientras sus menus estaban deshabilitados.
    """
    if project is None:
        return set()
    env = envfile.load_config(project.path)
    path = project.path
    # Las 62 capacidades se resuelven contra el MISMO repo, y cada una lo
    # volvia a recorrer entera: `one_scan` reparte un solo recorrido entre
    # todas (`core/targets.py`).
    with targets.one_scan():
        aplicables = applicable_ids(path)
        return {
            cap.id for cap in registry.get_all()
            if cap.id in aplicables and not missing_keys(cap, env, path)
        }
