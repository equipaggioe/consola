from __future__ import annotations
import shlex
import threading
from pathlib import Path
from typing import Sequence

from .. import android, catalog, process, shots, targets
from ..context import Level
from ..errors import TaskError
from ..registry import registry

"""
Grupo Imágenes: las capturas publicables de las apps del repo.

La camara es un script del repo y Consola solo la dispara (ADR-0049): le pasa
que apps, temas e idiomas capturar, y el emulador ya encendido si hay una app
movil. Despues lee los crudos que dejo y los revela para cada destino.
"""

LANDING = 'landing'


def shoot_screens(ctx, apps: Sequence[str] = (), themes: Sequence[str] = (),
                  languages: Sequence[str] = (), avd: str = '') -> Path:
    """Corre la camara del repo y comprueba que dejo lo que se le pidio."""
    ctx.require_config('SHOTS_CMD', 'SHOTS_LANGS')
    if not (apps and themes and languages):
        raise TaskError('Marca al menos una app, un tema y un idioma.')

    elegidas = [targets.pick(ctx.root, shots.SHOT_KINDS, nombre) for nombre in apps]
    moviles = [t.name for t in elegidas if t.kind in targets.MOBILE_APP]
    # ADR-0049: el emulador lo elige quien aprieta el boton, no el script. Se
    # corta antes de la primera foto, no a mitad de la corrida.
    if moviles and not avd:
        raise TaskError(f'Marcaste {", ".join(moviles)}, que es una app móvil: '
                        'elige el emulador donde capturarla.')

    raw = shots.resolve_dir(ctx.root, ctx.config.get('SHOTS_RAW'))
    borrados = shots.clear_raw(raw, apps, themes, languages)
    if borrados:
        ctx.info(f'Se borraron {borrados} capturas de la corrida anterior.')

    comando = shlex.split(ctx.config.get('SHOTS_CMD'))
    ejecutable = process.resolve_executable([comando[0]], label=comando[0],
                                            hint='Revisa SHOTS_CMD.')
    serial, encendido = _emulator(ctx, avd) if moviles else ('', False)
    try:
        ctx.run([*ejecutable, *comando[1:],
                 *shots.camera_args(apps, themes, languages, raw, serial)],
                cwd=ctx.root)
    finally:
        if encendido:
            android.stop(ctx, android.resolve_sdk(), serial)

    sacadas = shots.collect(ctx.root, raw, apps)
    faltan = shots.missing_combinations(sacadas, apps, themes, languages)
    if faltan:
        raise TaskError('La cámara terminó sin capturas para: ' + '; '.join(faltan))
    ctx.ok(f'{len(sacadas)} capturas en {raw}')
    return raw


def _emulator(ctx, avd: str) -> tuple[str, bool]:
    """El serial del AVD elegido, encendiendolo si hace falta.

    Devuelve tambien si lo encendio esta corrida: el que ya estaba vivo se deja
    como estaba, el que se encendio aca se apaga al terminar.
    """
    sdk = android.resolve_sdk()
    for serial, nombre in android.running(sdk).items():
        if nombre == avd:
            ctx.info(f'{avd} ya está encendido: {serial}')
            return serial, False
    if avd not in android.list_avds(sdk):
        raise TaskError(f'No existe el AVD "{avd}".')

    puerto = android.free_port(sdk)
    serial = f'emulator-{puerto}'
    ctx.info(f'Encendiendo {avd} como {serial}.')
    # La salida del emulador no le sirve a quien mira las capturas: solo pasan
    # sus avisos y errores. Comparte la cancelacion con esta corrida.
    silencioso = ctx.child('launch_emulator')
    silencioso.log_sink = (lambda msg, nivel: ctx.log(msg, nivel)
                           if nivel in (Level.WARN, Level.ERROR) else None)
    ctx.on_cancel(lambda: android.stop_quiet(sdk, serial))
    threading.Thread(target=_run_quietly, daemon=True,
                     args=(android.start, silencioso, sdk, avd),
                     kwargs={'port': puerto}).start()
    android.wait_for_boot(ctx, sdk, serial=serial)
    ctx.ok(f'{avd} listo.')
    return serial, True


