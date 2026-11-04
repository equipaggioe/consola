from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import targets
from app.core.errors import MissingConfig, TaskError
from app.core.files import read_text

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
LOGO = "logo"
FOREGROUND = "foreground"
MASKABLE = "maskable"
LAYER_KEYS = {
    LOGO: "BRAND_ICON",
    FOREGROUND: "BRAND_ICON_FOREGROUND",
    MASKABLE: "BRAND_ICON_MASKABLE",
}

SECTION = "flutter_launcher_icons"
# Las claves del pubspec que llevan el logo tal cual. Las anidadas van con su
# plataforma delante, como las devuelve `yaml_section`.
LOGO_KEYS = (
    "image_path",
    "image_path_android",
    "image_path_ios",
    "web.image_path",
    "windows.image_path",
    "macos.image_path",
)
FOREGROUND_KEY = "adaptive_icon_foreground"
# Cualquier otra clave que apunte a una imagen pide un dibujo que el repo no
# declara (el monocromo de Android, el oscuro de iOS): no se adivina cual es.
_IMAGE_VALUE = re.compile(r"\.(png|jpe?g|webp)$", re.IGNORECASE)

# Lado del PNG que se le da a `flutter_launcher_icons` y a `flet build`: el de
# la tienda de iOS, el mas grande que recortan.
RASTER_SIZE = 1024

FLET_ICON = Path("src/assets/icon.png")

# YAML: un `#` abre comentario al principio de la linea o despues de un blanco.
# Dentro de comillas (`"#0b1224"`) no hay blanco delante, y no se toca.
_COMMENT = re.compile(r"(?:^|\s)#.*$")

