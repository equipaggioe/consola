"""SDK, AVDs, system images and emulators."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.services import cache, ports
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.host import HOST
from app.services.language import QT_TRANSLATE_NOOP
from app.services.process import capture, which_any

_TOOLS = {
    "adb": ("platform-tools",),
    "emulator": ("emulator",),
    "avdmanager": ("cmdline-tools", "latest", "bin"),
    "sdkmanager": ("cmdline-tools", "latest", "bin"),
}


def sdk_root() -> Path | None:
    """Return the Android SDK's root declared in the environment."""
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return Path(value)
    return None


@dataclass(frozen=True)
class Sdk:
    """The four SDK tools Consola needs, already located.

    The SDK resolves once and they all come from it: if one is missing,
    it says which and where it looked, instead of failing later with
    «command not found».
    """

    root: Path | None

    def tool(self, name: str) -> str:
        """Return the path of a tool of the SDK."""
        subpath = _TOOLS.get(name)
        if subpath is None:
            raise TaskError(
                QCoreApplication.translate("Sdk", "Herramienta desconocida del SDK: {0}").format(
                    name
                )
            )

        names = HOST.executable_names(name)

        if self.root:
            for candidate in (self.root.joinpath(*subpath, n) for n in names):
                if candidate.is_file():
                    return str(candidate)
            raise TaskError(
                QCoreApplication.translate(
                    "Sdk", 'No se encontro "{0}" dentro del SDK ({1}). Esperado en: {2}'
                ).format(name, self.root, self.root.joinpath(*subpath))
            )

        found = which_any(names)
        if found:
            return found
        raise TaskError(
            QCoreApplication.translate(
                "Sdk",
                'No se encontro "{0}". Define ANDROID_SDK_ROOT o instala el SDK con la '
                "capacidad SDK Android.",
            ).format(name)
        )

    @property
    def adb(self) -> str:
        """Return the path of `adb`."""
        return self.tool("adb")

    @property
    def emulator(self) -> str:
        """Return the path of `emulator`."""
        return self.tool("emulator")


def resolve_sdk() -> Sdk:
    """Return the installed SDK, or stop saying what to install."""
    return Sdk(sdk_root())


def avd_home() -> Path:
    """Return the folder where AVDs live."""
    configured = (os.environ.get("ANDROID_AVD_HOME") or "").strip()
    return Path(configured) if configured else Path.home() / ".android" / "avd"


# --- presets ---

# --- catalogs and profiles ---

# The model number inside a device's name, to sort from new to old. A
# word has to come first: without that, `3.7" WVGA` enters as model 3
# and screen sizes mix with the Pixels.
_MODEL = re.compile(r"^[A-Za-z][A-Za-z ]*?\s(\d+)")


