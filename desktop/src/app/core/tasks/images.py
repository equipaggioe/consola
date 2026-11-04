from __future__ import annotations

import os
import shlex
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.core import android, catalog, icons, process, shots, targets, toolchain
from app.core.context import Level, TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.registry import registry
from app.core.tasks import raster

"""
Grupo Imágenes: los iconos y las capturas publicables de las apps del repo.

Los iconos salen de los SVG del repo: Consola los rasteriza (`raster.py`,
ADR-0055) y los deja donde cada app declara que toma el suyo (ADR-0056).

La camara es un script del repo y Consola solo la dispara (ADR-0049): le pasa
que apps, temas e idiomas capturar, y el emulador ya encendido si se eligio uno
(ADR-0052). Despues lee los crudos que dejo y los revela para cada destino.
"""

LANDING = "landing"
# Lo que tarda la camara en decir que captura: arrancar node y cargar su modulo,
# sin levantar nada.
_SUPPORTED_TIMEOUT = 60


def generate_icons(ctx: TaskContext, apps: Sequence[str] = ()) -> None:
    """Deja el logo del repo, y sus capas, como icono de cada app marcada."""
    ctx.require_config("BRAND_ICON")
    if not apps:
        raise TaskError("Marca al menos una app.")
    layers = {
        layer: icons.brand_file(ctx.root, ctx.config.get(key), key)
        for layer, key in icons.LAYER_KEYS.items()
        if ctx.config.get(key)
    }

    # Se planean todas antes de escribir ninguna: una app mal declarada corta
    # la corrida, no la deja con unos iconos nuevos y otros viejos.
    jobs = [icons.plan(ctx.root, name, layers) for name in apps]
    dart = toolchain.dart_cmd() if any(t.is_flutter for t in jobs) else []
    for work in jobs:
        ctx.raise_if_cancelled()
        ctx.info(f"{work.app}:")
        for source, place in work.writes:
            _write(ctx, place.path, _render(source, place))
        if work.is_flutter:
            ctx.run([*dart, "run", icons.SECTION], cwd=work.path)
        ctx.ok(f"{work.app}: ícono listo.")


def _render(svg: Path, place: icons.Place) -> bytes:
    """El contenido del archivo segun su formato: el SVG tal cual, un PNG o un ICO."""
    suffix = place.path.suffix.lower()
    if suffix == ".svg":
        return svg.read_bytes()
    if suffix == ".ico":
        return raster.svg_to_ico(svg)
    return raster.svg_to_png(svg, place.size)


def _write(ctx: TaskContext, destination: Path, content: bytes) -> None:
    """Escribe el archivo solo si cambia, y dice que paso (ADR-0039)."""
    name = destination.relative_to(ctx.root).as_posix()
    if destination.is_file() and destination.read_bytes() == content:
        ctx.info(f"  sin cambios: {name}")
        return
    state = "actualizado" if destination.exists() else "nuevo"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    ctx.info(f"  {state}: {name}")


def camera_command(config: Config) -> list[str]:
    """`SHOTS_CMD` listo para correr, con su ejecutable ubicado."""
    if not config.get("SHOTS_CMD"):
        raise TaskError(
            "Falta SHOTS_CMD en la configuración: es el comando de la cámara del repo."
        )
    command = shlex.split(config.get("SHOTS_CMD"))
    executable = process.resolve_executable(
        [command[0]], label=command[0], hint="Revisa SHOTS_CMD."
    )
    return [*executable, *command[1:]]


