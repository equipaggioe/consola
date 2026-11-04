"""Build group.

The version bump is one atomic capability for the three manifests
(`pubspec.yaml`, `package.json`, `pyproject.toml`), the upload is
another, and all that is each builder's own is the compile step. Only
the executable still bumps the version and publishes on the VPS: the
mobile app and the SPAs compile and nothing else (ADR-0059).
"""

from __future__ import annotations

import json
import platform
import re
import shutil
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from app.core import canone, files, icons, ssh, targets, toolchain, versioning, vps
from app.core.context import TaskContext
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.registry import registry
from app.core.tasks import raster


def _target(ctx: TaskContext, kind: str, name: str = "") -> targets.Target:
    return targets.pick(ctx.root, (kind,), name)


def _mobile(ctx: TaskContext, name: str = "") -> targets.Target:
    """Return the repo's mobile app, whether Flutter or Flet.

    Both types are looked for together because the framework is not a
    choice of whoever presses the button: it is a property of the
    folder, and `compile_flutter` reads it by itself.
    """
    return targets.pick(ctx.root, targets.MOBILE_APP, name)


# --- cross-cutting atomic ---


def bump_version(ctx: TaskContext, directory: str = "", mode: str = "patch") -> tuple[str, str]:
    """Bump the version in the manifest, of any of the three types.

    It has its own button because bumping the version without compiling
    yet is a real operation: it happens on closing a change, before
    deciding whether to publish.
    """
    folder = ctx.path(directory) if directory else ctx.root
    manifest = versioning.find_manifest(folder)
    previous = versioning.read_version(manifest)
    new = versioning.bump(previous, mode)
    versioning.write_version(manifest, new)
    ctx.ok(f"{manifest.name}: {previous} -> {new}")
    return previous, new


def upload_artifact(
    ctx: TaskContext, local: Path, remote_rel: str = "", *, chmod: str = ""
) -> str:
    """Upload an artifact to the VPS, keeping its repo-relative path.

    Its own button: re-uploading a compiled APK after a network cut
    should not force recompiling it.

    `chmod` is for what executes on the other side: `scp` does not keep
    the execute bit, so a binary uploaded without this arrives useless.
    Other artifacts (an APK, an SPA's folder) are served, not executed,
    and do not need it.
    """
    if not local.exists():
        raise TaskError(f"No existe el artefacto: {local}")
    rel = remote_rel or local.relative_to(ctx.root).as_posix()
    remote = ssh.resolve_remote(ctx.config)
    destination = ssh.upload(ctx, remote, local, vps.remote_path(ctx.config, rel), chmod=chmod)
    ctx.ok(f"Subido: {destination}")
    return destination


# --- Flutter and Flet steps ---


def compile_flutter(ctx: TaskContext, directory: str = "", platform_id: str = "apk") -> Path:
    """Compile the app for one platform.

    It is the only step that changes between Flutter and Flet, and
    between platforms.

    The API's URL enters through `--dart-define` from the configuration:
    the same source the debug launcher uses, so release and debug do not
    point to different servers by accident. Flet has no `--dart-define`
    of its own: it passes it to its underlying `flutter build` with
    `--flutter-build-args`.

    On web the app goes at its host's root, Flutter's default: each
    piece has its own (ADR-0065).

    There is no offline: the service worker Flutter generates
    unregisters itself (its `--pwa-strategy` is deprecated and caches
    nothing), so the app installs through its `manifest.json` but only
    works online.
    """
    app = _mobile(ctx, directory)
    kind = toolchain.detect_app_kind(app.path)
    destination = toolchain.BUILD_PLATFORMS[platform_id]
    api = ctx.config.require("API_URL")
    define = f"--dart-define=API_BASE_URL={api}"

    if kind == toolchain.FLUTTER:
        ctx.run(
            [*toolchain.flutter_cmd(), "build", destination.flutter, "--release", define],
            cwd=app.path,
        )
    else:
        # The environment variable stays for the Python code that reads
        # it when packaging.
        ctx.run(
            [*toolchain.flet_cmd(), "build", destination.flet, f"--flutter-build-args={define}"],
            cwd=app.path,
            env={"API_BASE_URL": api},
        )

    pattern = destination.output(kind)
    output = _newest(app.path, pattern)
    if output is None:
        raise TaskError(
            f"El build {destination.label} termino pero no aparecio nada en {pattern}."
        )
    output = _deliver(ctx, app.path, platform_id, output)
    ctx.ok(f"{destination.label}: {output} ({files.human_size(files.size_of(output))})")
    return output


