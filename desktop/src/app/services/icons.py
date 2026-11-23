"""App icons from the repo's logo.

The repo supplies the SVGs and each app says where its icon goes
(ADR-0055, ADR-0056):

- a Flutter app, in the `flutter_launcher_icons:` section of its
  pubspec;
- a Flet app, with the `src/assets/icon.png` that `flet build` takes;
- an SPA, with the `<link rel="icon">` and `<link
  rel="apple-touch-icon">` of its `+layout.svelte`, `app.html` or
  `index.html`, and with the `icons` of the manifest its `<link
  rel="manifest">` links (ADR-0057).

Everything but rasterizing lives here: which apps take their icon from
Consola and which layer goes to each file. Rasterizing uses Qt and lives
in `services/tasks/raster.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.services import targets
from app.services.errors import MissingConfig, TaskError
from app.services.files import read_text
from app.services.settings import names

ICON_KINDS = (targets.FLUTTER_APP, targets.FLET_APP, targets.SPA_VITE)

# The layers: the logo, the front layer of Android's adaptive icon and a
# PWA's maskable icon. Each is an SVG of the repo, with its key.
LOGO = "logo"
FOREGROUND = "foreground"
MASKABLE = "maskable"
LAYER_KEYS = {
    LOGO: "BRAND_ICON",
    FOREGROUND: "BRAND_ICON_FOREGROUND",
    MASKABLE: "BRAND_ICON_MASKABLE",
}

SECTION = "flutter_launcher_icons"
# The pubspec keys that carry the logo as is. Nested ones go with their
# platform first, as `yaml_section` returns them.
LOGO_KEYS = (
    "image_path",
    "image_path_android",
    "image_path_ios",
    "web.image_path",
    "windows.image_path",
    "macos.image_path",
)
FOREGROUND_KEY = "adaptive_icon_foreground"
# Any other key pointing to an image asks for a drawing the repo does
# not declare (Android's monochrome, iOS's dark): it is not guessed.
_IMAGE_VALUE = re.compile(r"\.(png|jpe?g|webp)$", re.IGNORECASE)

# The side of the PNG given to `flutter_launcher_icons` and `flet
# build`: the iOS store's, the largest they crop.
RASTER_SIZE = 1024

FLET_ICON = Path("src/assets/icon.png")

# YAML: a `#` opens a comment at the start of the line or after a blank.
# Inside quotes (a quoted color) no blank comes first, and it stays.
_COMMENT = re.compile(r"(?:^|\s)#.*$")

_LINK = re.compile(r"<link\b[^>]*>", re.IGNORECASE | re.DOTALL)
_ATTR = re.compile(r'([\w-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|\{([^}]*)\})')
_ICON_RELS = ("icon", "apple-touch-icon")
_SIZE = re.compile(r"(\d+)x(\d+)")
# The PWA plugin (`VitePWA` of `vite-plugin-pwa`, `SvelteKitPWA` of
# `@vite-pwa/sveltekit`) generates the manifest unless told `manifest:
# false`.
_PWA_PLUGIN = re.compile(r"\b(?:VitePWA|SvelteKitPWA)\(")
_MANIFEST_OFF = re.compile(r"\bmanifest\s*:\s*false\b")


@dataclass(frozen=True)
class Place:
    """A file of the app that carries a layer of the logo.

    `size` is the PNG's side. An `.svg` receives the layer as is and an
    `.ico` carries the sides of `raster.ICO_SIZES`: on both it is 0.
    """

    path: Path
    layer: str
    size: int = 0


@dataclass(frozen=True)
class IconJob:
    """What is generated for an app: which SVG goes to which file."""

    app: str
    kind: str
    path: Path
    writes: tuple[tuple[Path, Place], ...]  # (source SVG, app file)

    @property
    def is_flutter(self) -> bool:
        """Return whether the app is a Flutter one."""
        return self.kind == targets.FLUTTER_APP


def yaml_section(text: str, name: str) -> dict[str, str] | None:
    """Return the keys of a top-level YAML section, or None if absent.

    Nested ones return as `web.image_path`, and a key that opens a block
    returns with an empty value. That is enough for a pubspec: maps of
    scalars, without lists or multi-line text. Consola needs no YAML
    reader for ten lines.
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


# --- where each app type's icon goes ---