_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r'([\w-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|\{([^}]*)\})')
_ICON_RELS = ("icon", "apple-touch-icon")
_SIZE = re.compile(r"(\d+)x(\d+)")
# El plugin de PWA (`VitePWA` de `vite-plugin-pwa`, `SvelteKitPWA` de
# `@vite-pwa/sveltekit`) genera el manifest salvo que se le diga `manifest: false`.
_PWA_PLUGIN = re.compile(r"\b(?:VitePWA|SvelteKitPWA)\(")
_MANIFEST_OFF = re.compile(r"\bmanifest\s*:\s*false\b")


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
    writes: tuple[tuple[Path, Place], ...]  # (SVG de origen, archivo de la app)

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
    output: dict[str, str] = {}
    found = inside = False
    parents: list[tuple[int, str]] = []
    for line in text.splitlines():
        line = _COMMENT.sub("", line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            inside = line == f"{name}:"
            found = found or inside
            parents = []
            continue
        if not inside:
            continue
        key, _, value = line.strip().partition(":")
        while parents and parents[-1][0] >= indent:
            parents.pop()
        path = ".".join([p for _, p in parents] + [key.strip()])
        value = value.strip().strip("\"'")
        output[path] = value
        if not value:
            parents.append((indent, key.strip()))
    return output if found else None


# --- donde va el icono de cada tipo de app ---------------------------------


def places(target: targets.Target) -> list[Place]:
    """Los archivos donde la app toma su icono. Vacio si no declara ninguno.

    Una declaracion que Consola no sabe llenar corta con el motivo: la app
    pide un icono, y callarlo dejaria uno viejo sin que nadie lo note.
    """
    if target.kind == targets.FLUTTER_APP:
        return _flutter_places(target)
    if target.kind == targets.FLET_APP:
        return (
            [Place(target.path / FLET_ICON, LOGO, RASTER_SIZE)]
            if (target.path / FLET_ICON).is_file()
            else []
        )
    if target.kind == targets.SPA_VITE:
        return _merge(target.name, [*_link_places(target), *_manifest_places(target)])
    return []


def _flutter_places(target: targets.Target) -> list[Place]:
    """Los PNG que lee `flutter_launcher_icons`, en las rutas que declara el pubspec.

    Las rutas se leen del pubspec y no de otra clave: ese archivo ya dice que
    PNG consume el paquete, y escribirlas dos veces seria una segunda fuente que
    se desfasa.
    """
    pubspec = read_text(target.path / "pubspec.yaml")
    section = yaml_section(pubspec, SECTION)
    if section is None:
        return []
    dependencies = yaml_section(pubspec, "dev_dependencies") or {}
    if SECTION not in dependencies:
        raise TaskError(f"{target.name}: falta {SECTION} en dev_dependencies del pubspec.yaml.")
    found_places = []
    for key, value in section.items():
        if key in LOGO_KEYS and value:
            found_places.append(Place(target.path / value, LOGO, RASTER_SIZE))
        elif key == FOREGROUND_KEY and value:
            found_places.append(Place(target.path / value, FOREGROUND, RASTER_SIZE))
        elif _IMAGE_VALUE.search(value):
            raise TaskError(
                f"{target.name}: el pubspec pide una imagen en {key} y Consola "
                "no sabe qué dibujo va ahí."
            )
    if not any(p.layer == LOGO for p in found_places):
        raise TaskError(f"{target.name}: la sección {SECTION} no declara image_path.")
    return _merge(target.name, found_places)


def _link_places(target: targets.Target) -> list[Place]:
    """Los `<link rel="icon">` y `rel="apple-touch-icon"` de la app.

    En el `+layout.svelte` el `href` es una variable importada: cuenta si el
    import es de `$lib/`, que es de la app. Uno que importa el logo de otro
    lado (`$brand/logomark.svg` en la landing de vettore) ya lo lee de la
    fuente y no hay nada que generar. En `app.html` e `index.html` el `href` es
    una ruta de los archivos estaticos.
    """
    found_places = []
    layout = target.path / "src" / "routes" / "+layout.svelte"
    if layout.is_file():
        text = read_text(layout)
        for href, size, literal in _icon_links(text):
            if literal:
                found_places.append(_static_place(target, href, size))
                continue
            imported = re.search(rf'import\s+{re.escape(href)}\s+from\s+[\'"]([^\'"]+)[\'"]', text)
            if imported and imported.group(1).startswith("$lib/"):
                path = target.path / "src" / "lib" / imported.group(1)[len("$lib/") :]
                found_places.append(_place(target, path, size, f"el <link> de {href}"))
    for text in _html(target):
        found_places += [
            _static_place(target, href, size)
            for href, size, literal in _icon_links(text)
            if literal
        ]
    return found_places


def _html(target: targets.Target) -> list[str]:
    """El `app.html` de SvelteKit y el `index.html` de Vite que tenga la app."""
    files = (target.path / "src" / "app.html", target.path / "index.html")
    return [read_text(a) for a in files if a.is_file()]


def _icon_links(text: str, rels: tuple[str, ...] = _ICON_RELS) -> list[tuple[str, str, bool]]:
    """(href, sizes, si el href es texto literal) de cada `<link>` con uno de `rels`."""
    output = []
    for label in _LINK.findall(text):
        attrs = {
            m.group(1).lower(): (m.group(2) if m.group(2) is not None else m.group(3), m.group(4))
            for m in _ATTR.finditer(label)
        }
        rel = (attrs.get("rel") or ("", None))[0] or ""
        if rel.lower() not in rels or "href" not in attrs:
            continue
        literal, variable = attrs["href"]
        size = (attrs.get("sizes") or ("", None))[0] or ""
        output.append(
            (literal, size, True) if variable is None else (variable.strip(), size, False)
        )
    return output


def _static_dir(target: targets.Target) -> Path:
    """Donde sirve la app sus archivos estaticos: `static/` en SvelteKit, `public/` en Vite.

    SvelteKit se reconoce por su paquete y no por `svelte.config.js`, que
    tambien lo tiene una app de Svelte sin Kit (`spazio/frontend`).
    """
    sveltekit = '"@sveltejs/kit"' in read_text(target.path / "package.json")
    return target.path / ("static" if sveltekit else "public")


def _static_path(target: targets.Target, href: str) -> Path:
    """El archivo de `static/` o `public/` que sirve un `href` de la app."""
    if _external(href):
        raise TaskError(f"{target.name}: el ícono apunta fuera de la app: {href}")
    return _static_dir(target) / re.sub(r"^%sveltekit\.assets%", "", href).lstrip("/")


def _external(href: str) -> bool:
    return bool(re.match(r"^[a-z]+:", href, re.IGNORECASE)) or href.startswith("//")


def _static_place(target: targets.Target, href: str, size: str) -> Place:
    return _place(target, _static_path(target, href), size, href)


def _place(target: targets.Target, path: Path, size: str, source: str) -> Place:
    """El lugar que corresponde a un archivo por su extension."""
    suffix = path.suffix.lower()
    if suffix in (".svg", ".ico"):
        return Place(path, LOGO)
    if suffix == ".png":
        side = _SIZE.fullmatch(size.strip())
        if not side:
            raise TaskError(
                f'{target.name}: {source} es un PNG sin sizes="NxN": no se sabe '
                "de qué tamaño generarlo."
            )
        if side.group(1) != side.group(2):
            raise TaskError(f"{target.name}: {source} no es cuadrado ({size}), y el logo sí.")
        return Place(path, LOGO, int(side.group(1)))
    raise TaskError(
        f"{target.name}: {source} es {suffix or 'un archivo sin extensión'}, "
        "y Consola solo genera .svg, .png e .ico."
    )


def _manifest_places(target: targets.Target) -> list[Place]:
    """Los iconos del manifest de la PWA, con su capa segun el `purpose`.

    El manifest es un archivo estatico que la app enlaza con `<link
    rel="manifest">`, y se lee como JSON (ADR-0057). Un `src` relativo se
    resuelve contra la carpeta del manifest, como en el navegador.
    """
    _no_generated_manifest(target)
    found_places: list[Place] = []
    for text in _html(target):
        for href, _, literal in _icon_links(text, ("manifest",)):
            if not literal:
                continue
            manifest = _static_path(target, href)
            if not manifest.is_file():
                raise TaskError(f"{target.name}: no existe el manifest {href}.")
            try:
                data = json.loads(read_text(manifest))
            except ValueError as error:
                raise TaskError(f"{target.name}: {manifest.name} no es JSON: {error}") from None
            found_places += [
                _manifest_place(target, manifest, icon) for icon in data.get("icons", [])
            ]
    return found_places


def _manifest_place(target: targets.Target, manifest: Path, icon: dict[str, Any]) -> Place:
    src, size = icon.get("src", ""), icon.get("sizes", "")
    if not src:
        raise TaskError(f"{target.name}: un ícono de {manifest.name} no tiene src.")
    if _external(src):
        raise TaskError(f"{target.name}: el ícono apunta fuera de la app: {src}")
    path = _static_path(target, src) if src.startswith("/") else manifest.parent / src
    place = _place(target, path, size, src)
    # Android recorta el maskable y el `any` se ve entero: el mismo dibujo no
    # sirve para los dos, y cada uno va en su archivo.
    purpose = icon.get("purpose", "any").split()
    if purpose not in (["any"], ["maskable"]):
        raise TaskError(
            f'{target.name}: {src} tiene purpose "{" ".join(purpose)}", y '
            'Consola genera "any" o "maskable", cada uno en su archivo.'
        )
    return Place(place.path, MASKABLE if purpose == ["maskable"] else LOGO, place.size)


def _no_generated_manifest(target: targets.Target) -> None:
    """Corta si el plugin de PWA genera el manifest desde `vite.config`.

    Ese manifest es un objeto de TypeScript que Consola no lee: sus iconos se
    quedarian viejos sin que nadie lo note.
    """
    for config in sorted(target.path.glob("vite.config.*")):
        text = read_text(config)
        if _PWA_PLUGIN.search(text) and not _MANIFEST_OFF.search(text):
            raise TaskError(
                f"{target.name}: el plugin de PWA de {config.name} genera el "
                "manifest. Va en un archivo de static/ enlazado con <link "
                'rel="manifest">, y el plugin con manifest: false.'
            )


def _merge(app: str, found_places: list[Place]) -> list[Place]:
    """Un lugar por archivo. Un archivo declarado dos veces pide lo mismo las dos."""
    by_path: dict[Path, Place] = {}
    for place in found_places:
        previous = by_path.setdefault(place.path, place)
        if previous.size != place.size:
            raise TaskError(
                f"{app}: {place.path.name} se declara de dos tamaños: "
                f"{previous.size} y {place.size}."
            )
        if previous.layer != place.layer:
            raise TaskError(
                f"{app}: {place.path.name} lleva dos capas distintas: "
                f"{', '.join(sorted({previous.layer, place.layer}))}."
            )
    return list(by_path.values())


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
    return sorted(
        (t for t in targets.by_kinds(root, ICON_KINDS) if takes_icon(t)), key=lambda t: t.name
    )


def brand_file(root: Path, value: str, key: str) -> Path:
    """Un SVG de la configuracion, relativo a la raiz del repo."""
    path = root / value
    if path.suffix.lower() != ".svg":
        raise TaskError(f"{key} tiene que ser un SVG: {value}")
    if not path.is_file():
        raise TaskError(f"No existe {key}: {path}")
    return path


def plan(root: Path, name: str, layers: dict[str, Path]) -> IconJob:
    """Que capa va a que archivo en la app `name`. Corta antes de escribir nada.

    `layers` trae los SVG de las capas configuradas. Una capa que la app pide y
    no esta configurada abre la configuracion en esa clave.
    """
    target = targets.pick(root, ICON_KINDS, name)
    found_places = places(target)
    if not found_places:
        raise TaskError(f"{name} no declara dónde va su ícono.")
    missing = sorted({LAYER_KEYS[p.layer] for p in found_places if p.layer not in layers})
    if missing:
        raise MissingConfig(missing)
    return IconJob(
        name, target.kind, target.path, tuple((layers[p.layer], p) for p in found_places)
    )