def _run_quietly(func, *args, **kwargs) -> None:
    """Corre el emulador en su hilo. Si muere, `wait_for_boot` es quien lo dice."""
    try:
        func(*args, **kwargs)
    except Exception:
        pass


def render_shots(ctx, destinations: Sequence[str] = (LANDING,)) -> None:
    """Convierte los crudos para cada destino marcado y deja un manifiesto por destino."""
    if not destinations:
        raise TaskError('Marca al menos un destino.')
    presets = shots.load_presets()
    sin_preset = [d for d in destinations if d not in presets]
    if sin_preset:
        raise TaskError(f'No hay preset para: {", ".join(sin_preset)} ({shots.PRESETS_FILE.name}).')

    raw = shots.resolve_dir(ctx.root, ctx.config.get('SHOTS_RAW'))
    crudos = shots.collect(ctx.root, raw)
    if not crudos:
        raise TaskError(f'No hay capturas en {raw}. Sácalas primero.')

    # Se planea todo antes de convertir nada: un destino al que no le sirven
    # los crudos corta la corrida, no la deja a medias con unas carpetas hechas
    # y otras no.
    trabajos = {d: shots.plan(_label(d), presets[d], crudos) for d in destinations}
    for destino, trabajo in trabajos.items():
        salida = _out_dir(ctx, destino)
        ctx.info(f'{_label(destino)}: {_files(len(trabajo))} en {salida}')
        if presets[destino].get('archive'):
            derivados = shots.render_archive([shot for shot, _ in trabajo], salida, destino)
        else:
            derivados = []
            for indice, (shot, medida) in enumerate(trabajo, start=1):
                ctx.raise_if_cancelled()
                ctx.progress(indice, len(trabajo), f'{destino} · {shot.stem}')
                derivados.append(shots.render_landing(shot, presets[LANDING], salida)
                                 if destino == LANDING
                                 else shots.render_sized(shot, medida, salida, destino))
        cambios = shots.write_manifest(salida, destino, derivados)
        for titulo, lista in (('Cambiaron', cambios.changed), ('Nuevas', cambios.added),
                              ('Ya no están', cambios.removed)):
            if lista:
                ctx.info(f'{titulo}: {", ".join(lista)}')
        ctx.ok(f'{_label(destino)}: {_files(len(derivados))} y {shots.MANIFEST}')


def _files(n: int) -> str:
    return f'{n} archivo' if n == 1 else f'{n} archivos'


def _label(destino: str) -> str:
    return catalog.SHOT_DESTINATION_LABELS[destino]


def _out_dir(ctx, destino: str) -> Path:
    if destino == LANDING:
        return shots.resolve_dir(ctx.root, ctx.config.get('SHOTS_PUBLISH'))
    return shots.resolve_dir(ctx.root, ctx.config.get('SHOTS_DIST')) / destino


def screenshots(ctx, apps: Sequence[str] = (), themes: Sequence[str] = (),
                languages: Sequence[str] = (), avd: str = '',
                destinations: Sequence[str] = (LANDING,), *,
                shoot: bool = True, render: bool = True) -> None:
    """Compuesta: sacar las capturas y revelarlas.

    Sin `shoot` se revela lo que ya esta en disco: es lo que se hace cuando
    cambio la medida de un destino y no la app.
    """
    if shoot:
        ctx.step('shoot')
        shoot_screens(ctx.child('shoot_screens'), apps, themes, languages, avd)
    if render:
        ctx.step('render')
        render_shots(ctx.child('render_shots'), destinations)


def bind_all() -> None:
    registry.bind('shoot_screens', shoot_screens)
    registry.bind('render_shots', render_shots)
    registry.bind('screenshots', screenshots)