def _newest(base: Path, pattern: str) -> Path | None:
    found = list(base.glob(pattern))
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def _out_dir(ctx: TaskContext, app_dir: Path, platform_id: str) -> Path | None:
    """Return the `config.env` folder for the build, if any.

    Empty, the build stays where the framework leaves it. It is relative
    to the app's folder, like the default paths the field shows.
    """
    value = ctx.config.get(toolchain.out_key(platform_id))
    return app_dir / value if value else None


def _deliver(ctx: TaskContext, app_dir: Path, platform_id: str, output: Path) -> Path:
    """Copy the build to the configured folder, if any.

    It copies and does not ask the framework to compile there: Flutter
    only accepts `--output` on web, and this way all seven platforms
    work the same on both frameworks. An APK or IPA lands *inside* the
    folder; a web or desktop build, already a folder, *becomes* it.
    """
    folder = _out_dir(ctx, app_dir, platform_id)
    if folder is None:
        return output
    destination = folder / output.name if toolchain.BUILD_PLATFORMS[platform_id].suffix else folder
    files.copy(output, destination)
    return destination


# --- release manifest ---
#
# Which version is published is a fact of the artifact, not server
# configuration. The builder writes it, the only one who knows the
# version at the exact moment it stops being an intention.
#
# It is the usual convention for updates: Sparkle's appcast,
# electron-updater's `latest.yml`, Tauri's `latest.json`. Flutter itself
# emits `build/web/version.json`, which is this for one platform.
#
# It is no new source of truth: it derives from the subproject's
# manifest when publishing, so nothing has to stay in sync by hand.

RELEASES_DIR = "releases"


def _release_manifest(
    ctx: TaskContext, app: str, platform_id: str, artifact: Path, manifest: Path
) -> Path:
    """Write `releases/<app>/<platform>.json`: what is published.

    `sha256` goes only when the artifact is a file: a web build is a
    tree, and a hash per file is not what anyone will verify. Without
    it, the rest of the manifest still serves.
    """
    version = versioning.read_version(manifest)
    data: dict[str, str | int] = {
        "app": app,
        "platform": platform_id,
        "version": version.split("+", 1)[0],
    }
    if "+" in version:
        data["build"] = int(version.split("+", 1)[1])
    data["artifact"] = artifact.name
    if artifact.is_file():
        data["sha256"] = files.digest(artifact)
    data["published_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    destination = ctx.root / RELEASES_DIR / app / f"{platform_id}.json"
    files.write_text(destination, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    ctx.ok(f"Release {app}/{platform_id}: {data['version']}")
    return destination


def _publish_release(
    ctx: TaskContext, app: str, platform_id: str, artifact: Path, manifest: Path
) -> None:
    """Write the release manifest and upload it with the artifact."""
    upload_artifact(ctx, _release_manifest(ctx, app, platform_id, artifact, manifest))


# --- Vite steps ---


def install_node_modules(ctx: TaskContext, directory: str = "") -> None:
    """Run `pnpm install`, as canone's sveltekit.md asks (ADR-0072)."""
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.pnpm_cmd(), "install"], cwd=spa.path)


def compile_spa(ctx: TaskContext, directory: str = "") -> Path:
    """Run `pnpm run build`.

    The SPA goes at its host's root, so Consola leaves nothing inside:
    the build is the repo's as is (ADR-0065).
    """
    spa = _target(ctx, targets.SPA_VITE, directory)
    ctx.run([*toolchain.pnpm_cmd(), "run", "build"], cwd=spa.path)
    output = _spa_output(spa)
    ctx.ok(f"Build de {spa.name}: {output} ({files.human_size(files.size_of(output))})")
    return output


def _spa_output(spa: targets.Target) -> Path:
    """Return the folder the build left.

    That is `dist/` in bare Vite and `build/` in SvelteKit's adapters.
    It looks at the disk and not `vite.config.*` because the output may
    be declared by a plugin.
    """
    for candidate in ("dist", "build"):
        output = spa.path / candidate
        if output.is_dir():
            return output
    raise TaskError(f"{spa.name} no tiene carpeta dist/ ni build/.")


