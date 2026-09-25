from __future__ import annotations
import os
import shlex
import threading
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from .. import android, catalog, icons, process, shots, targets, toolchain
from ..context import Level
from ..errors import TaskError
from ..registry import registry

"""
Grupo Imágenes: los iconos y las capturas publicables de las apps del repo.

Los iconos salen del logo del repo: Consola lo rasteriza con Qt, que ya trae
como biblioteca de imagenes (ADR-0055), y lo deja donde cada app lo toma.

La camara es un script del repo y Consola solo la dispara (ADR-0049): le pasa
que apps, temas e idiomas capturar, y el emulador ya encendido si se eligio uno
(ADR-0052). Despues lee los crudos que dejo y los revela para cada destino.
"""

LANDING = 'landing'
# Lo que tarda la camara en decir que captura: arrancar node y cargar su modulo,
# sin levantar nada.
_SUPPORTED_TIMEOUT = 60


def generate_icons(ctx, apps: Sequence[str] = ()) -> None:
    """Deja el logo del repo como icono de cada app marcada."""
    ctx.require_config('BRAND_ICON')
    if not apps:
        raise TaskError('Marca al menos una app.')
    logo = icons.brand_file(ctx.root, ctx.config.get('BRAND_ICON'), 'BRAND_ICON')
    frente = (icons.brand_file(ctx.root, ctx.config.get('BRAND_ICON_FOREGROUND'),
                               'BRAND_ICON_FOREGROUND')
              if ctx.config.get('BRAND_ICON_FOREGROUND') else None)

    # Se planean todas antes de escribir ninguna: una app mal declarada corta
    # la corrida, no la deja con unos iconos nuevos y otros viejos.
    trabajos = [icons.plan(ctx.root, nombre, logo, frente) for nombre in apps]
    dart = toolchain.dart_cmd() if any(t.is_flutter for t in trabajos) else []
    for trabajo in trabajos:
        ctx.raise_if_cancelled()
        ctx.info(f'{trabajo.app}:')
        for origen, destino in trabajo.writes:
            contenido = (origen.read_bytes() if destino.suffix.lower() == '.svg'
                         else _rasterize(origen, icons.RASTER_SIZE))
            _write(ctx, destino, contenido)
        if trabajo.is_flutter:
            ctx.run([*dart, 'run', icons.SECTION], cwd=trabajo.path)
        ctx.ok(f'{trabajo.app}: ícono listo.')


def _rasterize(svg: Path, lado: int) -> bytes:
    """El SVG como PNG cuadrado de `lado` pixeles, con antialiasing.

    QtSvg implementa SVG Tiny 1.2: un logo con filtros, mascaras o CSS sale
    distinto que en el navegador (ADR-0055).
    """
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise TaskError(f'Qt no pudo leer {svg.name} como SVG.')
    caja = renderer.viewBoxF()
    # Qt estira el viewBox hasta llenar la imagen: uno que no es cuadrado sale
    # deformado.
    if abs(caja.width() - caja.height()) > 1e-6:
        raise TaskError(f'{svg.name} no es cuadrado: su viewBox mide '
                        f'{caja.width():g}×{caja.height():g}.')
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(pintor)
    pintor.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(buffer, 'PNG')
    return bytes(buffer.data())


def _write(ctx, destino: Path, contenido: bytes) -> None:
    """Escribe el archivo solo si cambia, y dice que paso (ADR-0039)."""
    nombre = destino.relative_to(ctx.root).as_posix()
    if destino.is_file() and destino.read_bytes() == contenido:
        ctx.info(f'  sin cambios: {nombre}')
        return
    estado = 'actualizado' if destino.exists() else 'nuevo'
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    ctx.info(f'  {estado}: {nombre}')


def camera_command(config) -> list[str]:
    """`SHOTS_CMD` listo para correr, con su ejecutable ubicado."""
    if not config.get('SHOTS_CMD'):
        raise TaskError('Falta SHOTS_CMD en la configuración: es el comando de la cámara del repo.')
    comando = shlex.split(config.get('SHOTS_CMD'))
    ejecutable = process.resolve_executable([comando[0]], label=comando[0],
                                            hint='Revisa SHOTS_CMD.')
    return [*ejecutable, *comando[1:]]


def camera_supported(root: Path, config) -> dict[str, dict]:
    """Las apps, temas e idiomas que la camara sabe capturar (ADR-0054).

    Se le pregunta a ella con `--supported`: lo declara en su codigo, donde
    tambien lo usa para rechazar lo que no sabe, y asi no hay una segunda copia
    que pueda quedar distinta.
    """
    argv = [*camera_command(config), '--supported', '--kit', str(shots.KIT)]
    try:
        salida = process.capture(argv, cwd=root, timeout=_SUPPORTED_TIMEOUT)
    except TaskError as exc:
        # El mensaje de `capture` empieza con la linea de comando entera; lo
        # que sirve es lo que dijo la camara.
        detalle = str(exc).split('\n', 1)[-1].strip()
        raise TaskError(f'La cámara no dijo qué sabe capturar: {detalle}') from exc
    return shots.parse_supported(salida)


def shoot_screens(ctx, apps: Sequence[str] = (), themes: Sequence[str] = (),
                  languages: Sequence[str] = (), avd: str = '') -> Path:
    """Corre la camara del repo y comprueba que dejo lo que se le pidio."""
    ctx.require_config('SHOTS_CMD')
    if not (apps and themes and languages):
        raise TaskError('Marca al menos una app, un tema y un idioma.')

    for nombre in apps:
        targets.pick(ctx.root, shots.SHOT_KINDS, nombre)

    raw = shots.resolve_dir(ctx.root, ctx.config.get('SHOTS_RAW'))
    borrados = shots.clear_raw(raw, apps, themes, languages)
    if borrados:
        ctx.info(f'Se borraron {borrados} capturas de la corrida anterior.')

    comando = camera_command(ctx.config)
    # ADR-0052: si una app necesita emulador lo sabe la camara, no Consola. Se
    # enciende el que se eligio; sin ninguno, la camara corta antes de la
    # primera foto si alguna app pedida lo necesita.
    serial, encendido = _emulator(ctx, avd) if avd else ('', False)
    # La camara maneja el dispositivo con `adb` (ADR-0051): el del SDK que
    # encontro Consola, este o no en el PATH de la maquina.
    entorno = ({'PATH': os.pathsep.join([str(Path(android.resolve_sdk().adb).parent),
                                         os.environ.get('PATH', '')])}
               if avd else None)
    try:
        ctx.run([*comando, *shots.camera_args(apps, themes, languages, raw, serial)],
                cwd=ctx.root, env=entorno)
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
    registry.bind('generate_icons', generate_icons)
    registry.bind('shoot_screens', shoot_screens)
    registry.bind('render_shots', render_shots)
    registry.bind('screenshots', screenshots)
