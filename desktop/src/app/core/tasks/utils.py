"""Utils group.

What crosses everything: clean artifacts, update DNS, sync common files
between repos and install the SDKs. All destructive tasks here share one
pattern: first the exact list of what will happen, and only then the
deletion (ADR-0018).
"""

from __future__ import annotations

import getpass
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from app.core import android, files, http, userenv
from app.core.catalog import (
    ANDROID_DIR_DEFAULT,
    API_LEVEL_DEFAULT,
    BUILD_TOOLS_DEFAULT,
    FLUTTER_DIR_DEFAULT,
)
from app.core.context import Level, TaskContext
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.process import as_argv, feed, format_argv, which_any
from app.core.registry import registry

# Light artifact families: they are walked and listed file by file. Each
# key is what `find_artifacts(families=...)` understands and also the
# catalog axis's value; what reads on the checkbox ('Gradle/Android')
# goes in `labels`.
FAMILIES: dict[str, dict[str, tuple[str, ...]]] = {
    "python": {"dirs": ("__pycache__",), "suffixes": (".pyc", ".pyo")},
    "gradle": {"dirs": (".gradle", ".kotlin", ".cxx")},
    "flutter": {"files": (".flutter-plugins", ".flutter-plugins-dependencies", ".packages")},
    "crash": {"files": ("CMakeOutput.log",), "prefixes": ("hs_err_pid", "replay_pid")},
}

# Heavy folders: not listed inside, they list as a unit and delete
# whole. Off by default (ADR-0018: what is expensive is asked for
# explicitly). Several names per key because node_modules does not
# change, but «venv» and «build» do.
HEAVY_DIRS: dict[str, tuple[str, ...]] = {
    "node_modules": ("node_modules",),
    "venv": (".venv", "venv"),
    "build": ("build", "dist"),
    "dart_tool": (".dart_tool",),
}

# Never entered, whatever was asked: they are not artifacts but version
# control itself and Consola's config.
ALWAYS_SKIP_DIRS = {".git", ".consola"}

COMMON_PATHS = (
    "server/alembic/env.py",
    "server/alembic/script.py.mako",
    "server/app/models/base.py",
    "server/app/schemas/base.py",
    "server/alembic.ini",
    ".gitignore",
)

CF_API = "https://api.cloudflare.com/client/v4"
IP_SERVICES = ("https://api.ipify.org", "https://ifconfig.me/ip")


# --- cleaning ---


def find_artifacts(
    ctx: TaskContext, families: list[str] | None = None, heavy: list[str] | None = None
) -> list[Path]:
    """List the repo's deletable artifacts, touching nothing.

    A read-only atomic capability: it is the dry run that feeds the
    destructive button, and it alone tells how much space can be
    recovered.

    `families` filters which light cache types list (by default all:
    `FAMILIES`). `heavy` are heavy folders (`node_modules`, `.venv`,
    `build`, `dist`, `.dart_tool`) that list whole, not inside; by
    default none, to not offer an expensive deletion unasked.
    """
    active_families = set(FAMILIES) if families is None else set(families)
    active_heavy_dirnames = {name for key in (heavy or ()) for name in HEAVY_DIRS.get(key, ())}
    # Heavy folders not asked for stay unwalked: entering node_modules
    # or .venv only to list nothing inside would be wasted work.
    skip_unrequested = {
        name for names in HEAVY_DIRS.values() for name in names
    } - active_heavy_dirnames

    found: list[Path] = []
    for current, subdirs, file_names in os.walk(ctx.root):
        base = Path(current)
        keep_subdirs = []
        for filename in subdirs:
            if filename in ALWAYS_SKIP_DIRS or filename in skip_unrequested:
                continue
            if filename in active_heavy_dirnames:
                found.append(base / filename)
                # it deletes whole: no need to go down and look
                continue
            if ("gradle" in active_families and filename in FAMILIES["gradle"]["dirs"]) or (
                "python" in active_families and filename in FAMILIES["python"]["dirs"]
            ):
                found.append(base / filename)
                continue
            keep_subdirs.append(filename)
        subdirs[:] = keep_subdirs

        for filename in file_names:
            if "flutter" in active_families and filename in FAMILIES["flutter"]["files"]:
                found.append(base / filename)
            elif "crash" in active_families and (
                filename in FAMILIES["crash"]["files"]
                or filename.startswith(FAMILIES["crash"]["prefixes"])
            ):
                found.append(base / filename)
            elif "python" in active_families and filename.endswith(FAMILIES["python"]["suffixes"]):
                found.append(base / filename)
    return found


