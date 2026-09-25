from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import targets
from .errors import MissingConfig, TaskError
from .files import read_text

"""
Iconos de las apps a partir del logo del repo.

El repo pone los SVG y cada app dice donde va su icono (ADR-0055, ADR-0056):

- una app Flutter, en la seccion `flutter_launcher_icons:` de su pubspec;
- una app Flet, con el `src/assets/icon.png` que toma `flet build`;
- una SPA, con los `<link rel="icon">` y `<link rel="apple-touch-icon">` de su
  `+layout.svelte`, su `app.html` o su `index.html`, y con los `icons` del
  manifest que enlaza su `<link rel="manifest">` (ADR-0057).

Aca vive todo lo que no es rasterizar: que apps toman su icono de Consola y que
capa va a cada archivo. Rasterizar usa Qt y vive en `core/tasks/raster.py`.
"""

ICON_KINDS = (targets.FLUTTER_APP, targets.FLET_APP, targets.SPA_VITE)

# Las capas: el logo, la capa frontal del icono adaptativo de Android y el
# icono maskable de una PWA. Cada una es un SVG del repo, con su clave.
LOGO = 'logo'
FOREGROUND = 'foreground'
MASKABLE = 'maskable'
LAYER_KEYS = {LOGO: 'BRAND_ICON', FOREGROUND: 'BRAND_ICON_FOREGROUND',
              MASKABLE: 'BRAND_ICON_MASKABLE'}

SECTION = 'flutter_launcher_icons'
# Las claves del pubspec que llevan el logo tal cual. Las anidadas van con su
# plataforma delante, como las devuelve `yaml_section`.
LOGO_KEYS = ('image_path', 'image_path_android', 'image_path_ios',
             'web.image_path', 'windows.image_path', 'macos.image_path')
FOREGROUND_KEY = 'adaptive_icon_foreground'
# Cualquier otra clave que apunte a una imagen pide un dibujo que el repo no
# declara (el monocromo de Android, el oscuro de iOS): no se adivina cual es.
_IMAGE_VALUE = re.compile(r'\.(png|jpe?g|webp)$', re.IGNORECASE)

# Lado del PNG que se le da a `flutter_launcher_icons` y a `flet build`: el de
# la tienda de iOS, el mas grande que recortan.
RASTER_SIZE = 1024

FLET_ICON = Path('src/assets/icon.png')

# YAML: un `#` abre comentario al principio de la linea o despues de un blanco.
# Dentro de comillas (`"#0b1224"`) no hay blanco delante, y no se toca.
_COMMENT = re.compile(r'(?:^|\s)#.*$')

_LINK = re.compile(r'<link\b[^>]*>', re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r'([\w-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|\{([^}]*)\})')
_ICON_RELS = ('icon', 'apple-touch-icon')
_SIZE = re.compile(r'(\d+)x(\d+)')
# El plugin de PWA (`VitePWA` de `vite-plugin-pwa`, `SvelteKitPWA` de
# `@vite-pwa/sveltekit`) genera el manifest salvo que se le diga `manifest: false`.
_PWA_PLUGIN = re.compile(r'\b(?:VitePWA|SvelteKitPWA)\(')
_MANIFEST_OFF = re.compile(r'\bmanifest\s*:\s*false\b')


@dataclass(frozen=True)
class Place:
    """Un archivo de la app que lleva una capa del logo.

    `size` es el lado del PNG. Un `.svg` recibe la capa tal cual y un `.ico`
    lleva los lados de `raster.ICO_SIZES`: en los dos es 0.
    """
    path: Path
    layer: str
    size: int = 0


@dataclass(frozen=True)
class IconJob:
    """Lo que se genera para una app: que SVG va a que archivo."""
    app: str
    kind: str
    path: Path
    writes: tuple[tuple[Path, Place], ...]   # (SVG de origen, archivo de la app)

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


# --- donde va el icono de cada tipo de app ---------------------------------

def places(target: targets.Target) -> list[Place]:
    """Los archivos donde la app toma su icono. Vacio si no declara ninguno.

    Una declaracion que Consola no sabe llenar corta con el motivo: la app
    pide un icono, y callarlo dejaria uno viejo sin que nadie lo note.
    """
    if target.kind == targets.FLUTTER_APP:
        return _flutter_places(target)
    if target.kind == targets.FLET_APP:
        return [Place(target.path / FLET_ICON, LOGO, RASTER_SIZE)] if (
            target.path / FLET_ICON).is_file() else []
    if target.kind == targets.SPA_VITE:
        return _merge(target.name, [*_link_places(target), *_manifest_places(target)])
    return []


