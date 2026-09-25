from __future__ import annotations
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
  manifest de `VitePWA` en su `vite.config`.

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
_PWA_PLUGIN = re.compile(r'\b(?:VitePWA|SvelteKitPWA)\(')
_PWA_ICONS = re.compile(r'\bicons\s*:\s*\[(.*?)\]', re.DOTALL)
_PWA_ENTRY = re.compile(r'\{([^{}]*)\}')
# Una propiedad de un objeto de JS con texto literal: entre comillas o entre
# acentos graves.
_JS_PROP = re.compile(r'\b(src|sizes|purpose)\s*:\s*([\'"`])(.*?)\2', re.DOTALL)


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
        return _merge(target.name, [*_link_places(target), *_pwa_places(target)])
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
    for html in ('src/app.html', 'index.html'):
        archivo = target.path / html
        if archivo.is_file():
            lugares += [_static_place(target, href, tamano)
                        for href, tamano, literal in _icon_links(read_text(archivo)) if literal]
    return lugares


def _icon_links(texto: str) -> list[tuple[str, str, bool]]:
    """(href, sizes, si el href es texto literal) de cada `<link>` de icono."""
    salida = []
    for etiqueta in _LINK.findall(texto):
        attrs = {m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3),
                                      m.group(4))
                 for m in _ATTR.finditer(etiqueta)}
        rel = (attrs.get('rel') or ('', None))[0] or ''
        if rel.lower() not in _ICON_RELS or 'href' not in attrs:
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


def _static_place(target: targets.Target, href: str, tamano: str) -> Place:
    if re.match(r'^[a-z]+:', href, re.IGNORECASE) or href.startswith('//'):
        raise TaskError(f'{target.name}: el ícono apunta fuera de la app: {href}')
    relativo = re.sub(r'^%sveltekit\.assets%', '', href).lstrip('/')
    return _place(target, _static_dir(target) / relativo, tamano, href)


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


def _pwa_places(target: targets.Target) -> list[Place]:
    """Los iconos del manifest de la PWA, con su capa segun el `purpose`.

    El plugin es `VitePWA` de `vite-plugin-pwa`, o `SvelteKitPWA` de
    `@vite-pwa/sveltekit`: el mismo manifest con otro envoltorio.
    """
    for config in sorted(target.path.glob('vite.config.*')):
        texto = read_text(config)
        if not _PWA_PLUGIN.search(texto):
            continue
        bloque = _PWA_ICONS.search(texto)
        if not bloque:
            return []
        # El `${base}` de la ruta es la base de la app, que no cambia donde esta
        # el archivo; fuera, deja de cortar las llaves de cada entrada.
        entradas = re.sub(r'\$\{[^}]*\}', '', bloque.group(1))
        lugares = []
        for entrada in _PWA_ENTRY.findall(entradas):
            props = {m.group(1): m.group(3) for m in _JS_PROP.finditer(entrada)}
            if 'src' not in props or 'sizes' not in props:
                raise TaskError(f'{target.name}: un ícono del manifest en {config.name} no '
                                'tiene src y sizes escritos como texto.')
            lugar = _static_place(target, props['src'], props['sizes'])
            capa = MASKABLE if 'maskable' in props.get('purpose', '').split() else LOGO
            lugares.append(Place(lugar.path, capa, lugar.size))
        return lugares
    return []


def _merge(app: str, lugares: list[Place]) -> list[Place]:
    """Un lugar por archivo.

    Un archivo que el manifest declara `any` y `maskable` lleva la capa
    maskable: sirve para los dos usos, y el logo recortado por Android no.
    """
    por_ruta: dict[Path, Place] = {}
    for lugar in lugares:
        previo = por_ruta.get(lugar.path)
        if previo is None or previo == lugar:
            por_ruta[lugar.path] = lugar
            continue
        if previo.size != lugar.size:
            raise TaskError(f'{app}: {lugar.path.name} se declara de dos tamaños: '
                            f'{previo.size} y {lugar.size}.')
        capas = {previo.layer, lugar.layer}
        if capas != {LOGO, MASKABLE}:
            raise TaskError(f'{app}: {lugar.path.name} lleva dos capas distintas: '
                            f'{", ".join(sorted(capas))}.')
        por_ruta[lugar.path] = Place(lugar.path, MASKABLE, lugar.size)
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