# `sv create` lays out the skeleton, with TypeScript, Prettier, ESLint
# and adapter-static. Then the template of canone goes on top, plus the
# `ssr = false` of a static SPA (ADR-0072).
_SV = "sv@1.2.0"
_SPA_TEMPLATE = (".gitignore", ".prettierrc", "uno.config.ts", "vite.config.ts")
_SPA_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")

_SPA_FILES = {
    "src/routes/+layout.ts": """\
export const ssr = false;
""",
    "src/routes/+layout.svelte": """\
<script lang="ts">
	import 'virtual:uno.css';
	import favicon from '#lib/assets/favicon.svg';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}
""",
    "src/routes/+page.svelte": """\
<main class="min-h-screen grid place-items-center">
	<h1 class="text-2xl font-semibold">{NAME}</h1>
</main>
""",
}


def _generate_colors(ctx: TaskContext, template: Path) -> None:
    """Generate the `src/lib/colors.ts` that `uno.config.ts` imports.

    It comes from the repo's tokens.

    A repo without them takes the canone starting point (transversal.md
    of canone, «Tema»).
    """
    generator = ctx.root / "scripts" / "tokens.py"
    if not generator.is_file():
        generator.parent.mkdir(exist_ok=True)
        shutil.copyfile(template / "scripts" / "tokens.py", generator)
    tokens = ctx.root / "brand" / "tokens"
    if not tokens.is_dir():
        shutil.copytree(template / "brand" / "tokens", tokens)
    ctx.run([*toolchain.python_cmd(), str(generator)], cwd=ctx.root)


def create_spa(ctx: TaskContext) -> Path:
    """Create a blank SPA in the repo.

    SvelteKit, TypeScript, runes, UnoCSS.

    It stays ready for the other Vite buttons: `serve_vite` and
    `build_vite` discover it by its `vite.config.ts`.

    The folder's name is asked here and does not come as a parameter: it
    is the run's only datum and differs each time, so it has nowhere to
    be saved (`core/catalog.py`, on registering `create_spa`).
    """
    name = ctx.ask("¿Cómo se va a llamar la carpeta de la SPA?").strip()
    if not name:
        raise TaskError("Cancelado: no se eligio un nombre de carpeta.")
    if not _SPA_NAME.fullmatch(name):
        raise TaskError(
            "El nombre de la carpeta va en minusculas, sin espacios "
            '(letras, numeros, ".", "_" o "-").'
        )
    destination = ctx.path(name)
    if destination.exists():
        raise TaskError(f"Ya existe {destination}.")
    template = canone.spa_template(ctx.config)
    pnpm = toolchain.pnpm_cmd()

    ctx.run(
        [
            *pnpm,
            "dlx",
            _SV,
            "create",
            name,
            "--template",
            "minimal",
            "--types",
            "ts",
            "--add",
            "prettier",
            "eslint",
            "sveltekit-adapter=adapter:static",
            "--install",
            "pnpm",
        ],
        cwd=ctx.root,
    )
    ctx.run([*pnpm, "add", "--save-dev", "unocss"], cwd=destination)
    version = ctx.capture([*pnpm, "--version"])
    ctx.run([*pnpm, "pkg", "set", f"packageManager=pnpm@{version}"], cwd=destination)

    (destination / "prettier.config.js").unlink()
    for file in _SPA_TEMPLATE:
        shutil.copyfile(template / file, destination / file)
    for rel, content in _SPA_FILES.items():
        (destination / rel).write_text(
            content.replace("{NAME}", name), encoding="utf-8", newline="\n"
        )
    ctx.run([*pnpm, "exec", "prettier", "--write", "."], cwd=destination)
    _generate_colors(ctx, template.parent)

    ctx.ok(f"SPA creada en {destination}")
    ctx.note(f"Nueva SPA {name}")
    return destination


# --- binary steps ---

# Entrypoints tried when the field stays empty, in order. `src/main.py`
# goes first because the App Python launcher already prefers it
# (`core/targets.py::python_entrypoint`): the executable to download is
# the same app launched in development, and asking for the path would be
# asking to confirm what the folder already answers.
_ENTRYPOINTS = ("src/main.py", "main.py", "app/main.py")

# An entrypoint called this does not name the program but the startup
# file: `src/main.py` would give an executable called «main». Then the
# name comes from the app's folder, the project's name.
_GENERIC_NAMES = ("main", "__main__", "app", "cli", "run")


