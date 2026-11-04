"""Deployment group, versions.

Publish, sign and deploy a tag (ADR-0059).

With each tag, the repo's `release.yml` builds the artifact and
publishes it in a GitHub release with its `.sha256`. This machine signs
that `.sha256` with `VPS_KEY_NAME`, outside GitHub, and the VPS installs
it with the `deploy.py` that `install.py` left, which only accepts what
a key in `allowed_signers` signs (despliegue.md of canone, «Versiones»).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from app.core import canone, process, ssh
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.registry import registry
from app.core.tasks.git import _current_branch, _ensure_git
from app.core.tasks.vps_setup import Access, access

WORKFLOW = "release.yml"
# How often to ask about the `release.yml` run, and how many times to
# ask whether it exists before giving it up.
_POLL = 15
_APPEARS = 12


def _gh() -> list[str]:
    return process.resolve_executable(
        HOST.executable_names("gh"),
        label="GitHub CLI (gh)",
        hint="Instálalo y corre gh auth login.",
    )


def _repo(root: Path) -> tuple[str, str]:
    """Return `owner/repo` on GitHub and canone's `<app>`.

    The repo's name.
    """
    owner, app = canone.origin(root)
    return f"{owner}/{app}", app


def releases(root: Path) -> list[dict[str, Any]]:
    """Return the repo's releases, newest first, with their files."""
    repo, _ = _repo(root)
    return json.loads(
        process.capture(
            [*_gh(), "api", f"repos/{repo}/releases?per_page=30"], cwd=root, timeout=30.0
        )
    )


def _latest(ctx: TaskContext) -> dict[str, Any]:
    """Return the last published release: GitHub's `latest`."""
    repo, _ = _repo(ctx.root)
    try:
        return json.loads(
            ctx.capture([*_gh(), "api", f"repos/{repo}/releases/latest"], timeout=30.0)
        )
    except TaskError as exc:
        raise TaskError(f"{repo} no tiene releases publicados: corre «Publicar versión».") from exc


# --- atomic ---


def _pushed(ctx: TaskContext) -> None:
    """Stop if the tag would not carry something.

    That is, uncommitted changes or unpushed commits: CI builds the
    tag's commit on GitHub, not this folder.
    """
    _ensure_git(ctx)
    branch = _current_branch(ctx)
    dirty = ctx.capture(["git", "status", "--porcelain"])
    if dirty:
        raise TaskError(f"Hay cambios sin commitear, y el tag no los lleva:\n{dirty}")
    ctx.run(["git", "fetch", "origin"], echo=False)
    upstream = ctx.capture(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False
    )
    if not upstream:
        raise TaskError(f"{branch} no tiene rama en origin: empújala primero.")
    if ctx.capture(["git", "rev-list", "--count", f"{upstream}..HEAD"]) != "0":
        raise TaskError(f"{branch} tiene commits que {upstream} no tiene: empújalos primero.")


def _run_id(ctx: TaskContext, gh: list[str], repo: str, tag: str) -> str:
    """Return the `release.yml` run the tag fired.

    GitHub creates it a few seconds later.
    """
    for _ in range(_APPEARS):
        run = ctx.capture(
            [
                *gh,
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                WORKFLOW,
                "--branch",
                tag,
                "--json",
                "databaseId",
                "--jq",
                ".[0].databaseId",
            ],
            timeout=30.0,
        )
        if run:
            return run
        ctx.wait_cancelled(5)
        ctx.raise_if_cancelled()
    raise TaskError(
        f"GitHub no creó la corrida de {WORKFLOW} para {tag}: ¿tiene el repo "
        f".github/workflows/{WORKFLOW}?"
    )


def _watch(ctx: TaskContext, repo: str, tag: str) -> None:
    """Wait for `release.yml`, and stop if it does not end well."""
    gh = _gh()
    run = _run_id(ctx, gh, repo, tag)
    ctx.info(f"{WORKFLOW} corre en https://github.com/{repo}/actions/runs/{run}")
    seen = ""
    while True:
        state = json.loads(
            ctx.capture(
                [*gh, "run", "view", run, "--repo", repo, "--json", "status,conclusion"],
                timeout=30.0,
            )
        )
        if state["status"] != seen:
            seen = state["status"]
            ctx.info(f"{WORKFLOW}: {seen}")
        if seen == "completed":
            break
        ctx.wait_cancelled(_POLL)
        ctx.raise_if_cancelled()
    if state["conclusion"] != "success":
        ctx.run([*gh, "run", "view", run, "--repo", repo, "--log-failed"], check=False)
        raise TaskError(f"{WORKFLOW} terminó en {state['conclusion']}: {tag} no se publicó.")


