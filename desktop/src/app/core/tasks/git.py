"""Git group.

The two forced operations below exist for when someone already decided
that this machine wins against origin, or origin against this machine,
even if the other side has commits the winner does not know. They run
only on this machine: the VPS has no clone of the repo (ADR-0059).

`clone_repo` belongs here for the same reason: it is git against GitHub
and nothing else. It is the only one in the module that does not work on
the open repo.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.process import which_any
from app.core.registry import registry


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
    """Force origin to match this machine's branch.

    `--force` and not `--force-with-lease`: the lease rejects the push
    when origin has commits this machine did not see, which is the case
    this button exists for.
    """
    _ensure_git(ctx)
    branch = _current_branch(ctx)
    ctx.run(["git", "fetch", "--quiet"], check=False, echo=False)
    ctx.run(["git", "push", "--force", "origin", branch])
    revision = ctx.capture(["git", "rev-parse", "--short", "HEAD"])
    ctx.ok(f"origin/{branch} ahora es {revision}, igual que esta maquina.")
    return revision


def force_reset(ctx: TaskContext, discard_changes: bool = False) -> str:
    """Force this machine to match origin, discarding its own work.

    It drops the commits origin lacks and whatever is untracked (`git
    clean -fd`). `discard_changes` chooses what to do with uncommitted
    changes: False asks with the file list in view, True discards them
    without asking.
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
    """Return the folder name git would give the clone.

    It follows `git clone` without a target: the URL's last segment
    without `.git`. It works alike for SSH
    (`git@github.com:user/repo.git`) and HTTPS, since both end in
    `/repo.git` or `:user/repo.git`. This machine's separator cuts too:
    git also clones from a local folder, where the last segment comes
    after a backslash.
    """
    clean = url.strip().rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    name = clean.rsplit("/", 1)[-1].rsplit(os.sep, 1)[-1].rsplit(":", 1)[-1]
    if not name:
        raise TaskError(f"No se entiende que repositorio clonar de: {url}")
    return name


def clone_repo(ctx: TaskContext, url: str = "", dest: str = "", branch: str = "") -> Path:
    """Clone a GitHub repository and return the folder it landed in.

    Returning the path is not cosmetic: the window opens it as a tab
    when the capability declares `opens_repo` (`core/registry.py`). The
    task knows nothing of tabs: it says where it left the repo, and that
    is enough.

    Without a target folder it clones next to the open repo: that is
    where the others live, and it is the only default that need not be
    invented. It never writes over an existing folder: that would not be
    cloning but mixing two repos.
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
    """Register the group's functions in the catalog."""
    registry.bind("git_force_push", force_push)
    registry.bind("git_force_reset", force_reset)
    registry.bind("clone_repo", clone_repo)
