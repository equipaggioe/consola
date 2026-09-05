from __future__ import annotations

from core.registry import registry
from core.settings import required_keys_for
from core import envfile
from ui import params_store


def missing_keys(capability, env: dict[str, str], repo_path: str) -> list[str]:
    """Que le falta a una accion para poder correr sin abrir la pestana.

    Correr de una (el boton ▶ del rail, Ctrl+clic en el menu) usa los
    parametros guardados para ese boton en ese repo, asi que se mira
    exactamente lo que esos parametros van a correr: los pasos apagados no
    pueden reclamar claves. Sin nada guardado se cuentan todos los pasos, que
    es lo que correria por defecto.

    La pregunta final se la hace a un `Config`, igual que
    `ui/params_panel.py::_missing_keys`: una clave con default fijo
    (`SERVER_DIR='server'`) o dinamico (`VPS_USER` -> nombre del repo) se
    resuelve sola al correr, y mirando el texto crudo del campo el rail la
    marcaba como faltante mientras el panel la daba por buena.
    """
    active = params_store.stored_steps(repo_path, capability.id)
    needed = set(required_keys_for(capability.id))
    for step in registry.resolve_steps(capability):
        if active is not None and step.optional and step.id not in active:
            continue
        needed |= step.requires_env
        needed |= set(required_keys_for(step.id))
    config = envfile.Config(env, repo_name=envfile.repo_name_of(repo_path))
    return [k for k in needed if not config.get(k)]


def ready_ids(project) -> set[str]:
    """Ids de las acciones que pueden correr ya sobre `project`, con su
    `.consola/config.env` guardado y sus parametros guardados.

    Una sola cuenta para los dos sitios que la muestran — el ▶ de cada fila
    del rail y el marcador del menu — para que no puedan discrepar.

    Sin repo abierto no hay nada listo, ni siquiera las acciones que no piden
    ninguna clave: no hay sobre que correrlas. Contarlas dejaba el menu con 22
    acciones marcadas como listas mientras sus menus estaban deshabilitados.
    """
    if project is None:
        return set()
    env = envfile.load_config(project.path)
    path = project.path
    return {
        cap.id for cap in registry.get_all()
        if not missing_keys(cap, env, path)
    }
