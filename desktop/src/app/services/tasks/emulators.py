"""Emulators group.

Three separate activities, each with its own catalog:

  Install machine  ->  from the SDK's system image catalog
  Create AVD       ->  from the device catalog + an installed machine
  Emulator         ->  among the AVDs that exist

No composite chains them. When a step stops being «the usual» and has
options of its own, it no longer fits in a checkbox: installing a
virtual machine happens every few months, creating an AVD once per
model, and starting twenty times a day. Chaining them would force
answering three catalogs to do what is almost always the third.

Stopping has no button in the rail: closing the tab stops the emulator
it launched, and orphans stop from the panel's status header.
"""

from __future__ import annotations

import shlex

from PySide6.QtCore import QCoreApplication, QLocale

from app.services import android, cache, files, session
from app.services.context import TaskContext
from app.services.errors import TaskError
from app.services.registry import registry

# The serial of the last emulator started, so the mobile app need not
# guess which one to run against. It is session state like `SERVER_PORT`
# (ADR-0009), but of the machine and not a repo: the emulator belongs to
# nobody in particular.
EMULATOR_SERIAL = "EMULATOR_SERIAL"


# --- install ---


def install_system_image(ctx: TaskContext, image: str = "") -> str:
    """Download a virtual machine from the SDK's catalog if missing.

    It is the group's slow part, several GB, so it has its own button:
    it happens once and then serves every AVD using it.
    """
    if not image:
        raise TaskError(
            QCoreApplication.translate("emulators", "Elige que maquina virtual instalar.")
        )
    sdk = android.resolve_sdk()
    spec = android.parse_image(image)
    ctx.info(QCoreApplication.translate("emulators", "Maquina: {0}").format(spec.label))
    android.ensure_image(ctx, sdk, image)
    cache.forget("android-installed")
    return image


def create_avd(ctx: TaskContext, device: str = "", image: str = "") -> str:
    """Create the virtual device with the chosen model and machine.

    The name is asked when running and does not come as a parameter: two
    AVDs cannot share a name, so a saved one only serves the first time
    (`ADR-0064` 6). Leaving it empty is the normal answer: it then
    derives from the device and API (`pixel_4_api36`), almost always
    what is wanted. It asks anyway, and not only on a collision, because
    the derived name shows right there: one sees the name before it
    exists, when it matters.
    """
    if not device:
        raise TaskError(
            QCoreApplication.translate("emulators", "Elige un dispositivo del catalogo.")
        )
    if not image:
        raise TaskError(
            QCoreApplication.translate(
                "emulators",
                "Elige una maquina virtual instalada. Si no hay ninguna, instalala "
                'primero con "Instalar imagen de sistema".',
            )
        )

    derived = android.suggest_avd_name(device, image)
    name = ctx.ask(
        QCoreApplication.translate("emulators", "Nombre del AVD (vacío = {0})").format(derived)
    )

    sdk = android.resolve_sdk()
    spec = android.AvdSpec(name.strip() or derived, device, image)
    created = android.ensure_avd(ctx, sdk, spec)
    cache.forget("android-avds")
    ctx.ok(QCoreApplication.translate("emulators", "AVD listo: {0}").format(created))
    return created


# --- usage ---


def launch_emulator(
    ctx: TaskContext,
    avd: str = "",
    wipe: bool = False,
    boot_flags: list[str] | None = None,
    gpu: str = "host",
    flags: str = "",
) -> str:
    """Start a created AVD and follow its output until it closes.

    Three details:

    - The port is chosen before starting, so the serial is known from
      the beginning: otherwise there is no way to know which live
      emulator is this tab's.
    - If that AVD is already running, the second copy goes in
      `-read-only`, the only way to have two open at once.
    - Stopping the tab asks the emulator to close through adb instead of
      killing its process (ADR-0028).

    Flags come by three paths that add up and never replace each other:
    `android.DEFAULT_FLAGS` (the usual), `boot_flags` and `gpu` (the
    panel's checkboxes, whose value IS the flag), and `flags` (what is
    left to type). Checking a box asks for *that as well*.

    `flags` is a command line and not a list, because that is what goes
    in a field: there `-memory 4096` is two tokens typed together, and
    it splits as a shell would.
    """
    if not avd:
        raise TaskError(
            QCoreApplication.translate(
                "emulators", 'Elige un AVD. Si no hay ninguno, crealo con "Crear AVD".'
            )
        )

    sdk = android.resolve_sdk()
    if avd not in android.list_avds(sdk):
        raise TaskError(
            QCoreApplication.translate("emulators", 'No existe el AVD "{0}".').format(avd)
        )

    alive = android.running(sdk)
    duplicate = avd in alive.values()
    if duplicate:
        ctx.info(
            QCoreApplication.translate(
                "emulators",
                '"{0}" ya esta corriendo: esta copia arranca en solo lectura (no guarda '
                "cambios en el disco del AVD).",
            ).format(avd)
        )

    # `-gpu` always goes, because the axis does not offer «let the
    # emulator decide»: the panel's two options are the two chosen by
    # hand.
    chosen = [
        *(boot_flags or []),
        "-gpu",
        "swiftshader_indirect" if gpu == "software" else "host",
    ]

    console_port = android.free_port(sdk)
    serial = f"emulator-{console_port}"
    ctx.info(
        QCoreApplication.translate("emulators", "Arrancando {0} como {1}.").format(avd, serial)
    )

    session.publish(session.MACHINE, EMULATOR_SERIAL, serial)
    ctx.on_cancel(lambda: android.stop_quiet(sdk, serial))
    try:
        android.start(
            ctx,
            sdk,
            avd,
            port=console_port,
            flags=[*android.DEFAULT_FLAGS, *chosen, *shlex.split(flags)],
            read_only=duplicate,
            wipe=wipe,
        )
    finally:
        if session.read(session.MACHINE, EMULATOR_SERIAL) == serial:
            session.forget(session.MACHINE, EMULATOR_SERIAL)
        ctx.info(QCoreApplication.translate("emulators", "{0} se cerro.").format(serial))
    return serial