@dataclass(frozen=True)
class Device:
    """A hardware profile from `avdmanager list device`'s catalog.

    The SDK publishes the whole catalog, a hundred phones, tablets,
    watches and TVs, so choosing a device is an axis of the panel and
    not a constant of the code.
    """

    id: str
    name: str = ""
    oem: str = ""
    tag: str = ""

    @property
    def label(self) -> str:
        """Return only the model.

        The maker was next to it and told nothing apart: the whole
        catalog is 64 `Google` and 24 `Generic`. A datum that never
        changes between two options does not help choose, and only
        spends the panel's width.
        """
        return self.name or self.id

    @property
    def order(self) -> tuple[Any, ...]:
        """Return the sort key: phones and tablets, then the rest.

        Then, inside each family, the new model before the old.

        The catalog comes sorted by id, so the list opened on «AI
        Glasses», a device almost nobody emulates. A phone is chosen 99
        % of the time.

        Name as the tie-break was not enough: alphabetically «Pixel 2»
        goes before «Pixel 9», so the list opened on the oldest phone of
        the most used family. It sorts by descending model number, like
        system images by API (`Image.order`), and what has no number
        (Pixel, Pixel Fold, Pixel Tablet) goes after those that do.
        """
        family = f"{self.tag} {self.id}".lower()
        key = (-self._model, self.name or self.id)
        for mark in ("tv", "wear", "automotive", "desktop", "glasses", "xr"):
            if mark in family:
                return (4, *key)
        for span, marks in enumerate(
            (("pixel",), ("phone", "nexus"), ("tablet", "foldable", "resizable"))
        ):
            if any(m in family for m in marks):
                return (span, *key)
        return (3, *key)

    @property
    def _model(self) -> int:
        """Return the name's model number.

        9 in «Pixel 9 Pro», 10 in «Nexus 10».

        It has to start with a letter so as not to mistake the model for
        the screen size: `3.7" WVGA (Nexus One)` is not a Pixel 3.
        """
        match = _MODEL.match(self.name or self.id)
        return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class Image:
    """A system image: the virtual machine the AVD will run.

    `package` is the id sdkmanager understands
    (`system-images;android-36;google_apis;x86_64`); the rest are its
    three parts already split, which is how it reads when choosing.
    """

    package: str
    api: str = ""
    variant: str = ""
    abi: str = ""

    @property
    def label(self) -> str:
        """Return how it reads when choosing."""
        if not self.api:
            return self.package
        return f"Android {self.api}  |  {variant_label(self.variant)}  |  {self.abi}"

    @property
    def order(self) -> tuple[Any, ...]:
        """Return the sort key: what is almost always chosen, first.

        New API before old; inside an API, phone variants before TV or
        watch; and inside a variant, the machine's architecture before
        the emulated one. Without this, an alphabetical catalog opens on
        «Android TV | arm64», which almost nobody wants.
        """
        try:
            api = int(self.api)
        except ValueError:
            api = 0
        return (
            -api,
            _VARIANT_RANK.get(self.variant, 9),
            _ABI_RANK.get(self.abi, 9),
            self.variant,
            self.abi,
        )


@dataclass(frozen=True)
class AvdSpec:
    """What creating an AVD takes: a device and a machine.

    They are chosen separately because they install separately: an image
    downloads once and serves every AVD using it.
    """

    name: str
    device: str
    image: str


# Readable name of each system image variant. What is not listed shows
# as is: the SDK's catalog gains variants with each version, and a raw
# label beats hiding the option.
VARIANTS = {
    "default": QT_TRANSLATE_NOOP("android", "Android puro"),
    "google_apis": "Google APIs",
    "google_apis_playstore": "Google APIs + Play Store",
    "android-tv": "Android TV",
    "google-tv": "Google TV",
    "android-wear": "Wear OS",
    "android-automotive": "Automotive",
    "aosp_atd": QT_TRANSLATE_NOOP("android", "AOSP ATD (liviana)"),
    "google_atd": QT_TRANSLATE_NOOP("android", "Google ATD (liviana)"),
}

# How each architecture reads. The raw id does not say the one thing to
# know when choosing: whether it runs native on this machine or
# emulated, and so slowly.
ABIS = {
    "x86_64": "x86_64 (Intel / AMD)",
    "x86": QT_TRANSLATE_NOOP("android", "x86 (32 bits, en desuso)"),
    "arm64-v8a": "arm64-v8a (ARM, Apple Silicon)",
    "armeabi-v7a": QT_TRANSLATE_NOOP("android", "armeabi-v7a (ARM 32 bits)"),
}


def variant_label(variant: str) -> str:
    """Return how a system image variant reads."""
    return QCoreApplication.translate("android", VARIANTS.get(variant, variant))