def _flutter_places(target: targets.Target) -> list[Place]:
    """Los PNG que lee `flutter_launcher_icons`, en las rutas que declara el pubspec.

    Las rutas se leen del pubspec y no de otra clave: ese archivo ya dice que
    PNG consume el paquete, y escribirlas dos veces seria una segunda fuente que
    se desfasa.
    """
    pubspec = read_text(target.path / 'pubspec.yaml')
    seccion = yaml_section(pubspec, SECTION)
    if seccion is None:
        return []
    dependencias = yaml_section(pubspec, 'dev_dependencies') or {}
    if SECTION not in dependencias:
        raise TaskError(f'{target.name}: falta {SECTION} en dev_dependencies del pubspec.yaml.')
    lugares = []
    for clave, valor in seccion.items():
        if clave in LOGO_KEYS and valor:
            lugares.append(Place(target.path / valor, LOGO, RASTER_SIZE))
        elif clave == FOREGROUND_KEY and valor:
            lugares.append(Place(target.path / valor, FOREGROUND, RASTER_SIZE))
        elif _IMAGE_VALUE.search(valor):
            raise TaskError(f'{target.name}: el pubspec pide una imagen en {clave} y Consola '
                            'no sabe qué dibujo va ahí.')
    if not any(p.layer == LOGO for p in lugares):
        raise TaskError(f'{target.name}: la sección {SECTION} no declara image_path.')
    return _merge(target.name, lugares)


def _link_places(target: targets.Target) -> list[Place]:
    """Los `<link rel="icon">` y `rel="apple-touch-icon"` de la app.

    En el `+layout.svelte` el `href` es una variable importada: cuenta si el
    import es de `$lib/`, que es de la app. Uno que importa el logo de otro
    lado (`$brand/logomark.svg` en la landing de vettore) ya lo lee de la
    fuente y no hay nada que generar. En `app.html` e `index.html` el `href` es
    una ruta de los archivos estaticos.
    """
    lugares = []
    layout = target.path / 'src' / 'routes' / '+layout.svelte'
    if layout.is_file():
        texto = read_text(layout)
        for href, tamano, literal in _icon_links(texto):
            if literal:
                lugares.append(_static_place(target, href, tamano))
                continue
            importado = re.search(rf'import\s+{re.escape(href)}\s+from\s+[\'"]([^\'"]+)[\'"]', texto)
            if importado and importado.group(1).startswith('$lib/'):
                ruta = target.path / 'src' / 'lib' / importado.group(1)[len('$lib/'):]
                lugares.append(_place(target, ruta, tamano, f'el <link> de {href}'))
    for texto in _html(target):
        lugares += [_static_place(target, href, tamano)
                    for href, tamano, literal in _icon_links(texto) if literal]
    return lugares


def _html(target: targets.Target) -> list[str]:
    """El `app.html` de SvelteKit y el `index.html` de Vite que tenga la app."""
    archivos = (target.path / 'src' / 'app.html', target.path / 'index.html')
    return [read_text(a) for a in archivos if a.is_file()]


def _icon_links(texto: str, rels: tuple[str, ...] = _ICON_RELS) -> list[tuple[str, str, bool]]:
    """(href, sizes, si el href es texto literal) de cada `<link>` con uno de `rels`."""
    salida = []
    for etiqueta in _LINK.findall(texto):
        attrs = {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3),
                                      m.group(4))
                 for m in _ATTR.finditer(etiqueta)}
        rel = (attrs.get('rel') or ('', None))[0] or ''
        if rel.lower() not in rels or 'href' not in attrs:
            continue
        literal, variable = attrs['href']
        tamano = (attrs.get('sizes') or ('', None))[0] or ''
        salida.append((literal, tamano, True) if variable is None else (variable.strip(), tamano, False))
    return salida


def _static_dir(target: targets.Target) -> Path:
    """Donde sirve la app sus archivos estaticos: `static/` en SvelteKit, `public/` en Vite.

    SvelteKit se reconoce por su paquete y no por `svelte.config.js`, que
    tambien lo tiene una app de Svelte sin Kit (`spazio/frontend`).
    """
    sveltekit = '"@sveltejs/kit"' in read_text(target.path / 'package.json')
    return target.path / ('static' if sveltekit else 'public')


def _static_path(target: targets.Target, href: str) -> Path:
    """El archivo de `static/` o `public/` que sirve un `href` de la app."""
    if _external(href):
        raise TaskError(f'{target.name}: el ícono apunta fuera de la app: {href}')
    return _static_dir(target) / re.sub(r'^%sveltekit\.assets%', '', href).lstrip('/')


def _external(href: str) -> bool:
    return bool(re.match(r'^[a-z]+:', href, re.IGNORECASE)) or href.startswith('//')


def _static_place(target: targets.Target, href: str, tamano: str) -> Place:
    return _place(target, _static_path(target, href), tamano, href)


def _place(target: targets.Target, ruta: Path, tamano: str, origen: str) -> Place:
    """El lugar que corresponde a un archivo por su extension."""
    sufijo = ruta.suffix.lower()
    if sufijo in ('.svg', '.ico'):
        return Place(ruta, LOGO)
    if sufijo == '.png':
        lado = _SIZE.fullmatch(tamano.strip())
        if not lado:
            raise TaskError(f'{target.name}: {origen} es un PNG sin sizes="NxN": no se sabe '
                            'de qué tamaño generarlo.')
        if lado.group(1) != lado.group(2):
            raise TaskError(f'{target.name}: {origen} no es cuadrado ({tamano}), y el logo sí.')
        return Place(ruta, LOGO, int(lado.group(1)))
    raise TaskError(f'{target.name}: {origen} es {sufijo or "un archivo sin extensión"}, '
                    'y Consola solo genera .svg, .png e .ico.')


