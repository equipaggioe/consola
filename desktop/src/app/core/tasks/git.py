from __future__ import annotations

import os
from pathlib import Path

from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.process import which_any
from app.core.registry import registry

"""
Grupo Git.

Los dos forzados de aca abajo existen para el caso en que alguien ya decidio
que esta maquina gana contra origin, o que origin gana contra esta maquina,
aunque el otro lado tenga commits que el ganador no conoce. Corren solo en esta
maquina: el VPS no tiene clon del repo (ADR-0059).

`clone_repo` es del mismo grupo por la misma razon: es git contra GitHub y
nada mas. Es la unica del modulo que no trabaja sobre el repo abierto.
"""


def _git_or_fail() -> None:
    if not which_any(["git", "git.exe"]):
        raise TaskError("No se encontro Git en el PATH.")


def _ensure_git(ctx: TaskContext) -> None:
    _git_or_fail()
    if not ctx.path(".git").exists():
        raise TaskError(f"La carpeta abierta no es un repositorio git: {ctx.root}")


def _current_branch(ctx: TaskContext) -> str:
    branch = ctx.capture(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch == "HEAD":
        raise TaskError("El repo local esta en HEAD desacoplado: no hay rama que forzar.")
    return branch


def force_push(ctx: TaskContext) -> str:
    """Fuerza a que origin quede igual a la rama de esta maquina.

    `--force` y no `--force-with-lease`: la lease rechaza el push justo cuando
    origin tiene commits que esta maquina no vio, que es exactamente el caso para
    el que existe este boton.
    """
    _ensure_git(ctx)
    branch = _current_branch(ctx)
    ctx.run(["git", "fetch", "--quiet"], check=False, echo=False)
    ctx.run(["git", "push", "--force", "origin", branch])
    revision = ctx.capture(["git", "rev-parse", "--short", "HEAD"])
    ctx.ok(f"origin/{branch} ahora es {revision}, igual que esta maquina.")
    return revision


def force_reset(ctx: TaskContext, discard_changes: bool = False) -> str:
    """Fuerza a que esta maquina quede igual a origin, descartando lo propio.

    Tira los commits que origin no tiene y lo que haya sin trackear
    (`git clean -fd`). `discard_changes` elige que hacer si hay cambios sin
    commitear: False pregunta con la lista de archivos a la vista, True los
    descarta sin preguntar.
    """
    _ensure_git(ctx)
    branch = _current_branch(ctx)
    dirty = ctx.capture(["git", "status", "--porcelain"])
    if dirty and not discard_changes:
        ctx.warn("Esta maquina tiene cambios sin commitear:\n" + dirty)
        if not ctx.confirm("Descartar esos cambios y resetear igual?", danger=True):
            raise TaskError("Reset cancelado: hay cambios sin commitear.")
    ctx.run(["git", "fetch", "origin", branch])
    ctx.run(["git", "reset", "--hard", f"origin/{branch}"])
    ctx.run(["git", "clean", "-fd"])
    revision = ctx.capture(["git", "rev-parse", "--short", "HEAD"])
    ctx.ok(f"{branch} ahora es {revision}, igual que origin.")
    return revision


def repo_folder_name(url: str) -> str:
    """El nombre de carpeta que git le pondria al clon.

    Mismo criterio que `git clone` sin destino: el ultimo tramo de la URL sin
    `.git`. Vale igual para SSH (`git@github.com:usuario/repo.git`) que para
    HTTPS, porque los dos terminan en `/repo.git` o en `:usuario/repo.git`.
    El separador de esta maquina tambien corta: git clona igual desde una
    carpeta local, y ahi el ultimo tramo viene detras de una barra invertida.
    """
    clean = url.strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    name = clean.rsplit("/", 1)[-1].rsplit(os.sep, 1)[-1].rsplit(":", 1)[-1]
    if not name:
        raise TaskError(f"No se entiende que repositorio clonar de: {url}")
    return name


def clone_repo(ctx: TaskContext, url: str = "", dest: str = "", branch: str = "") -> Path:
    """Clona un repositorio de GitHub y devuelve la carpeta donde quedo.

    Devolver la ruta no es cosmetico: es lo que la ventana abre como pestana
    cuando la capacidad declara `opens_repo` (`core/registry.py`). La tarea no
    sabe nada de pestanas — dice donde dejo el repo, y eso alcanza.

    Sin carpeta destino se clona al lado del repo abierto: es donde viven los
    demas, y es el unico default que no hay que inventar. Nunca escribe sobre
    una carpeta que ya existe: eso no seria clonar sino mezclar dos repos.
    """
    if not url.strip():
        raise TaskError("Falta la URL del repositorio a clonar.")
    _git_or_fail()

    if dest.strip():
        folder = Path(dest.strip()).expanduser()
    elif ctx.project is not None:
        folder = ctx.root.parent
    else:
        raise TaskError("Indica la carpeta destino: no hay ningun repo abierto del que deducirla.")

    destination = folder / repo_folder_name(url)
    if destination.exists():
        raise TaskError(f"Ya existe {destination}. Elige otra carpeta destino o borra esa.")
    folder.mkdir(parents=True, exist_ok=True)

    argv = ["git", "clone"]
    if branch.strip():
        argv += ["--branch", branch.strip()]
    argv += [url.strip(), str(destination)]
    ctx.run(argv, cwd=str(folder))
    revision = ctx.capture(["git", "rev-parse", "--short", "HEAD"], cwd=str(destination))
    ctx.ok(f"{destination.name} clonado en {destination} ({revision}).")
    return destination


def bind_all() -> None:
    registry.bind("git_force_push", force_push)
    registry.bind("git_force_reset", force_reset)
    registry.bind("clone_repo", clone_repo)