def places(target: targets.Target) -> list[Place]:
    """Return the files where the app takes its icon.

    Empty if none declared.

    A declaration Consola cannot fill stops with the reason: the app
    asks for an icon, and keeping quiet would leave an old one
    unnoticed.
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
    """Return the PNGs `flutter_launcher_icons` reads, at their paths.

    Paths are read from the pubspec and no other key: that file already
    says which PNGs the package consumes, and writing them twice would
    be a second source that drifts.
    """
    pubspec = read_text(target.path / "pubspec.yaml")
    section = yaml_section(pubspec, SECTION)
    if section is None:
        return []
    dependencies = yaml_section(pubspec, "dev_dependencies") or {}
    if SECTION not in dependencies:
        raise TaskError(
            QCoreApplication.translate(
                "icons", "{0}: falta {1} en dev_dependencies del pubspec.yaml."
            ).format(target.name, SECTION)
        )
    found_places = []
    for key, value in section.items():
        if key in LOGO_KEYS and value:
            found_places.append(Place(target.path / value, LOGO, RASTER_SIZE))
        elif key == FOREGROUND_KEY and value:
            found_places.append(Place(target.path / value, FOREGROUND, RASTER_SIZE))
        elif _IMAGE_VALUE.search(value):
            raise TaskError(
                QCoreApplication.translate(
                    "icons",
                    "{0}: el pubspec pide una imagen en {1} y Consola no sabe qué dibujo va ahí.",
                ).format(target.name, key)
            )
    if not any(p.layer == LOGO for p in found_places):
        raise TaskError(
            QCoreApplication.translate(
                "icons", "{0}: la sección {1} no declara image_path."
            ).format(target.name, SECTION)
        )
    return _merge(target.name, found_places)


def _link_places(target: targets.Target) -> list[Place]:
    """Return the app's `rel="icon"` and `rel="apple-touch-icon"` links.

    In `+layout.svelte` the `href` is an imported variable: it counts if
    the import is from `$lib/`, the app's. One importing the logo from
    elsewhere (`$brand/logomark.svg`) already reads it from the source
    and there is nothing to generate. In `app.html` and `index.html` the
    `href` is a static file's path.
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
                found_places.append(
                    _place(
                        target,
                        path,
                        size,
                        QCoreApplication.translate("icons", "el <link> de {0}").format(href),
                    )
                )
    for text in _html(target):
        found_places += [
            _static_place(target, href, size)
            for href, size, literal in _icon_links(text)
            if literal
        ]
    return found_places


def _html(target: targets.Target) -> list[str]:
    """Return whichever of `app.html` and `index.html` the app has."""
    files = (target.path / "src" / "app.html", target.path / "index.html")
    return [read_text(a) for a in files if a.is_file()]


def _icon_links(text: str, rels: tuple[str, ...] = _ICON_RELS) -> list[tuple[str, str, bool]]:
    """Return (href, sizes, literal) of each `<link>` among `rels`."""
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
    """Return where the app serves static files.

    That is `static/` in SvelteKit and `public/` in Vite. SvelteKit is
    recognized by its package and not `svelte.config.js`, which a Svelte
    app without Kit also has.
    """
    sveltekit = '"@sveltejs/kit"' in read_text(target.path / "package.json")
    return target.path / ("static" if sveltekit else "public")


def _static_path(target: targets.Target, href: str) -> Path:
    """Return the `static/` or `public/` file an app's `href` serves."""
    if _external(href):
        raise TaskError(
            QCoreApplication.translate(
                "icons", "{0}: el ícono apunta fuera de la app: {1}"
            ).format(target.name, href)
        )
    return _static_dir(target) / re.sub(r"^%sveltekit\.assets%", "", href).lstrip("/")


def _external(href: str) -> bool:
    return bool(re.match(r"^[a-z]+:", href, re.IGNORECASE)) or href.startswith("//")


def _static_place(target: targets.Target, href: str, size: str) -> Place:
    return _place(target, _static_path(target, href), size, href)


def _place(target: targets.Target, path: Path, size: str, source: str) -> Place:
    """Return the place for a file, by its extension."""
    suffix = path.suffix.lower()
    if suffix in (".svg", ".ico"):
        return Place(path, LOGO)
    if suffix == ".png":
        side = _SIZE.fullmatch(size.strip())
        if not side:
            raise TaskError(
                QCoreApplication.translate(
                    "icons",
                    '{0}: {1} es un PNG sin sizes="NxN": no se sabe de qué tamaño generarlo.',
                ).format(target.name, source)
            )
        if side.group(1) != side.group(2):
            raise TaskError(
                QCoreApplication.translate(
                    "icons", "{0}: {1} no es cuadrado ({2}), y el logo sí."
                ).format(target.name, source, size)
            )
        return Place(path, LOGO, int(side.group(1)))
    raise TaskError(
        QCoreApplication.translate(
            "icons", "{0}: {1} es {2}, y Consola solo genera .svg, .png e .ico."
        ).format(
            target.name,
            source,
            suffix or QCoreApplication.translate("icons", "un archivo sin extensión"),
        )
    )


def _manifest_places(target: targets.Target) -> list[Place]:
    """Return the PWA manifest's icons, with their layer by `purpose`.

    The manifest is a static file the app links with `<link
    rel="manifest">`, and reads as JSON (ADR-0057). A relative `src`
    resolves against the manifest's folder, as in the browser.
    """
    _no_generated_manifest(target)
    found_places: list[Place] = []
    for text in _html(target):
        for href, _, literal in _icon_links(text, ("manifest",)):
            if not literal:
                continue
            manifest = _static_path(target, href)
            if not manifest.is_file():
                raise TaskError(
                    QCoreApplication.translate("icons", "{0}: no existe el manifest {1}.").format(
                        target.name, href
                    )
                )
            try:
                data = json.loads(read_text(manifest))
            except ValueError as error:
                raise TaskError(
                    QCoreApplication.translate("icons", "{0}: {1} no es JSON: {2}").format(
                        target.name, manifest.name, error
                    )
                ) from None
            found_places += [
                _manifest_place(target, manifest, icon) for icon in data.get("icons", [])
            ]
    return found_places


