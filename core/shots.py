from __future__ import annotations
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import targets
from .errors import TaskError

"""
Capturas publicables: el contrato con la camara del repo y el revelado.

La camara es un script del repo (ADR-0049): Consola lo corre con la seleccion
como argumentos y despues lee lo que dejo. Aca vive todo lo que no es correr
procesos: donde van los crudos, como se llaman, que se le pasa al script y como
se convierte cada crudo para cada destino.
"""

THEMES = ('claro', 'oscuro')

# Los tipos de app que se pueden fotografiar: lo que tiene pantalla. El servidor
# y las apps de escritorio quedan fuera hasta que alguien las necesite.
SHOT_KINDS = (targets.SPA_VITE, *targets.MOBILE_APP)

# <app>/<pantalla>.<tema>.<idioma>.png. Los cuatro segmentos son obligatorios:
# un nombre que no calza no se adivina, corta el revelado.
_RAW_NAME = re.compile(r'^(?P<screen>[^.]+)\.(?P<theme>[^.]+)\.(?P<language>[^.]+)\.png$')

PRESETS_FILE = Path(__file__).with_name('shots_presets.json')
MANIFEST = 'capturas.json'


@dataclass(frozen=True)
class Shot:
    """Una captura cruda, ya leida de su nombre."""
    app: str
    kind: str
    screen: str
    theme: str
    language: str
    path: Path

    @property
    def stem(self) -> str:
        return f'{self.screen}.{self.theme}.{self.language}'


def resolve_dir(root: Path, value: str) -> Path:
    """Una carpeta de la configuracion: relativa cuelga del repo, absoluta va tal cual."""
    declarada = Path(value)
    return declarada if declarada.is_absolute() else root / declarada


def camera_args(apps: Iterable[str], themes: Iterable[str], languages: Iterable[str],
                output: Path, device: str = '') -> list[str]:
    """Los argumentos que Consola le agrega a `SHOTS_CMD` (ADR-0049)."""
    args = ['--apps', ','.join(apps), '--themes', ','.join(themes),
            '--languages', ','.join(languages), '--output', str(output)]
    if device:
        args += ['--device', device]
    return args


def clear_raw(raw: Path, apps: Iterable[str], themes: Iterable[str],
              languages: Iterable[str]) -> int:
    """Borra los crudos de las combinaciones que se van a volver a sacar.

    Sin esto, una pantalla que el script dejo de capturar seguiria en la
    carpeta y el revelado la publicaria como si fuera nueva. Solo se tocan las
    combinaciones pedidas: sacar el ingles no borra el espanol.
    """
    borrados = 0
    for app in apps:
        for theme in themes:
            for language in languages:
                for viejo in (raw / app).glob(f'*.{theme}.{language}.png'):
                    viejo.unlink()
                    borrados += 1
    return borrados


def collect(root: Path, raw: Path, apps: Iterable[str] | None = None) -> list[Shot]:
    """Las capturas crudas, validadas. `apps` limita a esas carpetas.

    Corta con error ante una carpeta que no es una app del repo o un archivo
    que no sigue el nombre acordado: revelar a medias dejaria la landing con
    una mezcla de corridas.
    """
    if not raw.is_dir():
        raise TaskError(f'No existe la carpeta de capturas crudas: {raw}')
    tipos = {t.name: t.kind for t in targets.by_kinds(root, SHOT_KINDS)}
    carpetas = [raw / a for a in apps] if apps is not None else sorted(
        p for p in raw.iterdir() if p.is_dir())

    shots: list[Shot] = []
    for carpeta in carpetas:
        if carpeta.name not in tipos:
            raise TaskError(f'{carpeta} no corresponde a ninguna app del repo '
                            f'({", ".join(sorted(tipos)) or "no hay ninguna"}).')
        if not carpeta.is_dir():
            continue
        for archivo in sorted(carpeta.iterdir()):
            nombre = _RAW_NAME.match(archivo.name)
            if not archivo.is_file() or nombre is None:
                raise TaskError(f'{archivo} no sigue el nombre '
                                '<pantalla>.<tema>.<idioma>.png.')
            if nombre['theme'] not in THEMES:
                raise TaskError(f'{archivo}: el tema "{nombre["theme"]}" no es '
                                f'{" ni ".join(THEMES)}.')
            shots.append(Shot(app=carpeta.name, kind=tipos[carpeta.name],
                              screen=nombre['screen'], theme=nombre['theme'],
                              language=nombre['language'], path=archivo))
    return shots


