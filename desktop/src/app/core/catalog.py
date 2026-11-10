"""The catalog: the shape of each button."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from app.core import android, cache, canone, files, icons, shots, ssh, targets, toolchain, vps
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.registry import AxisDef, Capability, Facet, Step, registry

_VPS_KEYS = {"VPS_IP", "VPS_USER", "VPS_KEY_NAME", "VPS_DEPLOY_DIR"}

# The three things truly chosen of a system image. The SDK's id brings
# them permuted in one package
# (`system-images;android-36;google_apis;x86_64`), and the catalog
# publishes several hundred: a list with all of them is the same
# question asked three hundred times. Declared this way, the panel draws
# three short lists trimming each other, so changing the version leaves
# only the variants existing for it, and the saved value is still the
# whole package.
_IMAGE_FACETS = (
    Facet("api", "Versión", 1),
    Facet("variant", "Variante", 2),
    Facet("abi", "Arquitectura", 3),
)

# The 'local'/'remote' axis repeats alike on a dozen buttons: one table
# of labels so the panel does not show raw lower-case values.
_SCOPE_LABELS = {"local": "Local", "remote": "Remoto"}

# Locally, every button with this axis connects to the database
# (`db.credentials`): user, database and password. On the VPS it enters
# by SSH, and canone's roles have no password.
_DB_KEYS = {"DB_USER", "DB_NAME", "DB_PASSWORD"}
_PG_KEYS = {"PG_SUPERUSER", "PG_PASSWORD"}


def _scope_axis() -> AxisDef:
    return AxisDef(
        "scope",
        ["local", "remote"],
        "scope",
        labels=_SCOPE_LABELS,
        requires_env={
            "local": _DB_KEYS,
            "remote": {"VPS_IP", "VPS_USER", "VPS_KEY_NAME"},
        },
    )


# Which systemd unit the action touches. Three services run on the same
# VPS, the repo's, coturn and Caddy, and all three restart, stop and
# read alike. It is an axis and not three new buttons for the same
# reason `action` is an axis and not nine buttons: all that changes
# between them is a name.
#
# Values are not enumerated: they come from asking THIS repo's VPS which
# of canone's units exist (`VPS_SERVICES`). Always offering them all
# offered restarting a coturn that is not installed, finding out only on
# pressing.
def _service_axis() -> AxisDef:
    return AxisDef(
        "service", [], "scope", label="Servicio", default=vps.MAIN_SERVICE, source=VPS_SERVICES
    )


# `host` belongs to the uvicorn brought up on THIS machine: listen on
# all interfaces, to try from the phone, or only loopback. Values are
# what uvicorn understands; what reads goes in `labels`, because
# `0.0.0.0` is no phrase.
def _host_axis() -> AxisDef:
    return AxisDef(
        "host",
        ["0.0.0.0", "127.0.0.1"],
        "scope",
        label="Escucha en",
        labels={"0.0.0.0": "Toda la red", "127.0.0.1": "Solo esta máquina"},
    )


def for_project(cap: Capability, root: Path | str | None) -> Capability:
    """Return the capability as seen with this repo open.

    Discovered axes (ADR-0006) cannot be declared in `load_catalog()`:
    the catalog builds once at startup and the repo changes with the
    selector. Here their values fill by looking at the repo, right
    before drawing the panel: a repo with three SPAs gives three values,
    one with one gives one, and a new subproject appears without
    touching the catalog.

    The same holds for steps: those requiring a feature the repo lacks
    (`Step.requires_repo`) do not draw. They do not go amber like those
    waiting for a key: there a datum that can be loaded is missing; here
    the object to act on is, and the checkbox would lead nowhere.

    Steps drop from the COPY the panel looks at, not the catalog: the
    registered capability builds the kwargs (`TabPanel._run` finds it by
    id), and a step the panel did not draw is not checked in the
    payload, so it reaches the function as False. That is right: the
    step stays off.

    It returns the same capability when there is nothing to discover, so
    calling it for all costs nothing.
    """
    if not root:
        return cap
    has_steps = any(s.requires_repo for s in cap.steps)
    if not has_steps and not any(a.is_discovered for a in cap.axes):
        return cap
    # `Project.path` is a str; discovery works with paths.
    folder = Path(root)
    if not folder.is_dir():
        return cap
    resolved = [
        replace(a, values=targets.names_of(folder, a.discover)) if a.is_discovered else a
        for a in cap.axes
    ]
    chosen_steps = cap.steps_for(repo_features(folder)) if has_steps else cap.steps
    return replace(cap, axes=resolved, steps=chosen_steps)


def repo_features(root: Path | str | None) -> frozenset[str]:
    """Return which features this repo has.

    See `core/targets.py::features`.
    """
    if not root:
        return frozenset()
    folder = Path(root)
    return targets.features(folder) if folder.is_dir() else frozenset()


def applicable_ids(root: Path | str | None) -> set[str]:
    """Return the buttons that make sense in this repo.

    Those that do not, such as «Migrar» in a repo without migrations,
    hide whole instead of staying amber: they lack no configuration but
    something to act on (ADR-0007). With nothing open nothing hides: the
    menus are already fully disabled.
    """
    if not root:
        return {cap.id for cap in registry.get_all()}
    features = repo_features(root)
    return {cap.id for cap in registry.get_all() if cap.applies_to(features)}


# --- catalogs that are queried ---
#
# A `discover` axis fills by looking at the open repo
# (`core/targets.py`). These fill by asking something: the SDK, which
# devices and virtual machines exist; the repo's VPS, which of the
# services Consola administers exist there. They are the same idea as
# ADR-0006 against a source that is not the folder, so they live here,
# next to `for_project`, and not in the catalog of buttons.
#
# The difference between the two families is who is asked, and with it
# how long it takes: the SDK is local, the VPS an SSH round trip. So
# both resolve off the interface thread
# (`ui/params_panel.py::AxesLoader`) and both are cached.

ANDROID_DEVICES = "android_devices"  # device catalog
ANDROID_IMAGES = "android_images"  # catalog of published machines
# machines already installed
ANDROID_IMAGES_INSTALLED = "android_installed"
ANDROID_AVDS = "android_avds"  # AVDs already created
ANDROID_RUNNING = "android_running"  # emulators alive right now
VPS_SERVICES = "vps_services"  # systemd services existing on the VPS
BACKUP_FILES = "backup_files"  # backups of this repo already saved
RELEASES = "releases"  # the repo's signed releases on GitHub
# what the repo's camera says it captures: its apps, themes and
# languages (ADR-0054)
SHOTS_APPS = "shots_apps"
SHOTS_THEMES = "shots_themes"
SHOTS_LANGUAGES = "shots_languages"
_SHOTS_AXES = {SHOTS_APPS: "apps", SHOTS_THEMES: "themes", SHOTS_LANGUAGES: "languages"}
# the repo's apps that take their icon from the logo
ICON_APPS = "icon_apps"
# the packages canone's `packages.py` installs for this repo
PACKAGES = "packages"
# the title each preview goes under in the panel, and what decides it
PREVIEW_TITLES = {PACKAGES: "Paquetes"}
PREVIEW_HINTS = {PACKAGES: "Lo decide config.env: DB_EXTENSIONS, TURN y LOGS"}

# What is installed and created changes while Consola is open, so they
# cache for a minute and no more: enough not to repeat the query on
# opening three tabs in a row, and not enough to lie after an install.
# The two large catalogs use the month default of `core/cache.py`.
_FRESH = 60.0


def preview_checks(source: str, *, config: Config) -> tuple[list[str], list[str]]:
    """Return what a capability's preview shows: all, and the marked.

    Every package canone's `packages.py` can install, and those it will
    install with the options `config.env` gives. It reads the saved
    file: what the task will read when it runs.
    """
    if source == PACKAGES:
        return canone.installable(config), canone.packages(config)
    raise TaskError(f"Vista previa desconocida: {source}")


def queried_values(
    source: str,
    *,
    refresh: bool = False,
    config: Config | None = None,
    root: Path | str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Return a queried axis's values, with their readable labels.

    A source that fails raises `TaskError`, and the panel shows why in
    place of the axis: an empty axis would hide it (ADR-0076).
    """
    if source == VPS_SERVICES:
        return _vps_services(config, root, refresh=refresh)
    if source == BACKUP_FILES:
        return _backup_files(config, root)
    if source == RELEASES:
        return _releases(root)
    if source in _SHOTS_AXES:
        return _shots_axis(source, config, root, refresh=refresh)
    if source == ICON_APPS:
        return _icon_apps(root)
    sdk = android.resolve_sdk()
    if source == ANDROID_DEVICES:
        catalog = android.device_catalog(sdk, refresh=refresh)
        return [d.id for d in catalog], {d.id: d.label for d in catalog}
    if source == ANDROID_IMAGES:
        catalog = android.image_catalog(sdk, refresh=refresh)
        return [i.package for i in catalog], _image_labels(catalog)
    if source == ANDROID_IMAGES_INSTALLED:
        packages = cache.cached(
            "android-installed", lambda: android.list_images(sdk), max_age=_FRESH, refresh=refresh
        )
        images = sorted((android.parse_image(p) for p in packages), key=lambda i: i.order)
        return [i.package for i in images], _image_labels(images)
    if source == ANDROID_AVDS:
        names = cache.cached(
            "android-avds", lambda: android.list_avds(sdk), max_age=_FRESH, refresh=refresh
        )
        return list(names), {}
    if source == ANDROID_RUNNING:
        # Never cached: it is state, not catalog. An old answer here
        # would offer stopping an emulator that no longer exists.
        alive = android.running(sdk)
        return list(alive), {s: f"{n or '?'}  ({s})" for s, n in alive.items()}
    raise TaskError(f"Fuente desconocida: {source}")


