from __future__ import annotations
import json
import re
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


def render_landing(shot: Shot, preset: dict, out_dir: Path) -> Path:
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
    return destino