def resolve_entrypoint(ctx: TaskContext, entrypoint: str = "") -> Path:
    """Return the Python file PyInstaller will package.

    Written by hand it always wins: any path of the repo is accepted
    (`server/main.py`, `tools/cli.py`). Empty, it deduces: the repo's
    only `python-app` and its `src/main.py`, and if the repo has none, a
    `main.py` at the root.

    There is no `app` axis with discovered apps, unlike the other two
    builders: an empty discovered axis blocks the button in amber, and a
    repo that packages from its root has no `python-app` to discover, so
    it could not compile its own executable.
    """
    if entrypoint:
        source = ctx.path(entrypoint)
        if not source.is_file():
            raise TaskError(f"No existe el punto de entrada: {source}")
        return source

    apps = targets.by_kind(ctx.root, targets.PYTHON_APP)
    if len(apps) > 1:
        choose = ", ".join(a.name for a in apps)
        raise TaskError(
            f"Hay mas de una app Python en {ctx.root.name}: {choose}. "
            "Escribe el punto de entrada de la que quieras empaquetar."
        )

    base = apps[0].path if apps else ctx.root
    for candidate in _ENTRYPOINTS:
        source = base / candidate
        if source.is_file():
            return source
    raise TaskError(
        f"No se encontro un punto de entrada en {base.name} "
        f"({', '.join(_ENTRYPOINTS)}). Escribe cual es."
    )


def _binary_app(root: Path, source: Path) -> Path:
    """Return the folder of the app the entrypoint belongs to.

    It is where the versioned manifest lives and where PyInstaller
    leaves `dist/` and `build/`. It looks upward from the entrypoint
    until finding a manifest: `entrypoint.parent`, which for
    `src/main.py` is `src/`, would create a `pyproject.toml` parallel to
    the app's, with its own version nobody else read.
    """
    folder = source.parent
    while folder != folder.parent:
        if any((folder / name).is_file() for name in versioning.MANIFEST_NAMES):
            return folder
        if folder == root:
            break
        folder = folder.parent
    return root


def _ensure_manifest(ctx: TaskContext, app_dir: Path) -> Path:
    """Return the app's version manifest, created at 0.0.0 if absent.

    A loose script that starts being distributed need not bring a
    `pyproject.toml` written beforehand, and without a manifest there is
    no version to bump or publish next to the binary.
    """
    try:
        return versioning.find_manifest(app_dir)
    except TaskError:
        pass
    name = re.sub(r"[^0-9A-Za-z._-]+", "-", app_dir.name).strip("-").lower() or "python-app"
    manifest = app_dir / "pyproject.toml"
    files.write_text(manifest, f'[project]\nname = "{name}"\nversion = "0.0.0"\n')
    ctx.warn(f"{app_dir.name} no tenia manifiesto: se creo {manifest.name} en 0.0.0.")
    return manifest


def _binary_label(app_dir: Path, source: Path, name: str) -> str:
    """Return the executable's name, tagged with its platform.

    PyInstaller does not cross-compile: the binary serves the system
    Consola runs on, and without the tag Windows's and Linux's overwrite
    each other at the same VPS path. The name carries no version on
    purpose: the download URL stays stable, and whoever wants the
    version reads the manifest published next to it.
    """
    base = name.strip()
    if not base:
        base = app_dir.name if source.stem in _GENERIC_NAMES else source.stem
    return f"{base}-{HOST.system.lower()}-{platform.machine().lower()}"


def _binary_output(app_dir: Path, label: str, onefile: bool) -> Path:
    """Return where PyInstaller's output lands.

    A file with `--onefile`, a folder without it. It serves to read what
    was just compiled and to find what was already there.
    """
    suffix = HOST.executable_suffix if onefile else ""
    return app_dir / "dist" / f"{label}{suffix}"