def facet_labels(images: list[Image]) -> dict[str, str]:
    """Return how each loose part of a system image reads.

    The panel chooses the image by feature
    (`services/registry.py::Facet`), so besides the whole package's
    label it needs those of its three pieces as they appear in the id:
    `android-36`, `google_apis`, `x86_64`. They build from the images
    present and not a fixed table because versions come from the SDK's
    catalog, which gains one a year.
    """
    labels: dict[str, str] = {}
    for image in images:
        if image.api:
            labels[f"android-{image.api}"] = f"Android {image.api}"
        if image.variant:
            labels[image.variant] = variant_label(image.variant)
        if image.abi:
            labels[image.abi] = QCoreApplication.translate(
                "android", ABIS.get(image.abi, image.abi)
            )
    return labels


# Order of preference within one API. What is not listed goes last,
# alphabetically: the niche variants (TV, watch, car).
_VARIANT_RANK = {
    "google_apis_playstore": 0,
    "google_apis": 1,
    "default": 2,
    "google_atd": 3,
    "aosp_atd": 4,
}
_ABI_RANK = {"x86_64": 0, "arm64-v8a": 1, "x86": 2}

DEFAULT_FLAGS = ["-no-boot-anim", "-netdelay", "none", "-netspeed", "full"]

# The ports the emulator accepts: even ones, from 5554 to 5584. adb uses
# the next odd one to speak to it, hence steps of two.
PORT_RANGE = range(5554, 5586, 2)

_DEVICE_CACHE = "android-devices"
_IMAGE_CACHE = "android-images"


def device_catalog(sdk: Sdk, *, refresh: bool = False) -> list[Device]:
    """Return all the device profiles the SDK offers.

    Cached on disk (`services/cache.py`): the query takes several
    seconds and the catalog changes when the SDK updates, not during a
    session.
    """
    raws = cache.cached(_DEVICE_CACHE, lambda: _read_device_catalog(sdk), refresh=refresh)
    return sorted((Device(**d) for d in raws), key=lambda d: d.order)


def _read_device_catalog(sdk: Sdk) -> list[dict[str, str]]:
    output = capture([sdk.tool("avdmanager"), "list", "device"], timeout=120, check=False)
    devices: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in output.splitlines():
        clean = line.strip()
        if clean.startswith("id:"):
            # `id: 9 or "pixel_4"`: the useful id is the quoted one, not
            # the number, which changes position with each SDK version.
            if current:
                devices.append(current)
            parts = clean.split('"')
            current = {"id": parts[1] if len(parts) > 1 else clean.split(":", 1)[1].strip()}
        elif current is not None and ":" in clean:
            key, _, value = clean.partition(":")
            field = key.strip().lower()
            if field in ("name", "oem", "tag"):
                current[field] = value.strip()
    if current:
        devices.append(current)
    return devices


def image_catalog(sdk: Sdk, *, refresh: bool = False) -> list[Image]:
    """Return all published system images, installed or not."""
    packages = cache.cached(_IMAGE_CACHE, lambda: _read_image_catalog(sdk), refresh=refresh)
    return sorted((parse_image(p) for p in packages), key=lambda i: i.order)


def _read_image_catalog(sdk: Sdk) -> list[str]:
    output = capture([sdk.tool("sdkmanager"), "--list"], timeout=600, check=False)
    seen: list[str] = []
    for line in output.splitlines():
        package = line.split("|")[0].strip()
        if package.startswith("system-images;") and package not in seen:
            seen.append(package)
    return seen


def parse_image(package: str) -> Image:
    """Split `system-images;android-36;google_apis;x86_64` in three."""
    parts = package.split(";")
    if len(parts) < 4:
        return Image(package)
    return Image(package, parts[1].replace("android-", ""), parts[2], parts[3])


def forget_catalogs() -> None:
    """Invalidate both catalogs.

    Whoever just touched the SDK calls this.
    """
    cache.forget(_DEVICE_CACHE)
    cache.forget(_IMAGE_CACHE)


def suggest_avd_name(device: str, image: str) -> str:
    """Return a new AVD's default name: device plus API.

    `avdmanager` only accepts letters, numbers, hyphen, dot and
    underscore.
    """
    api = parse_image(image).api
    raw = f"{device}_api{api}" if api else device
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)