def camera_supported(root: Path, config: Config) -> dict[str, dict[str, Any]]:
    """Las apps, temas e idiomas que la camara sabe capturar (ADR-0054).

    Se le pregunta a ella con `--supported`: lo declara en su codigo, donde
    tambien lo usa para rechazar lo que no sabe, y asi no hay una segunda copia
    que pueda quedar distinta.
    """
    argv = [*camera_command(config), "--supported", "--kit", str(shots.KIT)]
    try:
        output = process.capture(argv, cwd=root, timeout=_SUPPORTED_TIMEOUT)
    except TaskError as exc:
        # El mensaje de `capture` empieza con la linea de comando entera; lo
        # que sirve es lo que dijo la camara.
        detail = str(exc).split("\n", 1)[-1].strip()
        raise TaskError(f"La cámara no dijo qué sabe capturar: {detail}") from exc
    return shots.parse_supported(output)


def shoot_screens(
    ctx: TaskContext,
    apps: Sequence[str] = (),
    themes: Sequence[str] = (),
    languages: Sequence[str] = (),
    avd: str = "",
) -> Path:
    """Corre la camara del repo y comprueba que dejo lo que se le pidio."""
    ctx.require_config("SHOTS_CMD")
    if not (apps and themes and languages):
        raise TaskError("Marca al menos una app, un tema y un idioma.")

    for name in apps:
        targets.pick(ctx.root, shots.SHOT_KINDS, name)

    raw = shots.resolve_dir(ctx.root, ctx.config.get("SHOTS_RAW"))
    deleted = shots.clear_raw(raw, apps, themes, languages)
    if deleted:
        ctx.info(f"Se borraron {deleted} capturas de la corrida anterior.")

    command = camera_command(ctx.config)
    # ADR-0052: si una app necesita emulador lo sabe la camara, no Consola. Se
    # enciende el que se eligio; sin ninguno, la camara corta antes de la
    # primera foto si alguna app pedida lo necesita.
    serial, on = _emulator(ctx, avd) if avd else ("", False)
    # La camara maneja el dispositivo con `adb` (ADR-0051): el del SDK que
    # encontro Consola, este o no en el PATH de la maquina.
    environment = (
        {
            "PATH": os.pathsep.join(
                [str(Path(android.resolve_sdk().adb).parent), os.environ.get("PATH", "")]
            )
        }
        if avd
        else None
    )
    try:
        ctx.run(
            [*command, *shots.camera_args(apps, themes, languages, raw, serial)],
            cwd=ctx.root,
            env=environment,
        )
    finally:
        if on:
            android.stop(ctx, android.resolve_sdk(), serial)

    taken = shots.collect(ctx.root, raw, apps)
    missing = shots.missing_combinations(taken, apps, themes, languages)
    if missing:
        raise TaskError("La cámara terminó sin capturas para: " + "; ".join(missing))
    ctx.ok(f"{len(taken)} capturas en {raw}")
    return raw


def _emulator(ctx: TaskContext, avd: str) -> tuple[str, bool]:
    """El serial del AVD elegido, encendiendolo si hace falta.

    Devuelve tambien si lo encendio esta corrida: el que ya estaba vivo se deja
    como estaba, el que se encendio aca se apaga al terminar.
    """
    sdk = android.resolve_sdk()
    for serial, name in android.running(sdk).items():
        if name == avd:
            ctx.info(f"{avd} ya está encendido: {serial}")
            return serial, False
    if avd not in android.list_avds(sdk):
        raise TaskError(f'No existe el AVD "{avd}".')

    port = android.free_port(sdk)
    serial = f"emulator-{port}"
    ctx.info(f"Encendiendo {avd} como {serial}.")
    # La salida del emulador no le sirve a quien mira las capturas: solo pasan
    # sus avisos y errores. Comparte la cancelacion con esta corrida.
    quiet = ctx.child("launch_emulator")
    quiet.log_sink = lambda msg, level: (
        ctx.log(msg, level) if level in (Level.WARN, Level.ERROR) else None
    )
    ctx.on_cancel(lambda: android.stop_quiet(sdk, serial))
    threading.Thread(
        target=_run_quietly,
        daemon=True,
        args=(android.start, quiet, sdk, avd),
        kwargs={"port": port},
    ).start()
    android.wait_for_boot(ctx, sdk, serial=serial)
    ctx.ok(f"{avd} listo.")
    return serial, True