def await_emulator(ctx: TaskContext, timeout: float = 180.0, serial: str = "") -> str:
    """Wait for an emulator to finish booting and return its serial.

    Not a button: nobody asks to wait for a boot alone. Mobile app
    launchers use it before installing the APK, because `flutter run`
    against a device that does not accept commands yet fails without
    explaining why.
    """
    found = android.wait_for_boot(ctx, android.resolve_sdk(), timeout=timeout, serial=serial)
    ctx.ok(QCoreApplication.translate("emulators", "Emulador listo: {0}").format(found))
    return found


def stop_emulator(ctx: TaskContext, serial: str = "") -> None:
    """Stop one or all live emulators.

    It runs from the ✕ of the panel's status header, for orphans: an
    emulator from an earlier session, or started from Android Studio. An
    open tab's emulator stops by itself on closing.
    """
    sdk = android.resolve_sdk()
    targets = [serial] if serial else android.list_devices(sdk)
    if not targets:
        ctx.info(QCoreApplication.translate("emulators", "No hay ningun emulador corriendo."))
        return
    for one in targets:
        android.stop(ctx, sdk, one)


# --- cleaning ---


def purge_emulators(
    ctx: TaskContext,
    avds: list[str] | None = None,
    images: list[str] | None = None,
    apply: bool = False,
) -> dict[str, list[str]]:
    """Delete the checked AVDs and machines, with a dry run first.

    It chooses what goes, shows the list with its size, and only then
    asks to type BORRAR (ADR-0018).
    """
    sdk = android.resolve_sdk()
    avds = list(avds or [])
    images = list(images or [])
    if not avds and not images:
        ctx.info(QCoreApplication.translate("emulators", "No hay nada marcado para borrar."))
        return {"avds": [], "images": []}

    if avds:
        ctx.warn(QCoreApplication.translate("emulators", "AVD a borrar ({0}):").format(len(avds)))
        for name in avds:
            path = android.avd_home() / f"{name}.avd"
            weight = files.human_size(files.size_of(path), QLocale()) if path.exists() else "?"
            ctx.info(f"  {name}  ({weight})")
    if images:
        ctx.warn(
            QCoreApplication.translate(
                "emulators", "Maquinas virtuales a desinstalar ({0}):"
            ).format(len(images))
        )
        for package in images:
            ctx.info(f"  {android.parse_image(package).label}")

    if not apply:
        ctx.info(
            QCoreApplication.translate(
                "emulators", 'Simulacro: no se borro nada. Marca "borrar" para confirmar.'
            )
        )
        return {"avds": avds, "images": images}

    total = len(avds) + len(images)
    if not ctx.confirm(
        QCoreApplication.translate(
            "emulators", "Escribe BORRAR para eliminar {0} elemento(s)."
        ).format(total),
        danger=True,
        expect="BORRAR",
    ):
        ctx.warn(QCoreApplication.translate("emulators", "Cancelado: no se borro nada."))
        return {"avds": [], "images": []}

    for name in avds:
        android.remove_avd(ctx, sdk, name)
        ctx.ok(QCoreApplication.translate("emulators", "AVD eliminado: {0}").format(name))
    for package in images:
        android.remove_image(ctx, sdk, package)
        ctx.ok(
            QCoreApplication.translate("emulators", "Maquina desinstalada: {0}").format(package)
        )

    cache.forget("android-avds")
    cache.forget("android-installed")
    ctx.note(
        QCoreApplication.translate(
            "emulators", "Limpieza de emuladores: {0} AVD, {1} maquina(s)."
        ).format(len(avds), len(images))
    )
    return {"avds": avds, "images": images}


def inventory(ctx: TaskContext | None = None) -> dict[str, list[str]]:
    """Return what is on the machine right now. It only looks."""
    sdk = android.resolve_sdk()
    return {
        "avds": android.list_avds(sdk),
        "images": android.list_images(sdk),
        "running": android.list_devices(sdk),
    }


def bind_all() -> None:
    """Register the group's functions in the catalog."""
    registry.bind("install_system_image", install_system_image)
    registry.bind("create_avd", create_avd)
    registry.bind("launch_emulator", launch_emulator)
    registry.bind("stop_emulator", stop_emulator)
    registry.bind("purge_emulators", purge_emulators)