def _manifest_place(target: targets.Target, manifest: Path, icon: dict[str, Any]) -> Place:
    src, size = icon.get("src", ""), icon.get("sizes", "")
    if not src:
        raise TaskError(
            QCoreApplication.translate("icons", "{0}: un ícono de {1} no tiene src.").format(
                target.name, manifest.name
            )
        )
    if _external(src):
        raise TaskError(
            QCoreApplication.translate(
                "icons", "{0}: el ícono apunta fuera de la app: {1}"
            ).format(target.name, src)
        )
    path = _static_path(target, src) if src.startswith("/") else manifest.parent / src
    place = _place(target, path, size, src)
    # Android crops the maskable and `any` shows whole: the same drawing
    # does not serve both, and each goes in its own file.
    purpose = icon.get("purpose", "any").split()
    if purpose not in (["any"], ["maskable"]):
        raise TaskError(
            QCoreApplication.translate(
                "icons",
                '{0}: {1} tiene purpose "{2}", y Consola genera "any" o "maskable", cada '
                "uno en su archivo.",
            ).format(target.name, src, " ".join(purpose))
        )
    return Place(place.path, MASKABLE if purpose == ["maskable"] else LOGO, place.size)


def _no_generated_manifest(target: targets.Target) -> None:
    """Stop if the PWA plugin generates the manifest from `vite.config`.

    That manifest is a TypeScript object Consola does not read: its
    icons would go stale unnoticed.
    """
    for config in sorted(target.path.glob("vite.config.*")):
        text = read_text(config)
        if _PWA_PLUGIN.search(text) and not _MANIFEST_OFF.search(text):
            raise TaskError(
                QCoreApplication.translate(
                    "icons",
                    "{0}: el plugin de PWA de {1} genera el manifest. Va en un archivo de "
                    'static/ enlazado con <link rel="manifest">, y el plugin con manifest: '
                    "false.",
                ).format(target.name, config.name)
            )


def _merge(app: str, found_places: list[Place]) -> list[Place]:
    """Keep one place per file: twice asks for the same."""
    by_path: dict[Path, Place] = {}
    for place in found_places:
        previous = by_path.setdefault(place.path, place)
        if previous.size != place.size:
            raise TaskError(
                QCoreApplication.translate(
                    "icons", "{0}: {1} se declara de dos tamaños: {2} y {3}."
                ).format(app, place.path.name, previous.size, place.size)
            )
        if previous.layer != place.layer:
            raise TaskError(
                QCoreApplication.translate(
                    "icons", "{0}: {1} lleva dos capas distintas: {2}."
                ).format(app, place.path.name, ", ".join(sorted({previous.layer, place.layer})))
            )
    return list(by_path.values())


# --- what is offered and what is written ---


def takes_icon(target: targets.Target) -> bool:
    """Return whether the app is eligible: it says where its icon goes.

    A broken declaration counts too: the app is offered and the run says
    what is wrong. Hiding it would leave the error unshown.
    """
    try:
        return bool(places(target))
    except TaskError:
        return True


def icon_apps(root: Path) -> list[targets.Target]:
    """Return the apps that take their icon from Consola, by name."""
    return sorted(
        (t for t in targets.by_kinds(root, ICON_KINDS) if takes_icon(t)), key=lambda t: t.name
    )


def brand_file(root: Path, value: str, key: str) -> Path:
    """Return a config SVG, relative to the repo's root."""
    path = root / value
    if path.suffix.lower() != ".svg":
        raise TaskError(
            QCoreApplication.translate("icons", "{0} tiene que ser un SVG: {1}").format(
                names([key]), value
            )
        )
    if not path.is_file():
        raise TaskError(
            QCoreApplication.translate("icons", "No existe {0}: {1}").format(names([key]), path)
        )
    return path


def plan(root: Path, name: str, layers: dict[str, Path]) -> IconJob:
    """Return which layer goes to which file in `name`, writing nothing.

    `layers` brings the configured layers' SVGs. A layer the app asks
    for that is not configured opens the settings on that key.
    """
    target = targets.pick(root, ICON_KINDS, name)
    found_places = places(target)
    if not found_places:
        raise TaskError(
            QCoreApplication.translate("icons", "{0} no declara dónde va su ícono.").format(name)
        )
    missing = sorted({LAYER_KEYS[p.layer] for p in found_places if p.layer not in layers})
    if missing:
        raise MissingConfig(missing)
    return IconJob(
        name, target.kind, target.path, tuple((layers[p.layer], p) for p in found_places)
    )
