from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from . import targets
from .errors import MissingConfig, TaskError
from .files import read_text

"""
Iconos de las apps a partir del logo del repo.

El repo pone el SVG (`BRAND_ICON`) y cada app dice donde va su icono: una app
Flutter en la seccion `flutter_launcher_icons:` de su pubspec, una SPA con el
`src/lib/assets/favicon.svg` que importa su `+layout.svelte`. Aca vive todo lo
que no es rasterizar: que apps toman su icono de Consola y que archivo va a
cada lugar. Rasterizar usa Qt y vive en `core/tasks/images.py` (ADR-0055).
"""

ICON_KINDS = (targets.FLUTTER_APP, targets.SPA_VITE)

# El que importa el `+layout.svelte` de la plantilla de SvelteKit. Una SPA sin
# este archivo toma su icono de otro lado (la landing de vettore importa el
# logo directo) y no se le ofrece.
SPA_FAVICON = Path('src/lib/assets/favicon.svg')

SECTION = 'flutter_launcher_icons'
# Las claves del pubspec que llevan el logo tal cual. Las anidadas van con su
# plataforma delante, como las devuelve `yaml_section`.
LOGO_KEYS = ('image_path', 'image_path_android', 'image_path_ios',
             'web.image_path', 'windows.image_path', 'macos.image_path')
FOREGROUND_KEY = 'adaptive_icon_foreground'
# Cualquier otra clave que apunte a una imagen pide un dibujo que el repo no
# declara (el monocromo de Android, el oscuro de iOS): no se adivina cual es.
_IMAGE_VALUE = re.compile(r'\.(png|jpe?g|webp)$', re.IGNORECASE)

# Lado del PNG que se le da a `flutter_launcher_icons`: el de la tienda de iOS,
# el mas grande que el paquete recorta.
RASTER_SIZE = 1024

# YAML: un `#` abre comentario al principio de la linea o despues de un blanco.
# Dentro de comillas (`"#0b1224"`) no hay blanco delante, y no se toca.
_COMMENT = re.compile(r'(?:^|\s)#.*$')


@dataclass(frozen=True)
class IconJob:
    """Lo que se genera para una app: que SVG va a que archivo."""
    app: str
    kind: str
    path: Path
    writes: tuple[tuple[Path, Path], ...]   # (SVG de origen, archivo de la app)

    @property
    def is_flutter(self) -> bool:
        return self.kind == targets.FLUTTER_APP


def yaml_section(text: str, name: str) -> dict[str, str] | None:
    """Las claves de una seccion de primer nivel de un YAML, o None si no esta.

    Las anidadas vuelven como `web.image_path`, y una clave que abre un bloque
    vuelve con valor vacio. Alcanza para lo que se lee de un pubspec: mapas de
    escalares, sin listas ni textos de varias lineas. Consola no depende de un
    lector de YAML para leer diez renglones.
    """
    salida: dict[str, str] = {}
    encontrada = dentro = False
    padres: list[tuple[int, str]] = []
    for linea in text.splitlines():
        linea = _COMMENT.sub('', linea).rstrip()
        if not linea.strip():
            continue
        sangria = len(linea) - len(linea.lstrip(' '))
        if sangria == 0:
            dentro = linea == f'{name}:'
            encontrada = encontrada or dentro
            padres = []
            continue
        if not dentro:
            continue
        clave, _, valor = linea.strip().partition(':')
        while padres and padres[-1][0] >= sangria:
            padres.pop()
        ruta = '.'.join([p for _, p in padres] + [clave.strip()])
        valor = valor.strip().strip('"\'')
        salida[ruta] = valor
        if not valor:
            padres.append((sangria, clave.strip()))
    return salida if encontrada else None


def takes_icon(target: targets.Target) -> bool:
    """Si la app dice donde va su icono, que es lo que la hace elegible."""
    if target.kind == targets.SPA_VITE:
        return (target.path / SPA_FAVICON).is_file()
    if target.kind == targets.FLUTTER_APP:
        return yaml_section(read_text(target.path / 'pubspec.yaml'), SECTION) is not None
    return False


def icon_apps(root: Path) -> list[targets.Target]:
    """Las apps del repo que toman su icono de Consola, por nombre."""
    return sorted((t for t in targets.by_kinds(root, ICON_KINDS) if takes_icon(t)),
                  key=lambda t: t.name)


def brand_file(root: Path, value: str, key: str) -> Path:
    """Un SVG de la configuracion, relativo a la raiz del repo."""
    ruta = root / value
    if ruta.suffix.lower() != '.svg':
        raise TaskError(f'{key} tiene que ser un SVG: {value}')
    if not ruta.is_file():
        raise TaskError(f'No existe {key}: {ruta}')
    return ruta


def plan(root: Path, name: str, logo: Path, foreground: Path | None) -> IconJob:
    """Que archivo va a donde en la app `name`. Corta antes de escribir nada."""
    target = targets.pick(root, ICON_KINDS, name)
    if target.kind == targets.SPA_VITE:
        destino = target.path / SPA_FAVICON
        if not destino.is_file():
            raise TaskError(f'{name} no tiene {SPA_FAVICON.as_posix()}: toma su ícono de '
                            'otro lado.')
        return IconJob(name, target.kind, target.path, ((logo, destino),))
    return IconJob(name, target.kind, target.path, _flutter_writes(target, logo, foreground))


def _flutter_writes(target: targets.Target, logo: Path,
                    foreground: Path | None) -> tuple[tuple[Path, Path], ...]:
    """Los PNG que lee `flutter_launcher_icons`, en las rutas que declara el pubspec.

    Las rutas se leen del pubspec y no de otra clave: ese archivo ya dice que
    PNG consume el paquete, y escribirlas dos veces seria una segunda fuente que
    se desfasa.
    """
    pubspec = read_text(target.path / 'pubspec.yaml')
    seccion = yaml_section(pubspec, SECTION)
    if seccion is None:
        raise TaskError(f'{target.name}: el pubspec.yaml no tiene sección {SECTION}:')
    dependencias = yaml_section(pubspec, 'dev_dependencies') or {}
    if SECTION not in dependencias:
        raise TaskError(f'{target.name}: falta {SECTION} en dev_dependencies del pubspec.yaml.')

    escrituras: dict[Path, Path] = {}
    for clave, valor in seccion.items():
        if clave in LOGO_KEYS and valor:
            origen = logo
        elif clave == FOREGROUND_KEY and valor:
            if foreground is None:
                raise MissingConfig(['BRAND_ICON_FOREGROUND'])
            origen = foreground
        elif _IMAGE_VALUE.search(valor):
            raise TaskError(f'{target.name}: el pubspec pide una imagen en {clave} y Consola '
                            'no sabe qué dibujo va ahí.')
        else:
            continue
        destino = target.path / valor
        if escrituras.get(destino, origen) != origen:
            raise TaskError(f'{target.name}: {valor} lleva el logo y la capa frontal a la vez.')
        escrituras[destino] = origen

    if logo not in escrituras.values():
        raise TaskError(f'{target.name}: la sección {SECTION} no declara image_path.')
    return tuple((origen, destino) for destino, origen in escrituras.items())