# --- inventory ---


def list_avds(sdk: Sdk) -> list[str]:
    """Return the names of the AVDs that exist."""
    output = capture([sdk.emulator, "-list-avds"], timeout=60, check=False)
    return [
        line.strip() for line in output.splitlines() if line.strip() and " " not in line.strip()
    ]


def list_images(sdk: Sdk) -> list[str]:
    """Return the installed system images, according to sdkmanager.

    Uncached, unlike the catalog: this changes each time one installs or
    uninstalls, and an old list would make «Crear AVD» offer an image
    that is gone.
    """
    output = capture([sdk.tool("sdkmanager"), "--list_installed"], timeout=180, check=False)
    return [
        line.split("|")[0].strip()
        for line in output.splitlines()
        if line.strip().startswith("system-images;")
    ]


def list_devices(sdk: Sdk) -> list[str]:
    """Return the live emulators' serials, asking adb.

    The emulator detaches from the process that launched it (ADR-0028),
    so its state cannot be inferred from a PID: it has to be probed.
    """
    output = capture([sdk.adb, "devices"], timeout=30, check=False)
    return [
        line.split()[0]
        for line in output.splitlines()[1:]
        if line.strip().endswith("device") and line.startswith("emulator-")
    ]


def running(sdk: Sdk) -> dict[str, str]:
    """Return serial -> AVD name for each live emulator.

    The serial only says the port; to know *which* AVD it is, the
    emulator's own console has to be asked. That allows warning that an
    AVD is already running before launching it a second time.
    """
    alive: dict[str, str] = {}
    for serial in list_devices(sdk):
        output = capture([sdk.adb, "-s", serial, "emu", "avd", "name"], timeout=15, check=False)
        name = next(
            (row.strip() for row in output.splitlines() if row.strip() and row.strip() != "OK"), ""
        )
        alive[serial] = name
    return alive


def free_port(sdk: Sdk) -> int:
    """Return a free emulator port.

    It is chosen here and passed with `-port` instead of leaving it to
    the emulator: so the serial (`emulator-5554`) is known BEFORE
    starting, and with it one can stop cleanly on closing the tab and
    tell the mobile app which device to run against. Otherwise one would
    have to guess which live emulator this tab launched.
    """
    busy = {s.rsplit("-", 1)[-1] for s in list_devices(sdk)}
    for port in PORT_RANGE:
        if str(port) not in busy and ports.is_free(port, host="127.0.0.1"):
            return port
    raise TaskError(
        QCoreApplication.translate("android", "No quedan puertos de emulador libres (5554-5584).")
    )


# --- life cycle ---


def ensure_image(ctx: TaskContext, sdk: Sdk, image: str) -> None:
    """Download the system image if it is missing."""
    if image in list_images(sdk):
        ctx.ok(
            QCoreApplication.translate("android", "System image ya instalada: {0}").format(image)
        )
        return
    ctx.info(QCoreApplication.translate("android", "Instalando system image: {0}").format(image))
    ctx.run([sdk.tool("sdkmanager"), image])


def ensure_avd(ctx: TaskContext, sdk: Sdk, spec: AvdSpec) -> str:
    """Create the AVD if missing, leaving the hardware keyboard on.

    Without `hw.keyboard=yes` the emulator ignores the real keyboard and
    one has to type on the touch screen.
    """
    if spec.name in list_avds(sdk):
        ctx.info(
            QCoreApplication.translate("android", 'El AVD "{0}" ya existe.').format(spec.name)
        )
    else:
        if spec.image not in list_images(sdk):
            raise TaskError(
                QCoreApplication.translate(
                    "android",
                    'La maquina {0} no esta instalada. Instalala primero con "Instalar maquina".',
                ).format(spec.image)
            )
        ctx.info(
            QCoreApplication.translate("android", 'Creando AVD "{0}" ({1}).').format(
                spec.name, spec.device
            )
        )
        ctx.run(
            [
                sdk.tool("avdmanager"),
                "create",
                "avd",
                "--name",
                spec.name,
                "--package",
                spec.image,
                "--device",
                spec.device,
            ]
        )
    _enable_hw_keyboard(ctx, spec.name)
    return spec.name