def create_tag(ctx: TaskContext, part: str = "patch") -> str:
    """Create the tag after origin's last, push it and wait for CI.

    The number comes from origin's tags and not the local ones: an
    unpushed tag does not move the version forward.
    """
    _pushed(ctx)
    repo, _ = _repo(ctx.root)
    remote = ctx.capture(["git", "ls-remote", "--tags", "--refs", "origin", "v*"])
    tags = [line.rpartition("refs/tags/")[2] for line in remote.splitlines()]
    tag = canone.next_tag(tags, part)
    ctx.run(["git", "tag", "-a", tag, "-m", tag])
    ctx.run(["git", "push", "origin", f"refs/tags/{tag}"])
    _watch(ctx, repo, tag)
    ctx.ok(f"{tag} publicado.")
    return tag


def sign_release(ctx: TaskContext, tag: str) -> None:
    """Sign the release's `.sha256` with `VPS_KEY_NAME`.

    Upload the signature.

    `-n deploy` is the namespace `deploy.py` checks: it separates this
    signature from any other use of the key. A release that has its
    signature is not signed again.
    """
    repo, app = _repo(ctx.root)
    gh = _gh()
    key = ssh.resolve_identity(ctx.config.require("VPS_KEY_NAME"))
    release = json.loads(
        ctx.capture(
            [*gh, "release", "view", tag, "--repo", repo, "--json", "isDraft,assets"], timeout=30.0
        )
    )
    names = {a["name"] for a in release["assets"]}
    total, signature = canone.checksum(app, tag), canone.signature(app, tag)
    if signature in names:
        ctx.ok(f"{tag} ya tiene {signature}.")
        return
    if release["isDraft"] or total not in names:
        raise TaskError(f"El release {tag} no tiene {total}: {WORKFLOW} no terminó.")
    with tempfile.TemporaryDirectory() as folder:
        ctx.run(
            [*gh, "release", "download", tag, "--repo", repo, "--pattern", total, "--dir", folder]
        )
        ctx.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-n",
                "deploy",
                "-f",
                str(key),
                str(Path(folder) / total),
            ]
        )
        ctx.run([*gh, "release", "upload", tag, str(Path(folder) / signature), "--repo", repo])
    ctx.ok(f"{tag} firmado.")


def deploy_release(ctx: TaskContext, tag: str) -> None:
    """Run `deploy.py` on the VPS with the tag, from the admin account.

    `deploy.py` downloads the release, checks the signature, migrates,
    switches `current` and waits for health to answer; if it does not
    answer, it goes back to the previous version when there were no
    migrations.
    """
    _, app = _repo(ctx.root)
    _deploy(ctx, _admin(ctx), app, tag)


def _admin(ctx: TaskContext) -> Access:
    entry = access(ctx)
    if entry.is_root:
        raise TaskError(
            "La cuenta que administra todavía no existe: corre «Configurar VPS» "
            "con «Instalar infraestructura» primero."
        )
    return entry


def _deploy(ctx: TaskContext, entry: Access, app: str, tag: str) -> None:
    entry.run(ctx, canone.deploy_command(app, tag))
    ctx.ok(f"{tag} desplegado en {entry.remote.host}.")


def deploy_latest(ctx: TaskContext) -> str:
    """Deploy the last published release, if signed.

    It is the first deployment of «Configurar VPS». If `current` is
    already that release it does nothing, so the composite can run
    again: `deploy.py` does not install the same version twice.
    """
    _, app = _repo(ctx.root)
    last = _latest(ctx)
    tag = last["tag_name"]
    if not canone.signed(app, [last]):
        raise TaskError(
            f"El último release, {tag}, no tiene {canone.signature(app, tag)}: "
            "fírmalo con «Publicar versión» sin «Crear tag»."
        )
    entry = _admin(ctx)
    current = ssh.capture(
        entry.remote, f"readlink {ssh.quote(f'/srv/{app}/current')}", check=False
    )
    if current.rpartition("/")[2] == tag:
        ctx.ok(f"{tag} ya está desplegado.")
        return tag
    _deploy(ctx, entry, app, tag)
    return tag


# --- buttons ---


def publish_release(
    ctx: TaskContext,
    part: str = "patch",
    *,
    tag: bool = True,
    sign: bool = True,
    deploy: bool = True,
) -> str:
    """Tag, `release.yml`, signature, then `deploy.py`.

    Without «Crear tag», it signs and deploys the last published
    release: that resumes a publication cut after CI.
    """
    if tag:
        ctx.step("tag")
        version = create_tag(ctx, part)
    else:
        version = _latest(ctx)["tag_name"]
    if sign:
        ctx.step("sign")
        sign_release(ctx, version)
    if deploy:
        ctx.step("deploy")
        deploy_release(ctx, version)
    ctx.note(f"{version} publicado.")
    return version


def deploy_version(ctx: TaskContext, version: str = "") -> None:
    """Install a signed release.

    `deploy.py` does not install a version that remains in
    `/srv/<app>/releases/`, where the newest five stay.
    """
    if not version:
        raise TaskError("Elige la versión que se despliega.")
    deploy_release(ctx, version)


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("publish_release", publish_release)
    registry.bind("deploy_version", deploy_version)
