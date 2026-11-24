"""Deployment group: publish, sign and deploy a tag (ADR-0059).

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

from PySide6.QtCore import QCoreApplication

from app.services import canone, process, ssh
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.host import HOST
from app.services.registry import registry
from app.services.settings import names
from app.services.tasks.git import _current_branch, _ensure_git
from app.services.tasks.vps_setup import Access, admin

WORKFLOW = "release.yml"
WORKFLOW_PATH = f".github/workflows/{WORKFLOW}"
# How often to ask about the `release.yml` run, and how many times to
# ask whether it exists before giving it up.
_POLL = 15
_APPEARS = 12


def _gh() -> list[str]:
    return process.resolve_executable(
        HOST.executable_names("gh"),
        label=QCoreApplication.translate("vps_release", "GitHub CLI (gh)"),
        hint=QCoreApplication.translate("vps_release", "Instálalo y corre gh auth login."),
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
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "{0} no tiene releases publicados: corre «Publicar versión»."
            ).format(repo)
        ) from exc


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
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "Hay cambios sin commitear, y el tag no los lleva:\n{0}"
            ).format(dirty)
        )
    ctx.run(["git", "fetch", "origin"], echo=False)
    upstream = ctx.capture(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], check=False
    )
    if not upstream:
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "{0} no tiene rama en origin: empújala primero."
            ).format(branch)
        )
    if ctx.capture(["git", "rev-list", "--count", f"{upstream}..HEAD"]) != "0":
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "{0} tiene commits que {1} no tiene: empújalos primero."
            ).format(branch, upstream)
        )


def release_run(answer: dict[str, Any], sha: str) -> str:
    """Return the id of the `release.yml` run, or "" if it is not there.

    `answer` is `GET /repos/{repo}/actions/runs`, newest first. The run
    is found by the path of its workflow: `gh run list --workflow` finds
    the file only on the default branch, and a repo can bring
    `release.yml` in the branch it tags. It also has to be of `sha`, the
    tag's commit: a tag deleted and created again keeps the runs of the
    old one under the same name, and before GitHub creates the new run
    the old one would pass for it.
    """
    for run in answer["workflow_runs"]:
        if run["path"] == WORKFLOW_PATH and run["head_sha"] == sha:
            return str(run["id"])
    return ""


def _run_id(ctx: TaskContext, gh: list[str], repo: str, tag: str) -> str:
    """Return the `release.yml` run the tag fired.

    GitHub creates it a few seconds later.
    """
    sha = ctx.capture(["git", "rev-parse", f"{tag}^{{commit}}"]).strip()
    for _ in range(_APPEARS):
        answer = ctx.capture(
            [*gh, "api", f"repos/{repo}/actions/runs?branch={tag}&event=push&head_sha={sha}"],
            timeout=30.0,
        )
        run = release_run(json.loads(answer), sha)
        if run:
            return run
        ctx.wait_cancelled(5)
        ctx.raise_if_cancelled()
    raise TaskError(
        QCoreApplication.translate(
            "vps_release", "GitHub no creó la corrida de {0} para {1}: ¿tiene el repo {2}?"
        ).format(WORKFLOW, tag, WORKFLOW_PATH)
    )


def _watch(ctx: TaskContext, repo: str, tag: str) -> None:
    """Wait for `release.yml`, and stop if it does not end well."""
    gh = _gh()
    run = _run_id(ctx, gh, repo, tag)
    ctx.info(
        QCoreApplication.translate(
            "vps_release", "{0} corre en https://github.com/{1}/actions/runs/{2}"
        ).format(WORKFLOW, repo, run)
    )
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
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "{0} terminó en {1}: {2} no se publicó."
            ).format(WORKFLOW, state["conclusion"], tag)
        )


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
    ctx.ok(QCoreApplication.translate("vps_release", "{0} publicado.").format(tag))
    return tag


def sign_release(ctx: TaskContext, tag: str) -> None:
    """Sign the `.sha256` with `VPS_KEY_NAME` and upload the signature.

    `-n deploy` is the namespace `deploy.py` checks: it separates this
    signature from any other use of the key. A release whose signature
    is `VPS_KEY_NAME`'s is not signed again; one signed with another
    key is signed again and its signature replaced, since the VPS only
    accepts the keys `install.py` received.
    """
    repo, app = _repo(ctx.root)
    gh = _gh()
    key = ssh.resolve_identity(ctx.config.require("VPS_KEY_NAME"))
    release = json.loads(
        ctx.capture(
            [*gh, "release", "view", tag, "--repo", repo, "--json", "isDraft,assets"], timeout=30.0
        )
    )
    assets = {a["name"] for a in release["assets"]}
    total, signature = canone.checksum(app, tag), canone.signature(app, tag)
    if signature in assets:
        if _signer(ctx, repo, tag, signature) in canone.public_keys(ssh.public_key(key)):
            ctx.ok(
                QCoreApplication.translate("vps_release", "{0} ya tiene {1}.").format(
                    tag, signature
                )
            )
            return
        ctx.warn(
            QCoreApplication.translate(
                "vps_release", "{0} está firmado con una llave distinta de {1}: se firma de nuevo."
            ).format(signature, names(["VPS_KEY_NAME"]))
        )
    if release["isDraft"] or total not in assets:
        raise TaskError(
            QCoreApplication.translate(
                "vps_release", "El release {0} no tiene {1}: {2} no terminó."
            ).format(tag, total, WORKFLOW)
        )
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
        ctx.run(
            [
                *gh,
                "release",
                "upload",
                tag,
                str(Path(folder) / signature),
                "--repo",
                repo,
                "--clobber",
            ]
        )
    ctx.ok(QCoreApplication.translate("vps_release", "{0} firmado.").format(tag))


def _signer(ctx: TaskContext, repo: str, tag: str, signature: str) -> str:
    """Return the key that signed the release, as `type base64`."""
    with tempfile.TemporaryDirectory() as folder:
        ctx.run(
            [*_gh(), "release", "download", tag, "--repo", repo]
            + ["--pattern", signature, "--dir", folder]
        )
        return canone.signer((Path(folder) / signature).read_text(encoding="ascii"))


def _check_signer(ctx: TaskContext, entry: Access, tag: str) -> None:
    """Stop unless the VPS accepts the key that signed the release.

    `deploy.py` checks the same, but only says «No principal matched».
    The way out depends on the key: `VPS_KEY_NAME`'s is added to the VPS
    by `install.py`; another one is replaced by signing again.
    """
    repo, app = _repo(ctx.root)
    key = _signer(ctx, repo, tag, canone.signature(app, tag))
    accepted = canone.public_keys(
        ssh.capture(entry.remote, f"cat {ssh.quote(canone.signers(app))}")
    )
    if key in accepted:
        return
    own = ssh.public_key(ssh.resolve_identity(ctx.config.require("VPS_KEY_NAME")))
    if key in canone.public_keys(own):
        raise TaskError(
            QCoreApplication.translate(
                "vps_release",
                "{0} está firmado con {1}, que {2} no tiene en {3}: agrégala con "
                "«Instalar infraestructura» de «Configurar VPS».",
            ).format(tag, names(["VPS_KEY_NAME"]), entry.remote.host, canone.signers(app))
        )
    raise TaskError(
        QCoreApplication.translate(
            "vps_release",
            "{0} está firmado con una llave distinta de {1}, que {2} no tiene en {3}: fírmalo de "
            "nuevo con «Publicar versión» sin «Crear tag».",
        ).format(tag, names(["VPS_KEY_NAME"]), entry.remote.host, canone.signers(app))
    )


def deploy_release(ctx: TaskContext, tag: str) -> None:
    """Run `deploy.py` on the VPS with the tag, from the admin account.

    `deploy.py` downloads the release, checks the signature, migrates,
    switches `current` and waits for health to answer; if it does not
    answer, it goes back to the previous version when there were no
    migrations.
    """
    _, app = _repo(ctx.root)
    _deploy(ctx, admin(ctx), app, tag)


def _deploy(ctx: TaskContext, entry: Access, app: str, tag: str) -> None:
    _check_signer(ctx, entry, tag)
    entry.run(ctx, canone.deploy_command(app, tag))
    ctx.ok(
        QCoreApplication.translate("vps_release", "{0} desplegado en {1}.").format(
            tag, entry.remote.host
        )
    )


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
            QCoreApplication.translate(
                "vps_release",
                "El último release, {0}, no tiene {1}: fírmalo con «Publicar versión» "
                "sin «Crear tag».",
            ).format(tag, canone.signature(app, tag))
        )
    entry = admin(ctx)
    current = ssh.capture(
        entry.remote, f"readlink {ssh.quote(f'/srv/{app}/current')}", check=False
    )
    if current.rpartition("/")[2] == tag:
        ctx.ok(QCoreApplication.translate("vps_release", "{0} ya está desplegado.").format(tag))
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
    ctx.note(QCoreApplication.translate("vps_release", "{0} publicado.").format(version))
    return version


def deploy_version(ctx: TaskContext, version: str = "") -> None:
    """Install a signed release.

    `deploy.py` does not install a version that remains in
    `/srv/<app>/releases/`, where the newest five stay.
    """
    if not version:
        raise TaskError(
            QCoreApplication.translate("vps_release", "Elige la versión que se despliega.")
        )
    deploy_release(ctx, version)


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("publish_release", publish_release)
    registry.bind("deploy_version", deploy_version)