def missing_combinations(shots: list[Shot], apps: Iterable[str], themes: Iterable[str],
                         languages: Iterable[str]) -> list[str]:
    """Las combinaciones pedidas para las que la camara no dejo ninguna captura."""
    hechas = {(s.app, s.theme, s.language) for s in shots}
    return [f'{a} · {t} · {l}' for a in apps for t in themes for l in languages
            if (a, t, l) not in hechas]


def load_presets() -> dict:
    return json.loads(PRESETS_FILE.read_text(encoding='utf-8'))


def render_landing(shot: Shot, preset: dict, out_dir: Path) -> 'Derived':
    """Un crudo -> el .webp de la landing, sin agrandarlo nunca.

    El ancho del preset es un tope: una captura mas angosta que el se deja
    como esta, porque agrandarla solo la desenfoca.
    """
    from PIL import Image

    anchos = preset['max_width']
    if shot.kind not in anchos:
        raise TaskError(f'El preset de la landing no tiene ancho para {shot.kind} '
                        f'({PRESETS_FILE.name}).')
    destino = out_dir / shot.app / f'{shot.stem}.webp'
    destino.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(shot.path) as imagen:
        tope = anchos[shot.kind]
        if imagen.width > tope:
            alto = round(imagen.height * tope / imagen.width)
            imagen = imagen.resize((tope, alto), Image.Resampling.LANCZOS)
        imagen.save(destino, 'WEBP', quality=preset['quality'])
        return Derived(shot, 'landing', destino, imagen.width, imagen.height)


@dataclass(frozen=True)
class Derived:
    """Un archivo que dejo el revelado, con lo que el manifiesto necesita."""
    shot: Shot
    destination: str
    path: Path
    width: int
    height: int
    archive: str = ''   # el ZIP que lo contiene, si el destino es un archivo


def aspect_crop(width: int, height: int, target_w: int, target_h: int) -> float:
    """La fraccion de la imagen que se pierde al llevarla a la proporcion destino."""
    actual, destino = width / height, target_w / target_h
    return 1 - min(actual, destino) / max(actual, destino)


def plan(destination: str, preset: dict, crudos: list[Shot]) -> list[tuple[Shot, dict | None]]:
    """Los pares (crudo, medida) que produce un destino; `None` es la medida nativa.

    - `kinds` dice de que crudos sale el destino: una captura de escritorio no
      se convierte en una de telefono.
    - `limits` (Play) no cambia la medida: el crudo tiene que cumplirlos.
    - `sizes` son medidas exactas. Cada crudo va a las medidas cuya proporcion
      se alcanza recortando como mucho `max_crop`; asi un telefono va a la de
      iPhone y una tablet a la de iPad sin que el contrato diga que es cada uno.

    Corta si al destino no le sirve ningun crudo, o si un crudo no cabe en
    ninguna medida: recortar de mas se come la barra o la navegacion de la app.
    """
    from PIL import Image

    tipos = preset.get('kinds')
    propios = [s for s in crudos if not tipos or s.kind in tipos]
    if not propios:
        raise TaskError(f'{destination}: ninguna captura es de un tipo que le sirva '
                        f'({", ".join(tipos)}).')
    if 'sizes' not in preset and 'limits' not in preset:
        return [(s, None) for s in propios]

    pares: list[tuple[Shot, dict | None]] = []
    fuera: list[str] = []
    for shot in propios:
        with Image.open(shot.path) as imagen:
            ancho, alto = imagen.size
        if 'limits' in preset:
            falla = _outside_limits(ancho, alto, preset['limits'])
            if falla:
                fuera.append(f'{shot.app}/{shot.stem} ({ancho}×{alto}): {falla}')
            else:
                pares.append((shot, None))
            continue
        caben = [m for m in preset['sizes']
                 if (not m.get('kinds') or shot.kind in m['kinds'])
                 and aspect_crop(ancho, alto, m['width'], m['height']) <= preset['max_crop']]
        if not caben:
            medidas = ', '.join(f'{m["width"]}×{m["height"]}' for m in preset['sizes'])
            fuera.append(f'{shot.app}/{shot.stem} ({ancho}×{alto}) no llega a {medidas} '
                         f'recortando como mucho {preset["max_crop"]:.0%}')
        pares.extend((shot, m) for m in caben)
    if fuera:
        raise TaskError(f'{destination}: capturas que no sirven tal como se sacaron. '
                        'Sácalas con un dispositivo de otra proporción o desmarca el '
                        'destino.\n  ' + '\n  '.join(fuera))
    return pares