def clean_artifacts(
    ctx: TaskContext,
    apply: bool = False,
    families: list[str] | None = None,
    heavy: list[str] | None = None,
) -> list[Path]:
    """Delete the listed artifacts. On a dry run it only shows them."""
    found = find_artifacts(ctx, families, heavy)
    if not found:
        ctx.ok("No hay artefactos para limpiar.")
        return []

    total = sum(files.size_of(p) for p in found)
    for path in found[:40]:
        ctx.info(f"  {path.relative_to(ctx.root)}")
    if len(found) > 40:
        ctx.info(f"  ... y {len(found) - 40} mas")
    ctx.warn(f"{len(found)} elemento(s), {files.human_size(total)}.")

    if not apply:
        ctx.info("Simulacro: no se borro nada.")
        return found

    for path in found:
        files.remove(path)
    ctx.ok(f"Liberados {files.human_size(total)}.")
    return found


# --- sync between repos ---


def compare_common_files(
    ctx: TaskContext, targets: list[str], paths: list[str] | None = None
) -> list[tuple[Path, str, str]]:
    """Compare the repo's shared files against the other repos.

    It returns `(target, path, state)` with state NEW, DIFF or SAME:
    what shows before enabling Apply (ADR-0004).
    """
    rel_paths = list(paths or COMMON_PATHS)
    result: list[tuple[Path, str, str]] = []
    for destination in targets:
        root = Path(destination)
        if not root.is_dir():
            ctx.warn(f"No existe el repo destino: {destination}")
            continue
        for rel in rel_paths:
            source = ctx.path(rel)
            if not source.exists():
                continue
            result.append((root, rel, files.compare(source, root / rel)))
    return result


def sync_common_files(
    ctx: TaskContext,
    targets: list[str] | None = None,
    paths: list[str] | None = None,
    apply: bool = False,
) -> list[tuple[Path, str, str]]:
    """Copy the shared files to the other managed repos.

    It no longer includes `scripts/` (ADR-0059).
    """
    if not targets:
        raise TaskError("No hay repos destino seleccionados.")

    differences = [row for row in compare_common_files(ctx, targets, paths) if row[2] != "SAME"]
    if not differences:
        ctx.ok("Todos los repos destino ya estan al dia.")
        return []

    for root, rel, state in differences:
        ctx.info(f"  [{state}] {root.name}/{rel}")

    if not apply:
        ctx.info("Simulacro: no se copio nada.")
        return differences

    for root, rel, _ in differences:
        files.copy(ctx.path(rel), root / rel)
        ctx.ok(f"{root.name}/{rel}")
    return differences


# --- DNS ---


def detect_public_ip(ctx: TaskContext) -> str:
    """Return this machine's public IP, asking an external service."""
    for service in IP_SERVICES:
        try:
            ip = http.request(service, timeout=10).decode("utf-8").strip()
            if ip:
                ctx.info(f"IP publica detectada: {ip}")
                return ip
        except OSError:
            continue
    raise TaskError("No se pudo detectar la IP publica.")