def compile_binary(
    ctx: TaskContext,
    entrypoint: str = "",
    name: str = "",
    *,
    onefile: bool = True,
    windowed: bool = False,
) -> Path:
    """Package an executable with PyInstaller.

    It runs with the app's folder as working directory, not the repo's
    root: so `dist/` and `build/` stay next to the manifest just
    versioned.

    `--specpath build` sends the generated `.spec` inside `build/`. It
    is a derived file, and at the app's root it showed as an uncommitted
    change after each compile; in `build/` «Limpiar artefactos» already
    covers it.

    No `--clean`: it deletes PyInstaller's cache and reanalyzes all
    dependencies each run. It is the same economy by which
    `install_node_modules` does not delete `node_modules`: the cache
    exists for repeated builds, and the artifact cleaning button is
    there for a truly clean one.
    """
    source = resolve_entrypoint(ctx, entrypoint)
    app_dir = _binary_app(ctx.root, source)
    label = _binary_label(app_dir, source, name)
    pyinstaller = toolchain.pyinstaller_cmd(app_dir, ctx.config.get("PYINSTALLER_BIN"))

    argv = [
        *pyinstaller,
        "--noconfirm",
        "--name",
        label,
        "--specpath",
        "build",
        *(["--onefile"] if onefile else []),
    ]
    if windowed:
        # No console: on Windows a window app also opens a black cmd
        # behind it if packaged without this.
        argv.append("--windowed")
    (app_dir / "build").mkdir(parents=True, exist_ok=True)
    if ctx.config.get("BRAND_ICON"):
        # The executable's icon is the repo's logo, like its other apps'
        # (ADR-0056). It goes to `build/`, which is derived: «Limpiar
        # artefactos» covers it and it shows as no change of the repo.
        logo = icons.brand_file(ctx.root, ctx.config.get("BRAND_ICON"), "BRAND_ICON")
        ico = app_dir / "build" / "icon.ico"
        ico.write_bytes(raster.svg_to_ico(logo))
        argv += ["--icon", str(ico)]
    ctx.run([*argv, str(source)], cwd=app_dir)

    artifact = _binary_output(app_dir, label, onefile)
    if not artifact.exists():
        raise TaskError(f"PyInstaller no dejo el binario esperado en {artifact}.")
    ctx.ok(f"Binario: {artifact} ({files.human_size(files.size_of(artifact))})")
    return artifact


def checksum_artifact(ctx: TaskContext, artifact: Path) -> Path:
    """Write the artifact's SHA-256 next to it, in `sha256sum` format.

    A downloaded executable cannot be looked into: the hash is all that
    lets one check that what was downloaded is what was published. It
    saves as `<binary>.sha256` so `sha256sum -c` verifies it unedited.
    """
    if artifact.is_dir():
        # With `--onefile` off there is no file to sign but a whole
        # tree; a hash per file is not what anyone will verify by hand.
        raise TaskError("El checksum solo aplica al empaquetado en un archivo.")
    fingerprint = files.digest(artifact)
    destination = artifact.with_name(f"{artifact.name}.sha256")
    files.write_text(destination, f"{fingerprint}  {artifact.name}\n")
    ctx.ok(f"SHA-256: {fingerprint}")
    return destination


def _maybe_checksum(ctx: TaskContext, artifact: Path) -> Path | None:
    """Run the checked step's checksum.

    Skipped with a notice if not applicable.

    Folder packaging has no file to sign, and there the step is no error
    but a combination that means nothing. Failing after packaging, the
    only expensive part of the flow, would throw away the build for a
    checkbox.
    """
    if artifact.is_dir():
        ctx.warn("Checksum omitido: el empaquetado en carpeta no es un archivo que firmar.")
        return None
    return checksum_artifact(ctx, artifact)


def _publish_binary(
    ctx: TaskContext, app: str, artifact: Path, manifest: Path, checksum: Path | None
) -> None:
    """Upload the binary, its manifest and its checksum if generated.

    They go together or not at all. The executable does not say which
    version it is, and on the VPS the manifest is all that identifies
    it.

    The binary uploads with execute permission: `scp` does not keep it,
    and the other side would get an executable that cannot execute.
    """
    # `chmod -R` for folder packaging: there the executable is a file
    # inside, and the folder's bit is no use to it.
    upload_artifact(ctx, artifact, chmod="-R 755" if artifact.is_dir() else "755")
    upload_artifact(ctx, manifest)
    if checksum is not None:
        upload_artifact(ctx, checksum)
    _publish_release(ctx, app, HOST.system.lower(), artifact, manifest)


# --- composites ---


