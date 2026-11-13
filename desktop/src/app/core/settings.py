"""The schema of the configuration keys."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Setting:
    """A key of `.consola/config.env`, declared only once.

    It has two consumers (ADR-0064): the Settings form and the check
    beforehand that marks in amber what an action lacks.
    """

    key: str
    group: str
    label: str = ""
    secret: bool = False
    default: str = ""
    # The default, written by hand, for when there is no
    default_hint: str = ""
    # `default` to set: what happens with an empty field is not a value
    # to save but where something else leaves it (each framework's build
    # folder). It shows as a watermark like a resolved default, so only
    # what will actually be used goes here: an explanation of what goes
    # in the field would read as a loaded value.
    # 'text' | 'list'. 'list' is a multi-line field: one entry per line,
    # saved separated by commas.
    kind: str = "text"
    # 'repo' = goes to `.consola/config.env`, because the value is the
    # project's. 'machine' = goes to QSettings, because the value is
    # THIS machine's and writing it in each repo would be writing the
    # same thing nine times.
    scope: str = "repo"
    # (`ui/params_store.py::machine_env`).
    required_by: tuple[str, ...] = field(default_factory=tuple)
    # Actions that USE the key but run without it. It appears in those
    # actions' filtered settings panel and does not block their button.
    # The difference matters: `serve_backend` never reads `API_URL`;
    # `compile_flutter` does and asks for it per step, so requiring it
    # left Backend amber for a key it would never look at
    # (docs/arquitectura/13_configuracion_y_persistencia.md).
    used_by: tuple[str, ...] = field(default_factory=tuple)
    # The `Settings` field the repo declares when the key applies to it:
    # `TURN_IP` only means something to an app with calls, the one that
    # reads `turn_secret` (ADR-0085). Without it, the form does not show
    # the key (`ui/env_panel.py`).
    needs: str = ""

    @property
    def display(self) -> str:
        """Return how the key reads in the form."""
        return self.label or self.key


# VPS keys any operation reaching the server needs.
_VPS_REACH = (
    "ssh_login",
    "health_check",
    "run_command",
    "upload_to_vps",
    "install_software",
    "bootstrap_vps",
    "load_credentials",
    "deploy_version",
    "view_logs",
    "systemd_action",
    "revoke_ssh",
    "clean_vps",
    "view_events",
    "ssh_tunnel",
)
# «Publicar versión» asks for them per step
# (`core/catalog.py::PUBLISH_RELEASE_STEPS`): creating the tag does not
# reach the VPS.
_VPS_STEPS = ("publish_release",)

# Only those of the database without a `scope` axis: those with one
# declare their keys on the axis (`core/catalog.py::_scope_axis`), since
# they depend on the chosen scope. These go always to the local
# database (ADR-0060). The tunnel goes to the VPS, without them.
_DB_FIXED = (
    "bootstrap_db",
    "migrate_db",
    "backup_db",
    "restore_db",
    "enable_extensions",
    "reinit_migrations",
    "teardown_db",
)
# Those that run SQL as the local superuser. «Reconstruir base» asks for
# them in its «Borrar tablas» step, which exists only locally.
_PG_FIXED = ("bootstrap_db", "teardown_db", "enable_extensions", "reinit_migrations")

SETTINGS: tuple[Setting, ...] = (
    # --- Server ---
    #
    # The Flutter build requires it, compiling it inside the app.
    # `run_mobile` falls back on this session's backend URL if empty.
    Setting(
        "API_URL",
        "Server",
        "URL publica de la API",
        required_by=("build_flutter",),
        used_by=("backend", "run_mobile"),
    ),
    # --- Cloudflare ---
    Setting(
        "CF_API_TOKEN", "Cloudflare", "API token", secret=True, required_by=("update_cloudflare",)
    ),
    Setting("CF_DOMAIN_NAME", "Cloudflare", "Dominio", required_by=("update_cloudflare",)),
    Setting("CF_RECORD_NAME", "Cloudflare", "Registro DNS", required_by=("update_cloudflare",)),
    # --- VPS ---
    # «Refrescar known_hosts» only forgets this host in known_hosts:
    # it needs the IP, not the account nor the key.
    Setting(
        "VPS_IP",
        "VPS",
        "IP del servidor",
        required_by=(*_VPS_REACH, "refresh_known_host"),
        used_by=_VPS_STEPS,
    ),
    Setting(
        "ROOT_USER",
        "VPS",
        "Usuario root",
        default="root",
        required_by=("install_software", "bootstrap_vps"),
    ),
    # The password of the provider, for the first entry only: «Poner la
    # llave» enters with it once and leaves the key. Empty, it is asked.
    # After `install.py` root no longer enters.
    Setting("ROOT_PASSWORD", "VPS", "Contraseña de root", secret=True, used_by=("bootstrap_vps",)),
    # The account that administers the VPS: the `--admin` of
    # `install.py`. No default, because canone does not let it be named
    # like the app (ADR-0087 of canone).
    Setting(
        "VPS_USER", "VPS", "Usuario de despliegue", required_by=_VPS_REACH, used_by=_VPS_STEPS
    ),
    # That account's password, which `sudo` asks for. Empty, Consola
    # asks once per session and keeps it only in memory.
    Setting(
        "SUDO_PASSWORD",
        "VPS",
        "Contraseña de sudo",
        secret=True,
        used_by=(
            "install_software",
            "bootstrap_vps",
            "load_credentials",
            "publish_release",
            "deploy_version",
            "systemd_action",
            "view_logs",
            "rebuild_db",
            "run_seeders",
            "run_mock_seeders",
            "health_check",
            "clean_vps",
        ),
    ),
    Setting(
        "VPS_KEY_NAME", "VPS", "Nombre de la llave SSH", required_by=_VPS_REACH, used_by=_VPS_STEPS
    ),
    Setting("VPS_DEPLOY_DIR", "VPS", "Directorio de despliegue", required_by=("upload_to_vps",)),
    # The arguments of `install.py` that change between deployments
    # (ADR-0063). The domain is the landing's; the other pieces hang
    # from it (`app.<domain>`, `panel.<domain>`).
    Setting("DOMAIN", "VPS", "Dominio", used_by=("bootstrap_vps",)),
    # Its Valkey's `maxmemory`, like `256mb`. It wins: empty,
    # «Configurar VPS» computes it with `VALKEY_PERCENT` of the VPS's
    # memory (ADR-0086).
    Setting(
        "VALKEY_MEMORY",
        "VPS",
        "Memoria de Valkey",
        default_hint="el % de RAM de abajo, al configurar",
        used_by=("bootstrap_vps",),
    ),
    # Only for computing `VALKEY_MEMORY` when it is empty. Valkey fixes
    # no share of a machine it shares with PostgreSQL and the server:
    # an eighth leaves a quarter at most while it saves its `.rdb`,
    # which may double it.
    Setting(
        "VALKEY_PERCENT", "VPS", "% de RAM para Valkey", default="12.5", used_by=("bootstrap_vps",)
    ),
    # `--turn-ip`: the public IPv4, when the interface only has a
    # private one. `--turn` is no key: it goes when the repo's Settings
    # declares `turn_secret` (`canone.calls`, ADR-0085).
    Setting(
        "TURN_IP", "VPS", "IP pública para TURN", used_by=("bootstrap_vps",), needs="turn_secret"
    ),
    # `--logs-ip`: the address Equipaggio gave this machine. The
    # destination and key are Equipaggio's, and go in the Machine group.
    Setting(
        "LOGS_IP", "VPS", "IP del túnel de logs", used_by=("bootstrap_vps", "install_software")
    ),
    # --- Database ---
    #
    # The local database's, save `DB_EXTENSIONS`, which is also the
    # VPS's: the database buttons reach the VPS's through canone's
    # `database.py`, which reads none of the others (ADR-0082).
    #
    # Empty, the role is the deployment user itself
    # (`Config._dynamic_default`).
    Setting("DB_USER", "Base de datos", "Rol de la base", required_by=_DB_FIXED),
    Setting("DB_NAME", "Base de datos", "Base de datos", required_by=_DB_FIXED),
    Setting(
        "DB_PASSWORD", "Base de datos", "Password de la base", secret=True, required_by=_DB_FIXED
    ),
    # Where `backup_db` dumps fall and where `restore_db` reads them
    # from. Relative resolves against the repo's root; absolute is used
    # as is, which lets them leave the repo: `.backups/` is in no
    # `.gitignore` by default, and a dump with real data stays ready to
    # commit with no warning.
    #
    # `used_by` and not `required_by`: both have a `default`, and a key
    # with a default never counts as missing (`Config.get`), so
    # requiring them would leave no button amber. `used_by` makes them
    # appear in these two buttons' filtered settings panel.
    Setting(
        "BACKUP_DIR",
        "Base de datos",
        "Carpeta de respaldos",
        default=".backups",
        used_by=("backup_db", "restore_db"),
    ),
    # How many dumps survive rotation. Configuration and not an axis by
    # the same criterion as `DB_EXTENSIONS`: a datum the task reads, not
    # a decision of the run. How many backups a project keeps does not
    # change between two presses of the button.
    Setting(
        "BACKUP_KEEP",
        "Base de datos",
        "Respaldos a conservar",
        default="7",
        used_by=("backup_db",),
    ),
    Setting(
        "PG_SUPERUSER",
        "Base de datos",
        "Superusuario Postgres",
        default="postgres",
        required_by=_PG_FIXED,
    ),
    Setting(
        "PG_PASSWORD",
        "Base de datos",
        "Password del superusuario",
        secret=True,
        required_by=_PG_FIXED,
    ),
    # Configuration and not a run parameter: which extensions the schema
    # needs is a property of the project. It comes from no Postgres
    # catalog, since `pg_available_extensions` says what CAN be created
    # (hundreds with contrib) and `pg_extension` what IS created, nor
    # from migrations, which with `--autogenerate` never write a `CREATE
    # EXTENSION`. It is declared.
    #
    # No default: an empty list means none. canone installs PostGIS only
    # if the app uses it, and an extension nobody uses would land in
    # every VPS (ADR-0071).
    Setting(
        "DB_EXTENSIONS",
        "Base de datos",
        "Extensiones de Postgres",
        kind="list",
        # Also the VPS's: PostGIS's package (`canone.packages`) and
        # `--extension` of `install.py` come from here.
        used_by=("bootstrap_db", "enable_extensions", "install_software", "bootstrap_vps"),
    ),
    # --- GitHub ---
    #
    # The repo's name on the VPS comes from it (`vps.repo_name`).
    Setting("GIT_REPO_URL", "GitHub", "URL del repositorio", used_by=("upload_to_vps",)),
    # `--private`: the VPS downloads the release with a token. `si` or
    # `no`.
    Setting("PRIVATE", "GitHub", "Repo privado", used_by=("bootstrap_vps", "load_credentials")),
    # --- Credentials ---
    #
    # The two `credentials.py` receives with a fixed name, besides the
    # repo's `Settings` fields, added to this group on opening it
    # (`core/fields.py`, ADR-0063).
    #
    # The local database of a canone repo: `app_database_url` of its
    # development credentials (ADR-0069). On the VPS `install.py` writes
    # it.
    Setting(
        "DATABASE_URL",
        "Credenciales",
        "Base de desarrollo",
        secret=True,
        used_by=("backend", "migrate_db"),
    ),
    Setting(
        "RESTIC_PASSWORD",
        "Credenciales",
        "Contraseña de restic",
        secret=True,
        required_by=("load_credentials",),
    ),
    # The read-only token the VPS downloads a private repo's release
    # with.
    Setting(
        "GITHUB_TOKEN",
        "Credenciales",
        "Token de GitHub",
        secret=True,
        used_by=("load_credentials",),
    ),
    # --- Server ---
    Setting(
        "SERVER_DIR",
        "Server",
        "Carpeta del server",
        default="server",
        used_by=("load_credentials",),
    ),
    # --- Builds ---
    #
    # Where each `build_flutter` build lands, relative to the app's
    # folder. Empty, where the framework leaves it: the watermark says
    # which. With a value, the build copies there. No `used_by`: each
    # platform's checkbox claims them (`AxisDef.uses_env` of the
    # catalog), and only those of the checked platforms show.
    *(
        Setting(f"BUILD_OUT_{key}", "Builds", f"Carpeta del build {name}", default_hint=default)
        for key, name, default in (
            ("APK", "APK", "build/app/outputs/flutter-apk · en Flet: build/apk"),
            ("AAB", "AAB", "build/app/outputs/bundle/release · en Flet: build/aab"),
            ("WEB", "web", "build/web"),
            ("WINDOWS", "Windows", "build/windows/x64/runner/Release · en Flet: build/windows"),
            ("LINUX", "Linux", "build/linux/x64/release/bundle · en Flet: build/linux"),
            ("MACOS", "macOS", "build/macos/Build/Products/Release · en Flet: build/macos"),
            ("IPA", "iOS", "build/ios/ipa · en Flet: build/ipa"),
        )
    ),
    # --- Brand ---
    #
    # The logo belongs to the repo and Consola rasterizes it for each
    # app and the executable. No default: a repo without a logo has no
    # icons to generate. By convention the three SVGs live in `brand/`
    # (ADR-0056).
    Setting(
        "BRAND_ICON",
        "Marca",
        "Logo (SVG)",
        required_by=("generate_icons",),
        used_by=("build_binary",),
    ),
    # The front layer of Android's adaptive icon: the same logo, with
    # the margin the system's crop demands. Only the Flutter app whose
    # pubspec declares `adaptive_icon_foreground` asks for it, and there
    # missing is an error.
    Setting(
        "BRAND_ICON_FOREGROUND", "Marca", "Capa frontal Android (SVG)", used_by=("generate_icons",)
    ),
    # A PWA's maskable icon: a full-bleed background and the logo inside
    # the central 80 % circle, which Android does not crop. Only the SPA
    # whose manifest declares a `maskable` icon asks for it.
    Setting(
        "BRAND_ICON_MASKABLE", "Marca", "Ícono maskable de PWA (SVG)", used_by=("generate_icons",)
    ),
    # --- Screenshots ---
    #
    # The camera is a script of the repo (Playwright, `flutter drive`):
    # Consola runs it and does not ask what it does inside. No default:
    # no repo has a camera until it writes one. It only runs with
    # Consola's kit, so it goes in .consola/camera/, versioned, and what
    # it generates in .consola/capturas/ and .consola/publicables/,
    # which .consola/.gitignore ignores (ADR-0087).
    Setting("SHOTS_CMD", "Capturas", "Comando para capturas", required_by=("shoot_screens",)),
    Setting(
        "SHOTS_RAW",
        "Capturas",
        "Carpeta de capturas crudas",
        default=".consola/capturas",
        used_by=("shoot_screens", "render_shots", "screenshots"),
    ),
    Setting(
        "SHOTS_PUBLISH",
        "Capturas",
        "Carpeta de la landing",
        default="landing/static/capturas",
        used_by=("render_shots", "screenshots"),
    ),
    # Any destination that is not the landing (stores, manual, social,
    # press kit): one folder per destination, with its manifest. They
    # are deliverables, not the site's.
    Setting(
        "SHOTS_DIST",
        "Capturas",
        "Carpeta de los demás destinos",
        default=".consola/publicables",
        used_by=("render_shots", "screenshots"),
    ),
    # --- Machine ---
    #
    # `pip install pyinstaller` leaves the executable in the user's
    # Scripts, which on Windows is not always on the PATH. It does not
    # block the button: empty, it looks first in the app's venv and then
    # the PATH.
    #
    # `scope='machine'`: where an executable got installed belongs to
    # the machine, not the project. In `config.env` the same path would
    # be written in each repo, and nine copies of a datum are eight
    # chances to disagree.
    Setting(
        "PYINSTALLER_BIN",
        "Máquina",
        "Ruta de PyInstaller",
        default_hint="venv de la app, si no el PATH",
        scope="machine",
        used_by=("build_binary",),
    ),
    # The public key kept off this machine (a physical key, for
    # example): with `VPS_KEY_NAME`'s, they are the two `--key` and two
    # `--signer` of `install.py`. It is one for all VPSs.
    Setting(
        "OFFLINE_KEY",
        "Máquina",
        "Llave pública guardada fuera",
        scope="machine",
        used_by=("bootstrap_vps",),
    ),
    # The local canone copy: the programs Consola uploads to the VPS
    # come from its `plantilla/infra/` (ADR-0059).
    Setting(
        "CANONE_DIR",
        "Máquina",
        "Carpeta de canone",
        scope="machine",
        required_by=(
            "install_software",
            "bootstrap_vps",
            "load_credentials",
            "clean_vps",
            "create_spa",
        ),
    ),
    # `--logs` and `--logs-key`: Equipaggio's WireGuard endpoint and its
    # public key. They are the same for all VPSs sending it their
    # journal.
    Setting(
        "LOGS",
        "Máquina",
        "Destino de logs",
        scope="machine",
        used_by=("bootstrap_vps", "install_software"),
    ),
    Setting("LOGS_KEY", "Máquina", "Llave de logs", scope="machine", used_by=("bootstrap_vps",)),
)

GROUP_ORDER = (
    "Server",
    "Cloudflare",
    "VPS",
    "Base de datos",
    "GitHub",
    "Credenciales",
    "Builds",
    "Marca",
    "Capturas",
    "Máquina",
)

# The repo's guards (`PROTECT_*`) are NOT here and are no `Setting`:
# they are no datum a task consumes, since no step reads one, but a
# console decision about this repo, and they live with the others in
# `.consola/params.json` (`ui/security_panel.py`,
# `ui/params_store.py::load_protection`).


def repo_settings() -> tuple[Setting, ...]:
    """Return those written in `.consola/config.env`.

    That is what regenerates the file (`core/envfile.py`): a machine key
    there would be a project datum that is not the project's.
    """
    return tuple(s for s in SETTINGS if s.scope == "repo")


def machine_settings() -> tuple[Setting, ...]:
    """Return those saved in QSettings."""
    return tuple(s for s in SETTINGS if s.scope == "machine")


def settings_by_group(fields: tuple[Setting, ...] = ()) -> dict[str, list[Setting]]:
    """Return the schema by group.

    With the repo's `Settings` fields if given.
    """
    groups: dict[str, list[Setting]] = {g: [] for g in GROUP_ORDER}
    for s in (*SETTINGS, *fields):
        groups.setdefault(s.group, []).append(s)
    return {g: items for g, items in groups.items() if items}


def get_setting(key: str) -> Setting | None:
    """Return the key's declaration, if any."""
    for s in SETTINGS:
        if s.key == key:
            return s
    return None


def required_keys_for(capability_id: str) -> list[str]:
    """Return those without which the action cannot run.

    Its button stays amber.
    """
    return [s.key for s in SETTINGS if capability_id in s.required_by]


def relevant_keys_for(capability_id: str) -> list[str]:
    """Return those the action may come to look at, required or not.

    That filters the settings panel: `API_URL` not blocking Backend does
    not mean it is not where one looks for it with that tab open.
    """
    return [
        s.key for s in SETTINGS if capability_id in s.required_by or capability_id in s.used_by
    ]