def _cloudflare(
    ctx: TaskContext, method: str, path: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    token = ctx.config.require("CF_API_TOKEN")
    ctx.guard(token)
    try:
        answer = http.request(
            f"{CF_API}{path}",
            method=method,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            body=json.dumps(body).encode("utf-8") if body is not None else None,
        )
        payload = json.loads(answer)
    except OSError as exc:
        raise TaskError(f"No se pudo hablar con Cloudflare: {exc}") from exc

    if not payload.get("success"):
        raise TaskError(f"Cloudflare rechazo la peticion: {payload.get('errors')}")
    return payload


def update_cloudflare(
    ctx: TaskContext, ip_mode: str = "vps", custom_ip: str = "", ttl: int = 1, proxied: bool = True
) -> str:
    """Point the DNS record to the chosen IP.

    Detected, the VPS's or fixed.
    """
    if ip_mode == "detect":
        ip = detect_public_ip(ctx)
    elif ip_mode == "static":
        ip = custom_ip or ctx.config.require("VPS_IP")
    else:
        ip = ctx.config.require("VPS_IP")

    domain = ctx.config.require("CF_DOMAIN_NAME")
    registry = ctx.config.require("CF_RECORD_NAME")

    zones = _cloudflare(ctx, "GET", f"/zones?name={domain}")["result"]
    if not zones:
        raise TaskError(f"Cloudflare no conoce el dominio {domain}.")
    zone = zones[0]["id"]

    records = _cloudflare(ctx, "GET", f"/zones/{zone}/dns_records?type=A&name={registry}")[
        "result"
    ]
    if not records:
        raise TaskError(f"No existe el registro A para {registry}.")

    current = records[0]
    if current["content"] == ip:
        ctx.ok(f"{registry} ya apunta a {ip}. No hay nada que cambiar.")
        return ip

    _cloudflare(
        ctx,
        "PUT",
        f"/zones/{zone}/dns_records/{current['id']}",
        {"type": "A", "name": registry, "content": ip, "ttl": ttl, "proxied": proxied},
    )
    ctx.ok(f"{registry}: {current['content']} -> {ip}")
    ctx.note(f"DNS {registry} apuntado a {ip}.")
    return ip


# --- SDKs: common plumbing ---

ANDROID_STUDIO_URL = "https://developer.android.com/studio#command-line-tools-only"
ANDROID_REPO_URL = "https://dl.google.com/android/repository/"
FLUTTER_RELEASES_URL = "https://storage.googleapis.com/flutter_infra_release/releases/"
FLUTTER_RELEASES_JSON = {
    "windows": "releases_windows.json",
    "linux": "releases_linux.json",
    "mac": "releases_macos.json",
}


def _fetch_text(url: str) -> str:
    try:
        answer = http.request(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        return answer.decode("utf-8", errors="replace")
    except OSError as exc:
        raise TaskError(f"No se pudo consultar {url}: {exc}") from exc


def _download(ctx: TaskContext, url: str, destination: Path) -> Path:
    """Download, reporting progress and attending to Stop.

    A bare `urlretrieve` left the interface mute during the SDK's
    hundreds of megabytes, with no way to stop it midway.
    """
    ctx.info(f"Descargando {url}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def progress(done: int, total: int) -> None:
        if total > 0:
            ctx.progress(done, total, f"{files.human_size(done)} de {files.human_size(total)}")

    try:
        with destination.open("wb") as target:
            http.download(
                url, target.write, on_progress=progress, should_stop=lambda: ctx.cancelled
            )
    except OSError as exc:
        raise TaskError(f"Fallo la descarga: {exc}") from exc
    ctx.raise_if_cancelled()

    ctx.ok(f"Descargado: {files.human_size(files.size_of(destination))}")
    return destination


def _verify(ctx: TaskContext, archive: Path, expected: str, algorithm: str) -> None:
    """Check the published digest.

    A half-downloaded SDK fails later and worse.
    """
    current = files.digest(archive, algorithm)
    if current.lower() != expected.lower():
        raise TaskError(
            f"{algorithm.upper()} no coincide: el archivo llego incompleto o alterado.\n"
            f"  esperado: {expected}\n  obtenido: {current}"
        )
    ctx.ok(f"{algorithm.upper()} verificado.")


# --- Android SDK ---

ANDROID_COMPONENTS = ("platform-tools", "emulator", "build-tools", "platform")


def _android_root(install_dir: str = "") -> Path:
    return Path(install_dir or ANDROID_DIR_DEFAULT).expanduser()


def _is_android_path(entry: str) -> bool:
    """Return whether a PATH entry belongs to an earlier SDK install."""
    path = entry.strip().strip('"').replace("\\", "/").rstrip("/").lower()
    return path.endswith(("/platform-tools", "/emulator", "/cmdline-tools/latest/bin"))


def _ensure_java(ctx: TaskContext) -> None:
    if which_any(["java", "java.exe"]):
        return
    raise TaskError(
        "No se encontro Java en el PATH y sdkmanager no corre sin el. "
        "Instala un JDK 17 o superior (en Debian/Ubuntu: apt install openjdk-17-jdk)."
    )


def _resolve_cmdline_tools(ctx: TaskContext, os_key: str) -> tuple[str, str]:
    """Return the URL and SHA-1 of cmdline-tools.

    From the official page.

    The URL is not a constant on purpose: Google changes the build
    number with each version, and an old constant fails with a 404 that
    explains nothing.
    """
    html = _fetch_text(ANDROID_STUDIO_URL)
    pattern = rf"commandlinetools-{'win' if os_key == 'windows' else os_key}-\d+_latest\.zip"

    names = list(dict.fromkeys(re.findall(pattern, html)))
    if len(names) != 1:
        raise TaskError(
            "No se pudo identificar el zip de cmdline-tools en la pagina de Android Studio "
            f"({len(names)} coincidencias para {os_key}). Puede que Google haya cambiado la "
            f"pagina."
        )

    filename = names[0]
    fingerprint = re.search(
        re.escape(filename) + r"[\s\S]{0,300}?([0-9a-f]{40})", html, re.IGNORECASE
    )
    if not fingerprint:
        raise TaskError(f"La pagina de Android Studio no publica el SHA-1 de {filename}.")

    ctx.info(f"Version publicada: {filename}")
    return ANDROID_REPO_URL + filename, fingerprint.group(1).lower()


def _extract_cmdline_tools(ctx: TaskContext, archive: Path, latest: Path) -> None:
    ctx.info(f"Descomprimiendo en {latest}")
    files.extract_zip(archive, latest)

    # The zip hangs everything from `cmdline-tools/`, but sdkmanager
    # deduces sdk_root from its own path and requires being in
    # `cmdline-tools/latest/bin`.
    interior = latest / "cmdline-tools"
    if interior.is_dir():
        for item in interior.iterdir():
            item.rename(latest / item.name)
        interior.rmdir()


def install_android_tools(ctx: TaskContext, install_dir: str = "") -> Path:
    """Install the Android command-line tools into the environment.

    Atomic: it resolves the published version, verifies it, extracts it
    and writes ANDROID_SDK_ROOT, ANDROID_HOME, ANDROID_AVD_HOME and the
    user's PATH. It installs no packages: `install_android_packages`
    handles that, run alone whenever another API or build-tools is
    needed.
    """
    os_key = HOST.sdk_key
    if os_key not in ("windows", "linux"):
        raise TaskError(f"Google no publica cmdline-tools para este sistema: {os_key}.")
    _ensure_java(ctx)

    root = _android_root(install_dir)
    latest = root / "cmdline-tools" / "latest"
    sdkmanager = latest / "bin" / HOST.script_name("sdkmanager")

    if sdkmanager.is_file():
        ctx.ok(f"Las cmdline-tools ya estaban en {latest}.")
    else:
        url, sha1 = _resolve_cmdline_tools(ctx, os_key)
        with tempfile.TemporaryDirectory(prefix="consola_cmdline_tools_") as temporary:
            archive = _download(ctx, url, Path(temporary) / "cmdline-tools.zip")
            _verify(ctx, archive, sha1, "sha1")
            _extract_cmdline_tools(ctx, archive, latest)
        if not sdkmanager.is_file():
            raise TaskError(f"No aparecio sdkmanager despues de descomprimir: {sdkmanager}")
        ctx.ok(f"cmdline-tools instaladas en {latest}.")

    avd = root / "avd"
    avd.mkdir(parents=True, exist_ok=True)
    userenv.configure(
        ctx,
        variables={
            "ANDROID_SDK_ROOT": str(root),
            "ANDROID_HOME": str(root),
            "ANDROID_AVD_HOME": str(avd),
        },
        path_add=[root / "platform-tools", root / "emulator", latest / "bin"],
        path_drop=_is_android_path,
    )
    return root


def _sdkmanager(ctx: TaskContext) -> tuple[list[str], Path]:
    """Return the installed sdkmanager and the SDK root it belongs to.

    It resolves through `core/android.py`, which explains what to do
    when missing, so the dependency does not couple the two atomic
    capabilities: if the tools are not installed yet, the error says so.
    """
    sdk = android.resolve_sdk()
    path = sdk.tool("sdkmanager")
    root = sdk.root or Path(path).resolve().parents[3]
    return as_argv(path), root


def _accept_licenses(ctx: TaskContext, sdkmanager: list[str], root: Path) -> None:
    ctx.info("Aceptando las licencias del SDK...")
    argv = [*sdkmanager, f"--sdk_root={root}", "--licenses"]
    ctx.log(format_argv(argv), Level.CMD)
    output = feed(argv, stdin_text="y\n" * 200, timeout=300)
    for line in output.splitlines():
        if line.strip():
            ctx.info(line.strip())
    ctx.ok("Licencias aceptadas.")


def _installed_packages(ctx: TaskContext, sdkmanager: list[str], root: Path) -> set[str]:
    output = ctx.capture(
        [*sdkmanager, f"--sdk_root={root}", "--list_installed"], timeout=300, check=False
    )
    return {line.split("|", 1)[0].strip() for line in output.splitlines() if "|" in line}


def install_android_packages(
    ctx: TaskContext,
    components: list[str] | None = None,
    api_level: str = "",
    build_tools: str = "",
) -> list[str]:
    """Install the missing packages in the present SDK.

    It is apart from the tools' install because it repeats: when a new
    API ships or a repo asks for another build-tools, that package adds
    without downloading the whole SDK again or touching the PATH.
    """
    chosen = list(ANDROID_COMPONENTS if components is None else components)
    if not chosen:
        raise TaskError("No se eligio ningun componente para instalar.")

    api = (api_level or API_LEVEL_DEFAULT).strip()
    tools = (build_tools or BUILD_TOOLS_DEFAULT).strip()
    packages = []
    for filename in chosen:
        if filename == "build-tools":
            packages.append(f"build-tools;{tools}")
        elif filename == "platform":
            packages.append(f"platforms;android-{api}")
        else:
            packages.append(filename)

    sdkmanager, root = _sdkmanager(ctx)
    _accept_licenses(ctx, sdkmanager, root)

    installed = _installed_packages(ctx, sdkmanager, root)
    missing = [p for p in packages if p not in installed]
    if not missing:
        ctx.ok(f"Los {len(packages)} paquete(s) pedidos ya estaban instalados.")
        return []

    for package in missing:
        ctx.info(f"  falta: {package}")
    ctx.run([*sdkmanager, f"--sdk_root={root}", *missing])
    ctx.ok(f"{len(missing)} paquete(s) instalados.")
    return missing


def install_android_hypervisor(ctx: TaskContext) -> bool:
    """Leave the emulator's hardware acceleration ready.

    It goes apart for two reasons. It is the only part of the whole
    install needing elevated rights (a kernel driver on Windows;
    belonging to the kvm group on Linux), so separating it means the
    other two ask for none. And it is what breaks by itself: a system
    update leaves the emulator very slow with the rest of the SDK
    unchanged.
    """
    return _ACCELERATIONS[HOST.emulator_acceleration](ctx)


def _install_hypervisor_driver(ctx: TaskContext) -> bool:
    """Install the kernel driver that accelerates on Windows."""
    try:
        ctx.capture(["sc", "query", "gvm"], timeout=30)
        ctx.ok("El Hypervisor Driver ya esta instalado (servicio gvm).")
        return True
    except TaskError:
        pass

    sdkmanager, root = _sdkmanager(ctx)
    ctx.info("Descargando el Google Android Emulator Hypervisor Driver...")
    ctx.run(
        [*sdkmanager, f"--sdk_root={root}", "extras;google;Android_Emulator_Hypervisor_Driver"]
    )

    installer = (
        root / "extras" / "google" / "Android_Emulator_Hypervisor_Driver" / "silent_install.bat"
    )
    if not installer.is_file():
        raise TaskError(f"No aparecio el instalador del driver: {installer}")

    ctx.warn("El driver necesita permisos de administrador: acepta el aviso de Windows.")
    _run_elevated(ctx, installer)
    return True


def _check_kvm(ctx: TaskContext) -> bool:
    """On Linux, acceleration is verified and, if missing, explained.

    Reaching in with sudo from a graphical interface would be worse than
    saying the exact command: the group change also takes no effect
    until signing in again.
    """
    device = Path("/dev/kvm")
    if not device.exists():
        raise TaskError(
            "No existe /dev/kvm: sin el, el emulador corre por software y es inusable.\n"
            "Revisa que la virtualizacion (VT-x o AMD-V) este activa en la BIOS y que el "
            "modulo kvm_intel o kvm_amd este cargado."
        )
    if os.access(device, os.R_OK | os.W_OK):
        ctx.ok("/dev/kvm accesible: la aceleracion por hardware esta disponible.")
        return True

    user = os.environ.get("USER") or getpass.getuser()
    ctx.warn("/dev/kvm existe pero este usuario no tiene permiso para usarlo.")
    ctx.warn(f"Corre:  sudo usermod -aG kvm {user}")
    ctx.warn("Y vuelve a iniciar sesion para que el grupo tome efecto.")
    return False


# One per value of `HOST.emulator_acceleration`.
_ACCELERATIONS = {"driver": _install_hypervisor_driver, "kvm": _check_kvm}


def _run_elevated(ctx: TaskContext, program: Path) -> None:
    """Launch a program asking for elevation: a single UAC prompt.

    It beats requiring all of Consola to run as administrator:
    everything else writes to HKCU and needs no rights.
    """
    import ctypes

    ctx.log(str(program), Level.CMD)
    code = getattr(ctypes, "windll").shell32.ShellExecuteW(
        None, "runas", str(program), None, str(program.parent), 1
    )
    if code <= 32:
        raise TaskError(
            f"No se pudo lanzar el instalador con permisos de administrador (codigo {code}). "
            "Si rechazaste el aviso de Windows, vuelve a intentarlo."
        )
    ctx.info("El instalador quedo corriendo en una ventana aparte; espera a que termine.")


def install_android_sdk(
    ctx: TaskContext,
    install_dir: str = "",
    components: list[str] | None = None,
    api_level: str = "",
    build_tools: str = "",
    *,
    tools: bool = True,
    packages: bool = True,
    hypervisor: bool = True,
) -> Path:
    """Install the whole Android SDK, end to end.

    Composite: it chains the three atomic capabilities in the only order
    that works, and each stays available alone from its own button. One
    boolean per step, like the other composites, because the naming
    contract asks for parameter names and not capability ids (ADR-0003).
    """
    root = _android_root(install_dir)

    if tools:
        ctx.step("tools")
        root = install_android_tools(ctx.child("install_android_tools"), install_dir)

    if packages:
        ctx.step("packages")
        install_android_packages(
            ctx.child("install_android_packages"), components, api_level, build_tools
        )

    if hypervisor:
        ctx.step("hypervisor")
        install_android_hypervisor(ctx.child("install_android_hypervisor"))

    ctx.ok(f"SDK de Android listo en {root}.")
    return root


# --- Flutter SDK ---


def _is_flutter_path(entry: str) -> bool:
    """Return whether a PATH entry is an old Flutter's `bin`.

    It looks at the parent folder and not only the exact name, to also
    recognize installs in their own folder (`~/sdk/flutter-stable/bin`).
    """
    parts = entry.strip().strip('"').replace("\\", "/").rstrip("/").lower().split("/")
    return len(parts) >= 2 and parts[-1] == "bin" and "flutter" in parts[-2]


def _ensure_git(ctx: TaskContext) -> None:
    if which_any(["git", "git.exe"]):
        return
    raise TaskError("No se encontro Git en el PATH, y Flutter lo necesita para actualizarse.")


def _resolve_flutter_stable(ctx: TaskContext, os_key: str) -> tuple[str, str]:
    """Return the stable channel's URL and SHA-256.

    From the releases index.
    """
    filename = FLUTTER_RELEASES_JSON.get(os_key)
    if not filename:
        raise TaskError(f"Flutter no publica releases para este sistema: {os_key}.")

    try:
        response_data = json.loads(_fetch_text(FLUTTER_RELEASES_URL + filename))
    except ValueError as exc:
        raise TaskError("El indice de releases de Flutter no vino en JSON valido.") from exc

    mark = ((response_data.get("current_release") or {}).get("stable") or "").strip()
    release = next(
        (
            r
            for r in (response_data.get("releases") or [])
            if (r.get("hash") or "").strip() == mark
        ),
        None,
    )
    if not release:
        raise TaskError("El indice de Flutter no identifica el release del canal stable.")

    file = (release.get("archive") or "").strip()
    fingerprint = (release.get("sha256") or "").strip().lower()
    if not file or not fingerprint:
        raise TaskError("El release stable de Flutter no publica archivo o SHA-256.")

    ctx.info(f"Version publicada: {release.get('version') or mark}")
    return FLUTTER_RELEASES_URL + file, fingerprint


def _extract_flutter(ctx: TaskContext, archive: Path, home: Path) -> None:
    """Extract the SDK, which brings its own `flutter/` folder.

    At the root.
    """
    destination = home.parent
    ctx.info(f"Descomprimiendo en {home}")
    destination.mkdir(parents=True, exist_ok=True)
    files.extract(archive, destination)

    extracted = destination / "flutter"
    if extracted != home:
        if home.exists():
            raise TaskError(f"Ya existe {home}: muevelo o elige otro directorio.")
        extracted.rename(home)


def install_flutter_sdk(ctx: TaskContext, install_dir: str = "") -> Path:
    """Install the Flutter SDK's stable channel into the environment.

    One atomic capability, unlike Android: Flutter has no loose packages
    added later, and it updates whole with `flutter upgrade`.
    """
    os_key = HOST.sdk_key
    _ensure_git(ctx)

    home = Path(install_dir or FLUTTER_DIR_DEFAULT).expanduser()
    flutter = home / "bin" / HOST.script_name("flutter")

    if flutter.is_file():
        ctx.ok(f"Flutter ya estaba instalado en {home}.")
    else:
        url, sha256 = _resolve_flutter_stable(ctx, os_key)
        with tempfile.TemporaryDirectory(prefix="consola_flutter_") as temporary:
            archive = _download(ctx, url, Path(temporary) / Path(url).name)
            _verify(ctx, archive, sha256, "sha256")
            _extract_flutter(ctx, archive, home)
        if not flutter.is_file():
            raise TaskError(f"No aparecio flutter despues de descomprimir: {flutter}")
        ctx.ok(f"Flutter instalado en {home}.")

    userenv.configure(
        ctx,
        variables={"FLUTTER_HOME": str(home)},
        path_add=[home / "bin"],
        path_drop=_is_flutter_path,
    )

    ctx.info("Verificando la instalacion...")
    ctx.run([*as_argv(str(flutter)), "--version"], check=False)
    ctx.info("flutter doctor: los avisos que siguen no son errores de la instalacion.")
    ctx.run([*as_argv(str(flutter)), "doctor"], check=False)
    return home


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("clean_artifacts", clean_artifacts)
    registry.bind("update_cloudflare", update_cloudflare)
    registry.bind("sync_common_files", sync_common_files)
    registry.bind("install_android_tools", install_android_tools)
    registry.bind("install_android_packages", install_android_packages)
    registry.bind("install_android_hypervisor", install_android_hypervisor)
    registry.bind("install_android_sdk", install_android_sdk)
    registry.bind("install_flutter_sdk", install_flutter_sdk)