def _manifest_places(target: targets.Target) -> list[Place]:
    """Los iconos del manifest de la PWA, con su capa segun el `purpose`.

    El manifest es un archivo estatico que la app enlaza con `<link
    rel="manifest">`, y se lee como JSON (ADR-0057). Un `src` relativo se
    resuelve contra la carpeta del manifest, como en el navegador.
    """
    _no_generated_manifest(target)
    lugares = []
    for texto in _html(target):
        for href, _, literal in _icon_links(texto, ('manifest',)):
            if not literal:
                continue
            manifest = _static_path(target, href)
            if not manifest.is_file():
                raise TaskError(f'{target.name}: no existe el manifest {href}.')
            try:
                datos = json.loads(read_text(manifest))
            except ValueError as error:
                raise TaskError(f'{target.name}: {manifest.name} no es JSON: {error}') from None
            lugares += [_manifest_place(target, manifest, icono) for icono in datos.get('icons', [])]
    return lugares


def _manifest_place(target: targets.Target, manifest: Path, icono: dict) -> Place:
    src, tamano = icono.get('src', ''), icono.get('sizes', '')
    if not src:
        raise TaskError(f'{target.name}: un ícono de {manifest.name} no tiene src.')
    if _external(src):
        raise TaskError(f'{target.name}: el ícono apunta fuera de la app: {src}')
    ruta = _static_path(target, src) if src.startswith('/') else manifest.parent / src
    lugar = _place(target, ruta, tamano, src)
    # Android recorta el maskable y el `any` se ve entero: el mismo dibujo no
    # sirve para los dos, y cada uno va en su archivo.
    proposito = icono.get('purpose', 'any').split()
    if proposito not in (['any'], ['maskable']):
        raise TaskError(f'{target.name}: {src} tiene purpose "{" ".join(proposito)}", y '
                        'Consola genera "any" o "maskable", cada uno en su archivo.')
    return Place(lugar.path, MASKABLE if proposito == ['maskable'] else LOGO, lugar.size)


def _no_generated_manifest(target: targets.Target) -> None:
    """Corta si el plugin de PWA genera el manifest desde `vite.config`.

    Ese manifest es un objeto de TypeScript que Consola no lee: sus iconos se
    quedarian viejos sin que nadie lo note.
    """
    for config in sorted(target.path.glob('vite.config.*')):
        texto = read_text(config)
        if _PWA_PLUGIN.search(texto) and not _MANIFEST_OFF.search(texto):
            raise TaskError(f'{target.name}: el plugin de PWA de {config.name} genera el '
                            'manifest. Va en un archivo de static/ enlazado con <link '
                            'rel="manifest">, y el plugin con manifest: false.')


def _merge(app: str, lugares: list[Place]) -> list[Place]:
    """Un lugar por archivo. Un archivo declarado dos veces pide lo mismo las dos."""
    por_ruta: dict[Path, Place] = {}
    for lugar in lugares:
        previo = por_ruta.setdefault(lugar.path, lugar)
        if previo.size != lugar.size:
            raise TaskError(f'{app}: {lugar.path.name} se declara de dos tamaños: '
                            f'{previo.size} y {lugar.size}.')
        if previo.layer != lugar.layer:
            raise TaskError(f'{app}: {lugar.path.name} lleva dos capas distintas: '
                            f'{", ".join(sorted({previo.layer, lugar.layer}))}.')
    return list(por_ruta.values())


# --- que se ofrece y que se escribe ----------------------------------------

def takes_icon(target: targets.Target) -> bool:
    """Si la app dice donde va su icono, que es lo que la hace elegible.

    Una declaracion rota tambien cuenta: la app se ofrece y la corrida dice
    que tiene mal. Esconderla dejaria el error sin mostrar.
    """
    try:
        return bool(places(target))
    except TaskError:
        return True


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


def plan(root: Path, name: str, layers: dict[str, Path]) -> IconJob:
    """Que capa va a que archivo en la app `name`. Corta antes de escribir nada.

    `layers` trae los SVG de las capas configuradas. Una capa que la app pide y
    no esta configurada abre la configuracion en esa clave.
    """
    target = targets.pick(root, ICON_KINDS, name)
    lugares = places(target)
    if not lugares:
        raise TaskError(f'{name} no declara dónde va su ícono.')
    faltan = sorted({LAYER_KEYS[p.layer] for p in lugares if p.layer not in layers})
    if faltan:
        raise MissingConfig(faltan)
    return IconJob(name, target.kind, target.path,
                   tuple((layers[p.layer], p) for p in lugares))