def _image_labels(images: list[android.Image]) -> dict[str, str]:
    """Return the labels of a system image axis.

    Whole package and parts.

    Both in the same table because `AxisDef.text_of` is one, and the ids
    do not clash: a package always starts with `system-images;`. The
    axis draws by feature (`_IMAGE_FACETS`), but the whole package still
    reads in the run's summary and the «Liberar disco» list.
    """
    return {**{i.package: i.label for i in images}, **android.facet_labels(images)}


def _vps_services(
    config: Config | None, root: Path | str | None, *, refresh: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Return the services that exist on THIS repo's VPS.

    Without configuration there is nobody to ask, and returning them all
    would offer coturn in a repo that has no IP yet: the axis stays
    empty and the panel says so, as when no AVDs exist.

    The cache is per host and not global: two open repos are almost
    always two VPSs, and sharing the answer would show one the other's
    services.
    """
    if config is None or root is None or not config.get("VPS_IP"):
        return [], {}
    remote = ssh.resolve_remote(config)
    _, app = canone.origin(Path(root))
    key = "".join(c if c.isalnum() else "-" for c in remote.target)
    values = cache.cached(
        f"vps-units-{key}",
        lambda: vps.installed_services(remote, app),
        max_age=_FRESH,
        refresh=refresh,
    )
    return list(values), vps.SERVICE_LABELS


def _backup_files(
    config: Config | None, root: Path | str | None
) -> tuple[list[str], dict[str, str]]:
    """Return this repo's saved backups, newest first.

    **Uncached**, like `ANDROID_RUNNING`: it is state, not catalog. An
    old list would offer restoring a dump rotation just deleted.

    Newest first so the preselected one is the last backup, almost
    always what is wanted.

    It is the only queried axis needing the repo's root besides the
    configuration: the folder may be relative to it. The others ask the
    SDK or the VPS, which do not depend on where the repo is.
    """
    if config is None or not root:
        return [], {}
    # circular: tasks imports the registry
    from app.core.tasks.database import list_backups

    values = list_backups(config, Path(root))
    return [p.name for p in values], {p.name: _backup_label(p) for p in values}


def _releases(root: Path | str | None) -> tuple[list[str], dict[str, str]]:
    """Return the repo's releases with their signature, newest first.

    Uncached, like `BACKUP_FILES`: a release gets signed while Consola
    is open. If GitHub does not answer, the `TaskError` rises with what
    `gh` said: an empty axis would say there are no releases.
    """
    if not root:
        return [], {}
    # circular: tasks imports the registry
    from app.core.tasks.vps_release import releases

    _, app = canone.origin(Path(root))
    signed = canone.signed(app, releases(Path(root)))
    return (
        [r["tag_name"] for r in signed],
        {r["tag_name"]: f"{r['tag_name']}  ({r['published_at'][:10]})" for r in signed},
    )


def _icon_apps(root: Path | str | None) -> tuple[list[str], dict[str, str]]:
    """Return the apps that say where their icon goes (ADR-0055).

    It looks at the repo and no tool, but the app's type is not enough:
    an SPA importing the logo by itself carries no `favicon.svg`, and
    offering it checked meant failing each run until someone unchecked
    it. Uncached: it is reading two files per app.
    """
    if not root or not Path(root).is_dir():
        return [], {}
    return [t.name for t in icons.icon_apps(Path(root))], {}


def _shots_axis(
    source: str, config: Config | None, root: Path | str | None, *, refresh: bool = False
) -> tuple[list[str], dict[str, str]]:
    """Return a camera axis, with what it says it captures (ADR-0054).

    Asking it means starting node, and the three axes ask the same: it
    caches per repo for a minute, like AVDs. A changed camera shows in a
    minute or with Reload.
    """
    if config is None or not root:
        return [], {}
    # circular: tasks imports the registry
    from app.core.tasks.images import camera_supported

    key = "".join(c if c.isalnum() else "-" for c in str(Path(root).resolve()))
    declared = cache.cached(
        f"shots-supported-{key}",
        lambda: camera_supported(Path(root), config),
        max_age=_FRESH,
        refresh=refresh,
    )
    axis = _SHOTS_AXES[source]
    labels = SHOT_THEME_LABELS if axis == "themes" else {}
    return shots.supported_values(declared, axis), labels


def _backup_label(path: Path) -> str:
    """Return `2026-09-23 14:30  ·  12,4 MB` for a backup.

    The real value is the file's name, which carries the stamp stuck on
    and unseparated: unreadable in a list.
    """
    parts = path.stem.rsplit("-", 2)
    try:
        when = (
            datetime.strptime("-".join(parts[-2:]), "%Y%m%d-%H%M%S")
            .replace(tzinfo=UTC)
            .astimezone()
        )
    except ValueError:
        return path.name
    return f"{when:%Y-%m-%d %H:%M}  ·  {files.human_size(files.size_of(path))}"


def forget_machine_cache() -> None:
    """Forget what changes on installing, creating or deleting.

    The UI calls it when a machine task ends: the next panel sees the
    new state.
    """
    cache.forget("android-installed")
    cache.forget("android-avds")


# The SDKs' default values. They live here, with the rest of the
# buttons' shape, and `core/tasks/utils.py` imports them to use the same
# when called without parameters: so the panel and the function cannot
# disagree. Linux uses the conventional paths under home; Windows, fixed
# drives.
ANDROID_DIR_DEFAULT = HOST.android_dir_default
FLUTTER_DIR_DEFAULT = HOST.flutter_dir_default
API_LEVEL_DEFAULT = "36"
BUILD_TOOLS_DEFAULT = "36.0.0"

ANDROID_PACKAGE_AXES = [
    AxisDef(
        "components",
        ["platform-tools", "emulator", "build-tools", "platform"],
        "checks",
        select="many",
        label="Componentes",
    ),
    AxisDef("api_level", [API_LEVEL_DEFAULT], "field", label="API level"),
    AxisDef("build_tools", [BUILD_TOOLS_DEFAULT], "field", label="Build-tools"),
]

# The axes of 'clean_artifacts'. Values are the keys
# `core/tasks/utils.py::find_artifacts` understands and labels go apart,
# in `labels`: that is the naming contract (ADR-0003).
FAMILY_AXIS_VALUES = ["python", "gradle", "flutter", "crash"]
FAMILY_AXIS_LABELS = {
    "python": "Python",
    "gradle": "Gradle/Android",
    "flutter": "Flutter",
    "crash": "Volcados de crash",
}
HEAVY_AXIS_VALUES = ["node_modules", "venv", "build", "dart_tool"]
HEAVY_AXIS_LABELS = {
    "node_modules": "node_modules",
    "venv": ".venv",
    "build": "build/dist",
    "dart_tool": ".dart_tool",
}

# Only the executable bumps the manifest's version (ADR-0059). They show
# from major to minor, and the real default is `patch`.
SEMVER_MODES = ["major", "minor", "patch", "none"]


def _semver_axis() -> AxisDef:
    return AxisDef("bump_mode", SEMVER_MODES, "scope", label="Bump", default="patch")


# Only those this machine can compile: offering Windows on Linux would
# be offering a checkbox that always ends in error. Each brings its
# output folder from `config.env`, which only appears on screen if the
# platform is checked.
def _platforms_axis() -> AxisDef:
    return AxisDef(
        "platforms",
        toolchain.host_platforms(),
        "checks",
        select="many",
        label="Plataformas",
        defaults={"apk"},
        labels={k: p.label for k, p in toolchain.BUILD_PLATFORMS.items()},
        uses_env={k: {toolchain.out_key(k)} for k in toolchain.BUILD_PLATFORMS},
    )


# «Compilar binario» is not required: uploading the executable already
# in `dist/` without packaging again resumes a cut `scp`. «Checksum
# SHA-256» belongs to the binary: a downloaded executable cannot be
# looked into, and the hash is all that lets one check that what was
# downloaded is what was published.
BUILD_BINARY_STEPS = [
    Step("bump", "Subir número de versión"),
    Step("build", "Compilar binario"),
    Step("checksum", "Calcular checksum"),
    Step("upload", "Subir al VPS", default=False, requires_env=_VPS_KEYS),
]

# The eight steps of `database.bootstrap_db` are its eight booleans: it
# ends in a usable database, with partitions and data, not only the
# created schema.
#
# «Extensiones» starts unchecked because PostGIS's system package is not
# always there: checking it by default promised an extension the machine
# did not have.
#
# Which extensions comes from `DB_EXTENSIONS`, not deduced: `alembic
# revision --autogenerate` never writes a `CREATE EXTENSION`, and a
# migration declaring one needs the extension already created to apply.
# The checkbox chooses whether the step runs; WHICH is no run parameter
# but repo configuration, so it has no axis.
#
# Labels are verbs and say what they act on: a box saying «Migraciones»
# does not tell generating from running them, and in a destructive
# composite «Base de datos» does not say whether it creates or deletes.
# The noun names the object; the checkbox has to name the act.
BOOTSTRAP_DB_STEPS = [
    Step("role", "Crear rol de la aplicación"),
    Step("database", "Crear base de datos"),
    Step("privileges", "Otorgar permisos al rol"),
    Step("extensions", "Habilitar extensiones", default=False),
    Step("migrate", "Ejecutar migraciones", requires_repo=targets.MIGRATIONS),
    Step("partitions", "Crear particiones"),
    Step("seeders", "Cargar seeders"),
    Step("mock_seeders", "Cargar datos mock", default=False),
]


# Those of `database.rebuild_db`, in the function's order.
#
# Rebuilding does not rewrite the migration history: it applies what is
# there. Deleting it and writing a new initial one is
# `reinit_migrations`, its own button.
#
# Locally it deletes the tables as superuser; on the VPS
# `database.py empty` deletes the database and the uploaded files.
# canone has no partitions.
_LOCAL = frozenset({"local"})
_REMOTE = frozenset({"remote"})
REBUILD_DB_STEPS = [
    Step("drop", "Borrar tablas", requires_env=_PG_KEYS, scopes=_LOCAL),
    Step("empty", "Vaciar la base y los archivos subidos", scopes=_REMOTE),
    Step("migrate", "Ejecutar migraciones", requires_repo=targets.MIGRATIONS),
    Step("partitions", "Crear particiones", scopes=_LOCAL),
    Step("seeders", "Cargar seeders"),
    Step("mock_seeders", "Cargar datos mock"),
]


# The three of `database.reinit_migrations`. «Vaciar esquema» is a step
# of its own and no precondition to remember: autogenerate compares
# against the live database, and over a database with tables the
# «initial» comes out empty.
REINIT_MIGRATIONS_STEPS = [
    Step("drop", "Borrar tablas"),
    Step("reset", "Borrar migraciones"),
    Step("generate", "Generar migración inicial"),
]


# The two steps of `database.migrate_db`: generating the revision to
# look at before applying, or bringing a late database up to date
# without autogenerating.
MIGRATE_DB_STEPS = [
    Step("generate", "Generar migración"),
    Step("apply", "Ejecutar migraciones"),
]


# Configure VPS, in the order the machine needs: `install.py` fails
# without the packages or swap, and `install.py` installs what
# `credentials.py` needs. Refreshing the fingerprint starts unchecked:
# it is needed only after reinstalling the VPS.
BOOTSTRAP_VPS_STEPS = [
    Step("known_host", "Refrescar known_hosts", default=False),
    Step("key", "Poner la llave"),
    Step("software", "Instalar paquetes y uv"),
    Step("swap", "Crear swap"),
    Step(
        "infra",
        "Instalar infraestructura",
        requires_env={"DOMAIN", "VALKEY_MEMORY", "OFFLINE_KEY"},
    ),
    Step("credentials", "Cargar credenciales", requires_env={"RESTIC_PASSWORD"}),
    Step("deploy", "Desplegar el último release"),
]

# Tag, `release.yml`, signature, `deploy.py`. Keys go per step: creating
# the tag does not reach the VPS, and signing only asks for the key.
PUBLISH_RELEASE_STEPS = [
    Step("tag", "Crear tag"),
    Step("sign", "Firmar release", requires_env={"VPS_KEY_NAME"}),
    Step("deploy", "Desplegar", requires_env=_VPS_KEYS - {"VPS_DEPLOY_DIR"}),
]


# The three launchers of the daily start, as steps of a composite that
# is NOT a sequence: they launch at once, each in its tab, and none ends
# (ADR-0011). This list's order is the dispatch's, and all that matters
# is that the backend goes first: the other two wait for its endpoint.
#
# The steps below are parameters of their function: `composed_of` names
# CAPABILITIES (`generate_remote_keypair`), not parameters (`generate`),
# so steps cannot derive from it (ADR-0003).

# The two sides of the key THIS machine enters with. Unchecking the
# local one is the case of revoking access of a machine no longer at
# hand.
REVOKE_SSH_STEPS = [
    Step("remote_side", "Borrar clave del VPS"),
    Step("local_side", "Borrar clave de esta máquina"),
]

# The three steps of `utils.install_android_sdk`, one boolean each
# (ADR-0003).
INSTALL_ANDROID_SDK_STEPS = [
    Step("tools", "Instalar herramientas de línea de comandos"),
    Step("packages", "Instalar paquetes del SDK"),
    Step("hypervisor", "Instalar aceleración del emulador"),
]

# Deleting the database and leaving the role is what is wanted before a
# bootstrap: other databases on the same server use the role.
TEARDOWN_DB_STEPS = [
    Step("database", "Borrar base de datos"),
    Step("role", "Borrar rol de la aplicación"),
]

SHOT_DESTINATION_LABELS = {
    "landing": "Landing",
    "play": "Google Play",
    "appstore": "App Store",
    "manual": "Manual",
    "og": "Open Graph",
    "social": "Redes sociales",
    "presskit": "Press kit",
}


def _shot_destinations_axis() -> AxisDef:
    return AxisDef(
        "destinations",
        list(SHOT_DESTINATION_LABELS),
        "checks",
        select="many",
        label="Destinos",
        defaults={"landing"},
        labels=SHOT_DESTINATION_LABELS,
    )


SHOT_THEME_LABELS = {"claro": "Claro", "oscuro": "Oscuro"}


# What Consola passes the repo's camera as arguments (`--apps`,
# `--themes`, `--languages`, and `--device` with the chosen AVD's
# serial). The camera itself offers the apps, themes and languages
# (ADR-0054): only what it can capture is offered. Screens are not
# chosen: they are its own.
def _shot_camera_axes() -> list[AxisDef]:
    return [
        AxisDef("apps", [], "checks", select="many", label="Apps", source=SHOTS_APPS),
        AxisDef("themes", [], "checks", select="many", label="Temas", source=SHOTS_THEMES),
        AxisDef("languages", [], "checks", select="many", label="Idiomas", source=SHOTS_LANGUAGES),
        # Consola chooses and starts the emulator, not the script
        # (ADR-0049): a created AVD is chosen, and if not alive it comes
        # up before running the camera. The camera knows whether an app
        # needs it (ADR-0052): with none, it stops before the first
        # shot.
        AxisDef(
            "avd",
            [],
            "pick",
            label="Emulador",
            source=ANDROID_AVDS,
            allow_empty=True,
            labels={"": "Ninguno"},
        ),
    ]


SCREENSHOTS_STEPS = [
    Step("shoot", "Sacar capturas", requires_env={"SHOTS_CMD"}),
    Step("render", "Revelar capturas"),
]

DEV_ENV_STEPS = [
    Step("backend", "Backend", optional=False),
    Step("serve_vite", "SPA"),
    Step("run_python", "App de escritorio", default=False),
]


def load_catalog() -> None:
    """Declare the shape of each button.

    `description` is the line the UI shows in the rail's tooltip and
    under the action's name: what it does, in the present, in one
    sentence. `level` is only written when not deduced by itself: a
    composite not publishing its steps (`teardown_db`, `migrate_db`) has
    to declare `level='C'` by hand, because without `steps` or
    `composed_of` the UI would take it for atomic.
    """
    # --- Run ---
    #
    # What the launcher DELIVERS decides whether its tab has a second
    # view: a URL is looked at in a browser, an emulator in its window
    # (ADR-0008).
    #
    # `view='web'` is no extra button or separate capability: it is the
    # second view of the launcher's own tab, pointed at the endpoint the
    # task publishes with `ctx.serve()`. An «open browser» button in the
    # rail would be a capability that runs nothing, records nothing and
    # has no parameters.
    registry.register(
        Capability(
            id="backend",
            name="Levantar backend",
            group="Ejecutar",
            kind="live",
            icon="▶",
            view="web",
            description="Levanta el servidor FastAPI del repo, local o contra el VPS.",
            # The server is discovered like SPAs: the folder whose
            # startup module creates `FastAPI(`, called `server/` or
            # `backend/`. The port is only the preferred one, since
            # `core/ports.py` looks for the next free, so it can stay as
            # is without fear of clashing with another tab.
            axes=[
                AxisDef("target", [], "scope", label="Servidor", discover=(targets.FASTAPI,)),
                _scope_axis(),
                _host_axis(),
                AxisDef("preferred_port", ["8000"], "field", label="Puerto", cast="int"),
                # No reload is the mode for trying what will run on the
                # VPS: `--reload` changes how the app starts and hides
                # errors that only happen once.
                AxisDef(
                    "reload",
                    ["reload", "no_reload"],
                    "scope",
                    label="Al cambiar el código",
                    truthy="reload",
                    labels={"reload": "Con recarga", "no_reload": "Sin recarga"},
                ),
            ],
            stub=True,
        )
    )
    # `fanout='target'`: checking panel + backoffice is two live dev
    # servers at once, not two steps in a row. A `many` axis loops when
    # the capability ends (`build_vite`) and shares into tabs when not
    # (ADR-0010).
    registry.register(
        Capability(
            id="serve_vite",
            name="Levantar SPA con Vite",
            group="Ejecutar",
            kind="live",
            icon="🌐",
            view="web",
            fanout="target",
            description="Arranca el dev server de Vite para las apps elegidas.",
            axes=[
                AxisDef(
                    "target",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=(targets.SPA_VITE,),
                ),
                # The preferred port, not the final one: with two SPAs
                # checked the second tab takes the next free by itself.
                AxisDef("preferred_port", ["5173"], "field", label="Puerto", cast="int"),
            ],
            stub=True,
        )
    )
    # No `framework` axis: choosing «Flutter or Flet» would ask to
    # confirm what the folder already answers. The app is chosen; the
    # framework comes with it. No `view` either: what it delivers is not
    # a URL but an app on an emulator, and Android draws that window.
    registry.register(
        Capability(
            id="run_mobile",
            name="Levantar app móvil",
            group="Ejecutar",
            kind="live",
            icon="📲",
            description="Corre la app móvil en el emulador o dispositivo conectado.",
            # `device` admits empty and starts empty: the function
            # already chooses by itself, the emulator this session
            # launched or else the first to answer, and it only has to
            # be said with two alive. An axis forcing a choice would
            # leave the button amber right when there is none, when the
            # useful message is the function's.
            axes=[
                AxisDef("target", [], "scope", label="App móvil", discover=targets.MOBILE_APP),
                AxisDef(
                    "device",
                    [],
                    "pick",
                    label="Emulador",
                    source=ANDROID_RUNNING,
                    allow_empty=True,
                    labels={"": "El que esté corriendo"},
                ),
            ],
            stub=True,
        )
    )
    # Any Python app of the repo that is not the server: PySide6,
    # desktop Flet, a bot. Like `serve_vite`, checking several opens one
    # tab each (ADR-0010).
    registry.register(
        Capability(
            id="run_python",
            name="Levantar app de escritorio",
            group="Ejecutar",
            kind="live",
            icon="🐍",
            fanout="target",
            description="Arranca las apps Python elegidas, con recarga al cambiar sus fuentes.",
            axes=[
                AxisDef(
                    "target",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=targets.DESKTOP_APP,
                )
            ],
            # Two loose booleans, not a chained step: a real checkbox,
            # not `scope`'s segment, which is for «one of these two»,
            # not «yes or no».
            steps=[
                Step("watch", "Relanzar al detectar cambios"),
                Step("auto_login", "Auto-login de dev", default=False),
            ],
            stub=True,
        )
    )
    # The group's concurrent composite. It has no `func` or adapter: its
    # body is the dispatcher of `ui/tab_panel.py`, because «one tab per
    # step, all alive at once» means nothing inside `core/` (ADR-0011).
    # So it declares `stub=False` by hand.
    registry.register(
        Capability(
            id="dev_env",
            name="Levantar todo el entorno",
            cut=True,
            group="Ejecutar",
            kind="live",
            icon="🧪",
            level="C",
            concurrent=True,
            description="Levanta backend, SPA y apps Python a la vez, cada uno en su pestaña.",
            steps=DEV_ENV_STEPS,
            composed_of=["backend", "serve_vite", "run_python"],
            stub=False,
        )
    )

    # --- Build ---
    #
    # No axes: the folder's name is asked when running (`ctx.ask`) and
    # not saved. It is not a parameter, since a parameter is a decision
    # repeated alike that the catalog remembers per repo, or a
    # configuration datum: each new SPA has another name, and saved it
    # left the second run starting with the first's name, a folder that
    # exists. It is not a discovered axis either: the folder is not
    # there yet.
    registry.register(
        Capability(
            id="create_spa",
            name="Crear SPA SvelteKit",
            group="Compilar",
            kind="once",
            icon="✨",
            description="Crea en el repo una SPA en blanco con SvelteKit, runes y UnoCSS.",
            stub=True,
        )
    )
    # `app` is discovered: one value per mobile app of the repo, Flutter
    # or Flet. The framework is not asked apart because it travels
    # inside the chosen target. `bump_mode` is a closed list, not text:
    # it goes as an exclusive option (like `dry_run` in clean_artifacts)
    # and not a written field.
    registry.register(
        Capability(
            id="build_flutter",
            name="Compilar app Flutter",
            group="Compilar",
            kind="once",
            icon="📦",
            description="Compila la app Flutter o Flet para las plataformas marcadas: APK, web, "
            "escritorio o iOS.",
            axes=[
                AxisDef("directory", [], "scope", label="App", discover=targets.MOBILE_APP),
                _platforms_axis(),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="build_vite",
            name="Compilar SPA",
            group="Compilar",
            kind="once",
            icon="🏗️",
            description="Deja compiladas las SPA del repo, listas para que el proxy las sirva.",
            axes=[
                AxisDef(
                    "directories",
                    [],
                    "checks",
                    select="many",
                    label="Apps",
                    discover=(targets.SPA_VITE,),
                )
            ],
            stub=True,
        )
    )
    # The third builder, and the only one that bumps the version and
    # publishes on the VPS. Its axes are fields and not a discovered
    # list: *any* path of the repo can package (`server/main.py`,
    # `tools/cli.py`), and an empty discovered `app` axis would leave
    # amber the repo packaging from its root (ADR-0007). Empty is not a
    # missing datum: `resolve_entrypoint` deduces `src/main.py` from the
    # repo's only Python app, as the App Python launcher does.
    registry.register(
        Capability(
            id="build_binary",
            name="Compilar ejecutable",
            group="Compilar",
            kind="once",
            icon="⚡",
            description="Empaqueta una app Python del repo como ejecutable descargable.",
            composed_of=["bump_version", "upload_to_vps"],
            axes=[
                AxisDef("entrypoint", [""], "field", label="Punto de entrada"),
                AxisDef("name", [""], "field", label="Nombre del ejecutable"),
                # PyInstaller's two decisions changing *what* gets
                # delivered: a loose file or a folder, and with or
                # without a console behind.
                AxisDef(
                    "onefile",
                    ["single_file", "folder"],
                    "scope",
                    label="Empaquetado",
                    truthy="single_file",
                    labels={"single_file": "Un archivo", "folder": "Carpeta"},
                ),
                AxisDef(
                    "windowed",
                    ["console", "window"],
                    "scope",
                    label="Al ejecutarse",
                    truthy="window",
                    labels={"console": "Consola", "window": "Ventana"},
                ),
                _semver_axis(),
            ],
            steps=BUILD_BINARY_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="bump_version",
            name="Subir número de versión",
            group="Compilar",
            kind="once",
            icon="🏷️",
            description="Sube el número de versión del repo.",
            hidden=True,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="clean_artifacts",
            name="Borrar artefactos de build",
            group="Compilar",
            kind="destructive",
            icon="🧹",
            description="Borra cachés y basura de build del repo; en simulacro solo los lista.",
            axes=[
                AxisDef(
                    "families",
                    FAMILY_AXIS_VALUES,
                    "checks",
                    select="many",
                    label="Qué borrar",
                    labels=FAMILY_AXIS_LABELS,
                ),
                AxisDef(
                    "heavy",
                    HEAVY_AXIS_VALUES,
                    "checks",
                    select="many",
                    label="Pesados",
                    labels=HEAVY_AXIS_LABELS,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "apply",
                    ["dry_run", "delete"],
                    "scope",
                    label="Modo",
                    truthy="delete",
                    labels={"dry_run": "Simulacro", "delete": "Borrar"},
                ),
            ],
            stub=True,
        )
    )

    # --- Images ---
    #
    # Icons come from the repo's logo: Consola rasterizes it and leaves
    # it where each app takes it (the pubspec's
    # `flutter_launcher_icons`, the SPA's favicon). Unlike screenshots
    # no repo script is needed: the repo only supplies the SVG. Only
    # apps that say where their icon goes are offered (ADR-0055).
    registry.register(
        Capability(
            id="generate_icons",
            name="Generar íconos",
            group="Imágenes",
            kind="once",
            icon="🎨",
            description="Genera los íconos de las apps a partir del logo del repo.",
            axes=[AxisDef("apps", [], "checks", select="many", label="Apps", source=ICON_APPS)],
            stub=True,
        )
    )

    # The repo supplies the camera and Consola the development:
    # navigating the app, seeding its data and taking the PNG is the
    # repo's code (it imports its modules, knows its selectors);
    # converting each PNG to each destination's sizes is the same for
    # all. Consola passes the script which apps, themes and languages to
    # capture (`_shot_camera_axes`); the script decides which screens
    # exist.
    registry.register(
        Capability(
            id="shoot_screens",
            name="Sacar capturas",
            cut=True,
            group="Imágenes",
            kind="once",
            icon="📷",
            description="Corre la cámara del repo, que deja las capturas crudas de sus apps.",
            axes=_shot_camera_axes(),
            stub=True,
        )
    )
    # A destination is a preset of sizes and format (landing, stores,
    # social). Only the landing starts checked: stores publish now and
    # then, and their sizes have to be checked first against the current
    # listing.
    registry.register(
        Capability(
            id="render_shots",
            name="Revelar capturas",
            group="Imágenes",
            kind="once",
            icon="🎞️",
            description="Convierte las capturas crudas a las medidas y formatos de cada destino.",
            axes=[_shot_destinations_axis()],
            stub=True,
        )
    )
    # Both steps uncheck: without shooting, developing what is on disk
    # remains, for when a store's size changes and the app does not. The
    # same criterion as the builders' uncheckable compile.
    registry.register(
        Capability(
            id="screenshots",
            name="Capturar y publicar",
            cut=True,
            group="Imágenes",
            kind="once",
            icon="📸",
            level="C",
            description="Saca las capturas de las apps del repo y las deja listas en cada "
            "destino.",
            composed_of=["shoot_screens", "render_shots"],
            axes=[*_shot_camera_axes(), _shot_destinations_axis()],
            steps=SCREENSHOTS_STEPS,
            stub=True,
        )
    )

    # --- Repository ---
    #
    # Cloning is the catalog's only action that does not happen to the
    # open repo but to one that does not exist yet, so it is
    # `scope='machine'`: its fields save once and not per repository
    # (`ui/params_store.py`). An empty target folder means «next to the
    # repos already open»: the real target is almost always the folder
    # holding the tab's repo, and writing it by hand would write what is
    # already known.
    #
    # `opens_repo=True` is the button's end and no extra: cloning only
    # to then add the folder with «+» leaves the action halfway. The
    # catalog declares it and the window executes it, being the only one
    # that knows what a tab is.
    registry.register(
        Capability(
            id="clone_repo",
            name="Clonar repositorio de GitHub",
            group="Repositorio",
            kind="once",
            icon="📥",
            scope="machine",
            opens_repo=True,
            description="Clona un repositorio de GitHub y lo abre como pestaña.",
            axes=[
                AxisDef("url", [""], "field", label="URL del repositorio", required=True),
                AxisDef("dest", [""], "field", label="Carpeta destino"),
                AxisDef("branch", [""], "field", label="Rama"),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="sync_common_files",
            name="Copiar archivos comunes a otros repos",
            group="Repositorio",
            kind="destructive",
            icon="🔄",
            description="Copia los archivos compartidos a los otros repos; en simulacro solo "
            "compara.",
            axes=[
                AxisDef("targets", [""], "field", label="Repos destino", multiline=True),
                AxisDef("paths", [""], "field", label="Archivos a copiar", multiline=True),
                AxisDef(
                    "apply",
                    ["dry_run", "apply"],
                    "scope",
                    label="Modo",
                    truthy="apply",
                    labels={"dry_run": "Simulacro", "apply": "Aplicar"},
                ),
            ],
            stub=True,
        )
    )
    # The two forced operations exist for when someone already decided
    # one side wins anyway. They run only on this machine: the VPS has
    # no clone of the repo (ADR-0061).
    registry.register(
        Capability(
            id="git_force_push",
            name="Force push",
            cut=True,
            group="Repositorio",
            kind="destructive",
            icon="⏫",
            description="Empuja a origin con --force la rama de esta máquina, aunque haya "
            "divergido.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="git_force_reset",
            name="Force reset",
            group="Repositorio",
            kind="destructive",
            icon="⏬",
            description="Descarta los commits y los cambios de esta máquina para dejarla igual "
            "a origin.",
            axes=[
                AxisDef(
                    "discard_changes",
                    ["ask", "discard"],
                    "scope",
                    label="Si hay cambios sin commitear",
                    truthy="discard",
                    danger={"discard"},
                    labels={"ask": "Preguntar", "discard": "Descartar"},
                )
            ],
            stub=True,
        )
    )

    # --- Database ---
    #
    # The buttons without a `scope` axis act only on the local database.
    # On the VPS `install.py` creates the database and its extensions,
    # `deploy.py` migrates, canone's receiver backs it up (ADR-0060) and
    # `database.py` empties and seeds it.
    registry.register(
        Capability(
            id="bootstrap_db",
            name="Configurar base de datos",
            group="Base de datos",
            kind="once",
            icon="🏗️",
            description="Deja la base local usable desde cero: creada, migrada y con sus datos "
            "mínimos.",
            steps=BOOTSTRAP_DB_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="enable_extensions",
            name="Habilitar extensiones",
            group="Base de datos",
            kind="once",
            icon="🧩",
            description="Crea en la base local las extensiones de Postgres que declara el repo.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="migrate_db",
            name="Correr migraciones",
            group="Base de datos",
            kind="once",
            icon="📐",
            requires_repo=targets.MIGRATIONS,
            description="Genera la migración pendiente y la aplica en la base local.",
            steps=MIGRATE_DB_STEPS,
            stub=True,
        )
    )
    # On the VPS they run `database.py seed`, with `--mock` only on a
    # machine in development.
    registry.register(
        Capability(
            id="run_seeders",
            name="Correr seeders",
            cut=True,
            group="Base de datos",
            kind="once",
            icon="🌱",
            description="Carga los datos mínimos que la app necesita para arrancar.",
            axes=[_scope_axis()],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="run_mock_seeders",
            name="Correr mock seeders",
            group="Base de datos",
            kind="once",
            icon="🎭",
            description="Carga datos de prueba encima de los datos base.",
            axes=[_scope_axis()],
            stub=True,
        )
    )
    # Live like a launcher: it holds the connection, and on remote the
    # tunnel, until the tab closes, and it delivers the tree and data
    # view, not the log (ADR-0015). On the VPS it enters as
    # `<app>_read`.
    registry.register(
        Capability(
            id="explore_db",
            name="Explorar datos",
            cut=True,
            group="Base de datos",
            kind="live",
            view="db",
            icon="🗂️",
            description="Navega esquemas, tablas y datos de la base, en solo lectura.",
            axes=[_scope_axis()],
            stub=True,
        )
    )
    # The tunnel has no parameters: it goes to the socket of the VPS's
    # PostgreSQL, enters as `<app>_read`, and `core/ports.py` chooses
    # the local port if 5432 is taken.
    registry.register(
        Capability(
            id="ssh_tunnel",
            name="Abrir túnel a Postgres",
            group="Base de datos",
            kind="background",
            icon="🔗",
            description="Abre un túnel SSH al Postgres del VPS para leerlo en local.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="backup_db",
            name="Respaldar base de datos",
            group="Base de datos",
            kind="once",
            icon="💾",
            description="Vuelca la base local a un archivo y rota los respaldos viejos.",
            stub=True,
        )
    )
    # Destructive: it overwrites the whole database with the dump. The
    # backup list is not enumerated and does not come from the repo: it
    # comes from looking at `BACKUP_DIR`, which may be outside the
    # working tree (ADR-0047).
    registry.register(
        Capability(
            id="restore_db",
            name="Restaurar base de datos",
            group="Base de datos",
            kind="destructive",
            icon="♻️",
            description="Carga un respaldo sobre la base local, reemplazando lo que haya.",
            axes=[AxisDef("dump", [], "pick", label="Respaldo", source=BACKUP_FILES)],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="rebuild_db",
            name="Reconstruir base",
            group="Base de datos",
            kind="destructive",
            icon="🔁",
            description="Vacía la base y vuelve a llenarla: migraciones y seeders.",
            axes=[_scope_axis()],
            steps=REBUILD_DB_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="reinit_migrations",
            name="Reiniciar historial de migraciones",
            group="Base de datos",
            kind="destructive",
            icon="🧨",
            requires_repo=targets.MIGRATIONS,
            description="Reinicia el historial de migraciones: deja una sola inicial con los "
            "modelos de hoy.",
            steps=REINIT_MIGRATIONS_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="teardown_db",
            name="Borrar base y rol",
            group="Base de datos",
            kind="destructive",
            icon="💥",
            description="Borra la base local de la aplicación y su rol.",
            steps=TEARDOWN_DB_STEPS,
            stub=True,
        )
    )

    # --- Deployment ---
    #
    # canone's versions and the two buttons operating the services
    # already on the VPS (ADR-0059).
    #
    # One axis and not two: `systemd_action` receives ONE parameter. The
    # default is 'status', the signature's, and not 'start': the value
    # starting checked is what runs if someone presses Run without
    # looking.
    registry.register(
        Capability(
            id="systemd_action",
            name="Control del servicio",
            group="Despliegue",
            kind="once",
            icon="⚙️",
            description="Manda una acción al servicio systemd elegido en el VPS.",
            axes=[
                _service_axis(),
                AxisDef(
                    "action",
                    [
                        "status",
                        "start",
                        "stop",
                        "restart",
                        "enable",
                        "disable",
                        "reload",
                        "is-active",
                        "is-enabled",
                    ],
                    "buttons",
                    label="Acción",
                    default="status",
                    danger={"stop"},
                ),
            ],
            stub=True,
        )
    )
    # `follow` is a boolean, not a free text field.
    registry.register(
        Capability(
            id="view_logs",
            name="Ver logs del servicio",
            group="Despliegue",
            kind="live",
            icon="📋",
            description="Muestra el journal del servicio elegido, de una o siguiéndolo en vivo.",
            axes=[
                _service_axis(),
                AxisDef(
                    "follow",
                    ["follow", "once"],
                    "scope",
                    label="Modo",
                    truthy="follow",
                    labels={"follow": "Seguir en vivo", "once": "De una"},
                ),
            ],
            stub=True,
        )
    )
    # Versions (ADR-0059): a tag the repo's `release.yml` publishes,
    # signed on this machine and installed by canone's `deploy.py`.
    registry.register(
        Capability(
            id="publish_release",
            name="Publicar versión",
            group="Despliegue",
            kind="once",
            icon="🏷️",
            description="Crea el tag siguiente, espera a release.yml, firma el release y lo "
            "despliega.",
            axes=[
                AxisDef(
                    "part",
                    list(canone.PARTS),
                    "scope",
                    label="Sube",
                    default="patch",
                    labels={"major": "Major", "minor": "Minor", "patch": "Patch"},
                )
            ],
            steps=PUBLISH_RELEASE_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="deploy_version",
            name="Desplegar versión",
            group="Despliegue",
            kind="once",
            icon="🚢",
            description="Instala en el VPS un release ya firmado.",
            axes=[AxisDef("version", [], "pick", label="Versión", source=RELEASES)],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="upload_to_vps",
            name="Subir artefacto al VPS",
            group="Despliegue",
            kind="once",
            icon="📤",
            description="Copia el artefacto compilado al VPS.",
            hidden=True,
            stub=True,
        )
    )

    # --- VPS ---
    #
    # What installs and how comes from the repo (ADR-0059): there are no
    # axes to choose.
    registry.register(
        Capability(
            id="bootstrap_vps",
            name="Configurar VPS",
            group="VPS",
            kind="once",
            icon="🚀",
            description="Deja el VPS listo con los programas de canone: paquetes, swap, "
            "install.py, credenciales y el último release.",
            preview=PACKAGES,
            steps=BOOTSTRAP_VPS_STEPS,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_software",
            name="Instalar paquetes base",
            cut=True,
            group="VPS",
            kind="once",
            icon="📦",
            description="Instala en el VPS los paquetes que pide canone para este repo, y uv.",
            preview=PACKAGES,
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="load_credentials",
            name="Cargar credenciales",
            group="VPS",
            kind="once",
            icon="🔐",
            description="Pasa las credenciales de config.env a credentials.py de canone.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="refresh_known_host",
            name="Refrescar known_hosts",
            group="VPS",
            kind="once",
            icon="🔄",
            description="Borra del known_hosts de esta máquina la huella vieja del VPS.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="update_cloudflare",
            name="Actualizar Cloudflare",
            group="VPS",
            kind="once",
            icon="☁️",
            description="Apunta el registro DNS de Cloudflare a la IP del VPS, a la pública "
            "de esta máquina o a otra escrita.",
            axes=[
                AxisDef(
                    "ip_mode",
                    ["vps", "detect", "static"],
                    "scope",
                    label="IP",
                    default="vps",
                    labels={
                        "vps": "La del VPS",
                        "detect": "La pública de esta máquina",
                        "static": "Otra",
                    },
                    requires_env={"vps": {"VPS_IP"}},
                ),
                # Read only with «Otra»: `update_cloudflare` stops if
                # that is chosen and it is empty.
                AxisDef("custom_ip", [""], "field", label="Otra IP"),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="health_check",
            name="Health check",
            cut=True,
            group="VPS",
            kind="once",
            icon="❤️",
            description="Comprueba que el VPS responde y el servicio está arriba.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="view_events",
            name="Ver eventos",
            group="VPS",
            kind="once",
            icon="📊",
            description="Muestra los últimos eventos, el último respaldo y el disco del servidor.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="run_command",
            name="Ejecutar comando",
            group="VPS",
            kind="once",
            icon="💻",
            description="Corre un comando suelto en el VPS y trae su salida.",
            axes=[AxisDef("command", [""], "field", label="Comando")],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="ssh_login",
            name="Abrir sesión SSH",
            group="VPS",
            kind="interactive",
            icon="🔑",
            description="Abre una sesión SSH interactiva contra el VPS del repo.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="revoke_ssh",
            name="Quitar acceso SSH",
            group="VPS",
            kind="destructive",
            icon="🔓",
            description="Quita del VPS la clave pública con la que entra esta máquina.",
            steps=REVOKE_SSH_STEPS,
            stub=True,
        )
    )
    # canone's `uninstall.py` does it, not Consola (ADR-0083). Each
    # level includes the one before; the default is the smallest.
    registry.register(
        Capability(
            id="clean_vps",
            name="Vaciar VPS",
            group="VPS",
            kind="destructive",
            icon="🧨",
            description="Deshace en el VPS lo que instaló canone: la base, la app o la máquina, "
            "salvo los paquetes; en simulacro solo lo lista.",
            axes=[
                AxisDef(
                    "level",
                    ["database", "app", "machine"],
                    "scope",
                    label="Nivel",
                    default="database",
                    labels={
                        "database": "La base",
                        "app": "La app",
                        "machine": "La máquina",
                    },
                ),
                AxisDef(
                    "apply",
                    ["dry_run", "delete"],
                    "scope",
                    label="Modo",
                    truthy="delete",
                    labels={"dry_run": "Simulacro", "delete": "Borrar"},
                ),
            ],
            stub=True,
        )
    )

    # --- Emulators ---
    #
    # The four buttons belong to the machine, not the repo: an AVD
    # serves any project, like the SDK. Installing the virtual machine,
    # creating the AVD and starting it are three buttons, because each
    # has its own catalog of options: a step with options of its own no
    # longer fits in a checkbox (ADR-0027).
    registry.register(
        Capability(
            id="install_system_image",
            name="Instalar imagen de sistema",
            group="Emuladores",
            kind="once",
            icon="💿",
            scope="machine",
            description="Descarga del SDK la máquina virtual (system image) que va a correr el "
            "AVD.",
            axes=[
                AxisDef(
                    "image",
                    [],
                    "pick",
                    label="Máquina virtual",
                    source=ANDROID_IMAGES,
                    facets=_IMAGE_FACETS,
                )
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="create_avd",
            name="Crear AVD",
            group="Emuladores",
            kind="once",
            icon="🧱",
            scope="machine",
            description="Crea el dispositivo virtual eligiéndolo del catálogo del SDK.",
            axes=[
                AxisDef("device", [], "pick", label="Dispositivo", source=ANDROID_DEVICES),
                # No `facets`, unlike «Instalar máquina»: here the list
                # is what is downloaded, almost always one or two.
                # Splitting two entries in three lists saves no reading
                # and suggests a catalog behind: the control's shape
                # would say something false about how many options there
                # are.
                AxisDef(
                    "image",
                    [],
                    "pick",
                    label="Máquina virtual (instaladas)",
                    source=ANDROID_IMAGES_INSTALLED,
                ),
            ],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="launch_emulator",
            name="Abrir emulador",
            group="Emuladores",
            kind="live",
            icon="📲",
            scope="machine",
            description="Arranca uno de los AVD ya creados y sigue su salida.",
            axes=[
                AxisDef("avd", [], "pick", label="AVD", source=ANDROID_AVDS),
                AxisDef(
                    "wipe",
                    ["normal", "wipe_data"],
                    "scope",
                    label="Arranque",
                    truthy="wipe_data",
                    danger={"wipe_data"},
                    labels={"normal": "Normal", "wipe_data": "Borrar datos"},
                ),
                # The three flags truly written. A yes or no choice,
                # which is exactly a checkbox. The flag's name IS the
                # value: so no translating table is needed, and
                # `core/tasks/emulators.py` adds them as they are.
                AxisDef(
                    "boot_flags",
                    ["-no-snapshot-load", "-no-snapshot-save", "-no-window"],
                    "checks",
                    select="many",
                    checked_by_default=False,
                    allow_empty=True,
                    label="Opciones de arranque",
                    labels={
                        "-no-snapshot-load": "Arranque en frío (ignora el snapshot)",
                        "-no-snapshot-save": "No guardar el snapshot al cerrar",
                        "-no-window": "Sin ventana (headless, solo adb)",
                    },
                ),
                # Rendering is exclusive, not a checkbox: asking for
                # host and software at once means nothing.
                AxisDef(
                    "gpu",
                    ["host", "software"],
                    "scope",
                    label="GPU",
                    labels={"host": "Host (GPU real)", "software": "Software (swiftshader)"},
                ),
                # What is left of the command line, for a flag not above
                # (`-memory 4096`, `-http-proxy ...`). It adds to the
                # checkboxes and `core/android.py`'s usual flags
                # (`-no-boot-anim`, `-netdelay none`) instead of
                # replacing them. One line because it is a command line:
                # it splits in tokens as a shell would, and `-memory
                # 4096` is two.
                AxisDef("flags", [""], "field", label="Flags extra del emulador"),
            ],
            live_state=ANDROID_RUNNING,
            stub=True,
        )
    )
    # Hidden atomic capabilities.
    #
    # Stopping is no rail button: closing the emulator's tab stops it,
    # and for orphans, an emulator from an earlier session or started
    # from Android Studio, there is the panel's status header ✕, where
    # they show. It stays a capability because the runner runs it like
    # any other, with its log in the console.
    registry.register(
        Capability(
            id="stop_emulator",
            name="Apagar emulador",
            group="Emuladores",
            kind="once",
            icon="⏹",
            scope="machine",
            description="Apaga por adb el emulador indicado.",
            # No panel draws for this capability, but the axis is
            # declared anyway: it is the only way the serial the ✕
            # passes reaches the function. The declaration is the
            # contract, whether or not anyone drew it.
            axes=[AxisDef("serial", [], "pick", label="Emulador", source=ANDROID_RUNNING)],
            hidden=True,
            stub=True,
        )
    )
    # One cleaning button for the two things taking disk: the AVD weighs
    # hundreds of MB and the virtual machine several GB. Deleting one is
    # checking a box, not another button (ADR-0004).
    registry.register(
        Capability(
            id="purge_emulators",
            name="Borrar AVDs e imágenes",
            group="Emuladores",
            kind="destructive",
            icon="🗑️",
            scope="machine",
            description="Borra AVD y máquinas virtuales; en simulacro solo los lista con su "
            "tamaño.",
            axes=[
                AxisDef(
                    "avds",
                    [],
                    "checks",
                    select="many",
                    label="AVD",
                    source=ANDROID_AVDS,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "images",
                    [],
                    "checks",
                    select="many",
                    label="Máquinas virtuales",
                    source=ANDROID_IMAGES_INSTALLED,
                    checked_by_default=False,
                    allow_empty=True,
                ),
                AxisDef(
                    "apply",
                    ["dry_run", "delete"],
                    "scope",
                    label="Modo",
                    truthy="delete",
                    labels={"dry_run": "Simulacro", "delete": "Borrar"},
                ),
            ],
            stub=True,
        )
    )

    # --- SDKs ---
    registry.register(
        Capability(
            id="install_android_sdk",
            name="Instalar SDK de Android",
            group="SDKs",
            kind="once",
            icon="🤖",
            scope="machine",
            description="Deja esta máquina lista para compilar y emular Android.",
            composed_of=[
                "install_android_tools",
                "install_android_packages",
                "install_android_hypervisor",
            ],
            axes=[
                AxisDef("install_dir", [ANDROID_DIR_DEFAULT], "field", label="Directorio"),
                *ANDROID_PACKAGE_AXES,
            ],
            steps=INSTALL_ANDROID_SDK_STEPS,
            stub=True,
        )
    )
    # The SDKs belong to the machine, not the open repo:
    # `scope='machine'`. The install splits in three atomic capabilities
    # because adding packages is what repeats (a new API, another
    # build-tools), and it need not drag the SDK's download or touch the
    # PATH.
    registry.register(
        Capability(
            id="install_android_tools",
            name="Instalar command-line tools",
            cut=True,
            group="SDKs",
            kind="once",
            icon="🧰",
            scope="machine",
            description="Descarga las command-line tools del SDK y las deja en el entorno del "
            "usuario.",
            axes=[AxisDef("install_dir", [ANDROID_DIR_DEFAULT], "field", label="Directorio")],
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_android_packages",
            name="Instalar paquetes del SDK",
            group="SDKs",
            kind="once",
            icon="📦",
            scope="machine",
            description="Acepta las licencias e instala en el SDK los paquetes que falten.",
            axes=list(ANDROID_PACKAGE_AXES),
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_android_hypervisor",
            name="Instalar aceleración del emulador",
            group="SDKs",
            kind="once",
            icon="⚡",
            scope="machine",
            description="Verifica la virtualización que el emulador necesita, y en Windows "
            "instala el driver.",
            stub=True,
        )
    )
    registry.register(
        Capability(
            id="install_flutter_sdk",
            name="Instalar SDK de Flutter",
            cut=True,
            group="SDKs",
            kind="once",
            icon="🦋",
            scope="machine",
            description="Descarga el canal stable de Flutter y lo deja en el entorno del usuario.",
            axes=[AxisDef("install_dir", [FLUTTER_DIR_DEFAULT], "field", label="Directorio")],
            stub=True,
        )
    )