def _outside_limits(ancho: int, alto: int, limits: dict) -> str:
    corto, largo = sorted((ancho, alto))
    if corto < limits['min_side']:
        return f'el lado corto es menor que {limits["min_side"]} px'
    if largo > limits['max_side']:
        return f'el lado largo pasa de {limits["max_side"]} px'
    if largo > corto * limits['max_ratio']:
        return f'la proporción {largo / corto:.2f}:1 pasa de {limits["max_ratio"]}:1'
    return ''


def render_sized(shot: Shot, size: dict | None, out_dir: Path, destination: str) -> Derived:
    """Un crudo -> un PNG sin canal alfa, nativo o de la medida exacta del destino.

    Las tiendas rechazan PNG con alfa. Con medida, se escala hasta cubrirla
    (aqui si se agranda: la medida es exacta) y se recorta del centro lo que
    sobra, que `plan` ya limito a `max_crop`.
    """
    from PIL import Image

    with Image.open(shot.path) as original:
        imagen = original.convert('RGB')
    if size is None:
        nombre = f'{shot.screen}.{shot.theme}.png'
    else:
        ancho, alto = size['width'], size['height']
        escala = max(ancho / imagen.width, alto / imagen.height)
        imagen = imagen.resize((max(ancho, round(imagen.width * escala)),
                                max(alto, round(imagen.height * escala))),
                               Image.Resampling.LANCZOS)
        izquierda = (imagen.width - ancho) // 2
        arriba = (imagen.height - alto) // 2
        imagen = imagen.crop((izquierda, arriba, izquierda + ancho, arriba + alto))
        nombre = f'{shot.screen}.{shot.theme}.{size["name"]}.png'
    # Las tiendas agrupan por idioma: una tanda por carpeta de idioma.
    destino = out_dir / shot.language / shot.app / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(destino, 'PNG', optimize=True)
    return Derived(shot, destination, destino, imagen.width, imagen.height)


def render_archive(crudos: list[Shot], out_dir: Path, destination: str) -> list[Derived]:
    """Los crudos, tal cual y sin comprimir, en un ZIP (press kit)."""
    from PIL import Image

    archivo = out_dir / 'capturas.zip'
    archivo.parent.mkdir(parents=True, exist_ok=True)
    derivados = []
    with zipfile.ZipFile(archivo, 'w', zipfile.ZIP_STORED) as zip_:
        for shot in crudos:
            miembro = f'{shot.app}/{shot.stem}.png'
            zip_.write(shot.path, miembro)
            with Image.open(shot.path) as imagen:
                derivados.append(Derived(shot, destination, archivo, imagen.width,
                                         imagen.height, archive=miembro))
    return derivados


@dataclass(frozen=True)
class Changes:
    """Lo que cambio entre el manifiesto anterior de un destino y el nuevo."""
    changed: list[str]
    added: list[str]
    removed: list[str]


def write_manifest(out_dir: Path, destination: str, derivados: list[Derived]) -> Changes:
    """Escribe `capturas.json` del destino y dice que cambio respecto del anterior.

    Es lo que la landing y el manual indexan en vez de escribir rutas a mano.
    Sin fecha y ordenado: dos corridas iguales dan el mismo archivo, y comparar
    el hash de cada entrada con el de la corrida anterior es la regresion visual.
    """
    items = []
    for d in derivados:
        item = {'app': d.shot.app, 'screen': d.shot.screen, 'theme': d.shot.theme,
                'language': d.shot.language, 'file': d.path.relative_to(out_dir).as_posix(),
                'width': d.width, 'height': d.height,
                'sha256': hashlib.sha256((d.shot.path if d.archive else d.path).read_bytes()).hexdigest()}
        if d.archive:
            item['member'] = d.archive
        items.append(item)
    items.sort(key=lambda i: (i['app'], i['screen'], i['theme'], i['language'], i['file']))

    salida = out_dir / MANIFEST
    antes = ({_entry(i): i['sha256'] for i in json.loads(salida.read_text(encoding='utf-8'))['items']}
             if salida.is_file() else {})
    ahora = {_entry(i): i['sha256'] for i in items}
    salida.write_text(json.dumps({'destination': destination, 'items': items},
                                 indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return Changes(changed=sorted(k for k in ahora.keys() & antes.keys() if ahora[k] != antes[k]),
                   added=sorted(ahora.keys() - antes.keys()),
                   removed=sorted(antes.keys() - ahora.keys()))


def _entry(item: dict) -> str:
    return item.get('member') or item['file']