def _enable_hw_keyboard(ctx: TaskContext, avd_name: str) -> None:
    config = avd_home() / f"{avd_name}.avd" / "config.ini"
    if not config.is_file():
        ctx.warn(
            QCoreApplication.translate(
                "android", 'No se encontro config.ini del AVD "{0}".'
            ).format(avd_name)
        )
        return

    lines = config.read_text(encoding="utf-8").splitlines()
    lines = [line for line in lines if not line.strip().startswith("hw.keyboard=")]
    lines.append("hw.keyboard=yes")
    config.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def start(
    ctx: TaskContext,
    sdk: Sdk,
    avd_name: str,
    *,
    port: int,
    flags: list[str] | None = None,
    read_only: bool = False,
    wipe: bool = False,
) -> int:
    """Start the emulator on a fixed port and follow its output.

    `read_only` allows bringing up an AVD that is already running: the
    emulator takes a lock on the AVD's folder, and without this flag the
    second start dies with «another emulator instance is running». The
    second copy writes no changes to the AVD's disk, exactly what is
    wanted when opening two to try something between them.
    """
    argv = [sdk.emulator, "-avd", avd_name, "-port", str(port), *(flags or DEFAULT_FLAGS)]
    if read_only:
        argv.append("-read-only")
    if wipe:
        argv.append("-wipe-data")
    return ctx.run(argv, check=False)


def wait_for_boot(ctx: TaskContext, sdk: Sdk, *, timeout: float = 180.0, serial: str = "") -> str:
    """Wait for an emulator to finish starting and return its serial.

    With `serial` it waits for THAT one and not the first to appear:
    with two live emulators, «the first» is a lottery.
    """
    limit = time.time() + timeout
    while time.time() < limit:
        ctx.raise_if_cancelled()
        for found in [serial] if serial else list_devices(sdk):
            ready = capture(
                [sdk.adb, "-s", found, "shell", "getprop", "sys.boot_completed"],
                timeout=15,
                check=False,
            )
            if ready.strip() == "1":
                return found
        time.sleep(2)
    raise TaskError(
        QCoreApplication.translate(
            "android", "Ningun emulador termino de arrancar en {0:.0f}s."
        ).format(timeout)
    )


def stop(ctx: TaskContext, sdk: Sdk, serial: str) -> None:
    """Stop the emulator through adb.

    Killing its launcher is not enough.
    """
    ctx.run([sdk.adb, "-s", serial, "emu", "kill"], check=False)
    ctx.ok(QCoreApplication.translate("android", "Emulador {0} detenido.").format(serial))


def stop_quiet(sdk: Sdk, serial: str) -> None:
    """Ask the emulator to stop, without a log and without waiting.

    It is the version callable from the cancellation hook
    (`TaskContext.on_cancel`): there the tab's console may be gone and
    nobody can stay waiting. `adb emu kill` returns right away; the
    emulator takes a couple of seconds to close and saves its state in
    that time, which is what is lost by killing the process instead.
    """
    try:
        capture([sdk.adb, "-s", serial, "emu", "kill"], timeout=15, check=False)
    except TaskError:
        pass


def remove_avd(ctx: TaskContext, sdk: Sdk, name: str) -> None:
    """Delete an AVD."""
    ctx.run([sdk.tool("avdmanager"), "delete", "avd", "--name", name], check=False)


def remove_image(ctx: TaskContext, sdk: Sdk, image: str) -> None:
    """Uninstall a system image."""
    ctx.run([sdk.tool("sdkmanager"), "--uninstall", image], check=False)