def build_flutter(
    ctx: TaskContext,
    directory: str = "",
    platforms: Sequence[str] = ("apk",),
) -> list[Path]:
    """Compile the app for each checked platform.

    Without the bump or the VPS upload: the version comes from the tag
    and the APK is not published on the VPS (ADR-0059). One button for
    Flutter and Flet: `directory` names *which* app of the repo, not
    what it is written in, and the framework comes from the folder.

    There is no `pub get` step: `flutter build` resolves dependencies by
    itself.
    """
    app = _mobile(ctx, directory)
    names = ", ".join(toolchain.BUILD_PLATFORMS[p].label for p in platforms)
    outputs: list[Path] = []
    for target_platform in platforms:
        ctx.raise_if_cancelled()
        outputs.append(compile_flutter(ctx, app.name, target_platform))
    ctx.note(f"Build {app.name} ({names})")
    return outputs


def build_vite(ctx: TaskContext, directories: Sequence[str] = ()) -> list[Path]:
    """Run pnpm install and build for each chosen SPA.

    Its axis is `many`: a repo has one mobile app but tends to have
    three SPAs (`panel`, `backoffice`, `landing`), and compiling them is
    a task that ends, so the checked ones loop here, N builds in a row
    in one log, and not one tab each like the dev server launcher
    (ADR-0010).

    An empty list means «the only SPA there is», like `build_flutter`'s
    empty `directory`: in a repo with one, the axis does not even draw.
    """
    chosen = [_target(ctx, targets.SPA_VITE, name) for name in (directories or [""])]
    outputs: list[Path] = []
    for index, spa in enumerate(chosen, start=1):
        ctx.raise_if_cancelled()
        if len(chosen) > 1:
            ctx.step(f"{spa.name} ({index} de {len(chosen)})")
        install_node_modules(ctx, spa.name)
        outputs.append(compile_spa(ctx, spa.name))
        ctx.note(f"Build Vite {spa.name}")
    return outputs


def build_binary(
    ctx: TaskContext,
    entrypoint: str = "",
    name: str = "",
    bump_mode: str = "patch",
    *,
    onefile: bool = True,
    windowed: bool = False,
    bump: bool = True,
    build: bool = True,
    checksum: bool = True,
    upload: bool = False,
) -> Path | None:
    """Composite: manifest bump, PyInstaller, checksum, upload.

    The same skeleton as `build_flutter` and `build_vite`, with the same
    re-upload mode: without `build` nothing compiles and the executable
    already in `dist/` uploads, to resume a cut `scp` without paying for
    another whole packaging.

    If the build fails, the version returns to what it was: the repo
    does not stay marked with a number never published.
    """
    source = resolve_entrypoint(ctx, entrypoint)
    app_dir = _binary_app(ctx.root, source)
    manifest = _ensure_manifest(ctx, app_dir)
    rel = "" if app_dir == ctx.root else app_dir.relative_to(ctx.root).as_posix()

    if not build:
        if not upload:
            raise TaskError("Sin compilar y sin subir no queda nada por hacer.")
        if bump:
            ctx.warn(
                "Bump ignorado: el binario que hay en disco se empaqueto con la "
                "version que ya tiene el manifiesto, y subirla cambiada lo "
                "anunciaria como otra cosa."
            )
        artifact = _binary_output(app_dir, _binary_label(app_dir, source, name), onefile)
        if not artifact.exists():
            raise TaskError(f"No hay ningun binario compilado en {artifact}.")
        signature = _maybe_checksum(ctx, artifact) if checksum else None
        ctx.step("upload")
        _publish_binary(ctx, app_dir.name, artifact, manifest, signature)
        ctx.note(f"Re-subida binario {artifact.name} {versioning.read_version(manifest)}")
        return artifact

    with files.reversible(manifest):
        if bump:
            ctx.step("bump")
            bump_version(ctx, rel, bump_mode)
        ctx.step("build")
        artifact = compile_binary(ctx, str(source), name, onefile=onefile, windowed=windowed)

    signature = None
    if checksum:
        ctx.step("checksum")
        signature = _maybe_checksum(ctx, artifact)

    if upload:
        ctx.step("upload")
        _publish_binary(ctx, app_dir.name, artifact, manifest, signature)

    ctx.note(f"Build binario {artifact.name} {versioning.read_version(manifest)}")
    return artifact


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("build_flutter", build_flutter)
    registry.bind("build_vite", build_vite)
    registry.bind("create_spa", create_spa)
    registry.bind("build_binary", build_binary)
    registry.bind("bump_version", bump_version)
    registry.bind("upload_to_vps", upload_artifact)