def _run_quietly(func: Callable[..., object], *args: object, **kwargs: Any) -> None:
    """Corre el emulador en su hilo. Si muere, `wait_for_boot` es quien lo dice."""
    try:
        func(*args, **kwargs)
    except Exception:
        pass


def render_shots(ctx: TaskContext, destinations: Sequence[str] = (LANDING,)) -> None:
    """Convierte los crudos para cada destino marcado y deja un manifiesto por destino."""
    if not destinations:
        raise TaskError("Marca al menos un destino.")
    presets = shots.load_presets()
    without_preset = [d for d in destinations if d not in presets]
    if without_preset:
        raise TaskError(
            f"No hay preset para: {', '.join(without_preset)} ({shots.PRESETS_FILE.name})."
        )

    raw = shots.resolve_dir(ctx.root, ctx.config.get("SHOTS_RAW"))
    raws = shots.collect(ctx.root, raw)
    if not raws:
        raise TaskError(f"No hay capturas en {raw}. Sácalas primero.")

    # Se planea todo antes de convertir nada: un destino al que no le sirven
    # los crudos corta la corrida, no la deja a medias con unas carpetas hechas
    # y otras no.
    jobs = {d: shots.plan(_label(d), presets[d], raws) for d in destinations}
    for destination, work in jobs.items():
        output = _out_dir(ctx, destination)
        ctx.info(f"{_label(destination)}: {_files(len(work))} en {output}")
        if presets[destination].get("archive"):
            derived = shots.render_archive([shot for shot, _ in work], output, destination)
        else:
            derived = []
            for index, (shot, size) in enumerate(work, start=1):
                ctx.raise_if_cancelled()
                ctx.progress(index, len(work), f"{destination} · {shot.stem}")
                derived.append(
                    shots.render_landing(shot, presets[LANDING], output)
                    if destination == LANDING
                    else shots.render_sized(shot, size, output, destination)
                )
        changes = shots.write_manifest(output, destination, derived)
        for title, items in (
            ("Cambiaron", changes.changed),
            ("Nuevas", changes.added),
            ("Ya no están", changes.removed),
        ):
            if items:
                ctx.info(f"{title}: {', '.join(items)}")
        ctx.ok(f"{_label(destination)}: {_files(len(derived))} y {shots.MANIFEST}")


def _files(n: int) -> str:
    return f"{n} archivo" if n == 1 else f"{n} archivos"


def _label(destination: str) -> str:
    return catalog.SHOT_DESTINATION_LABELS[destination]


def _out_dir(ctx: TaskContext, destination: str) -> Path:
    if destination == LANDING:
        return shots.resolve_dir(ctx.root, ctx.config.get("SHOTS_PUBLISH"))
    return shots.resolve_dir(ctx.root, ctx.config.get("SHOTS_DIST")) / destination


def screenshots(
    ctx: TaskContext,
    apps: Sequence[str] = (),
    themes: Sequence[str] = (),
    languages: Sequence[str] = (),
    avd: str = "",
    destinations: Sequence[str] = (LANDING,),
    *,
    shoot: bool = True,
    render: bool = True,
) -> None:
    """Compuesta: sacar las capturas y revelarlas.

    Sin `shoot` se revela lo que ya esta en disco: es lo que se hace cuando
    cambio la medida de un destino y no la app.
    """
    if shoot:
        ctx.step("shoot")
        shoot_screens(ctx.child("shoot_screens"), apps, themes, languages, avd)
    if render:
        ctx.step("render")
        render_shots(ctx.child("render_shots"), destinations)


def bind_all() -> None:
    registry.bind("generate_icons", generate_icons)
    registry.bind("shoot_screens", shoot_screens)
    registry.bind("render_shots", render_shots)
    registry.bind("screenshots", screenshots)
