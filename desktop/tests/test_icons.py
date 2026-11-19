"""The icons that come from the repo's logo.

It builds a fake repo with the shapes real repos have: SPAs with the
template's favicon, with `static/favicon.svg` in their `app.html`, with
the logo imported from elsewhere and with a PWA's static manifest; a
Flutter app with its `flutter_launcher_icons:` section; and a Flet app
with its `icon.png`.
"""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.services import icons
from app.services.context import TaskContext
from app.services.envfile import Config
from app.services.errors import MissingConfig, TaskError
from app.services.projects import Project
from app.services.tasks import images, raster

LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
    '<rect x="4" y="4" width="56" height="56" rx="16" fill="#0b1224"/></svg>'
)

PUBSPEC = """\
name: app
dev_dependencies:
  flutter_launcher_icons: ^0.14.3  # los PNG los genera Consola
flutter_launcher_icons:
  android: true
  image_path: "assets/launcher_icon/icon.png"
  adaptive_icon_background: "#0b1224"
  adaptive_icon_foreground: "assets/launcher_icon/icon_foreground.png"
  web:
    generate: true
    image_path: "assets/launcher_icon/icon.png"
flutter:
  uses-material-design: true
"""

LAYOUT = """<script>
	import favicon from '$lib/assets/favicon.svg';
</script>
<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>
"""

VITE_PWA = """import { SvelteKitPWA } from '@vite-pwa/sveltekit';
export default defineConfig({
  plugins: [SvelteKitPWA({ registerType: 'autoUpdate', manifest: false })]
});
"""

MANIFEST_LINK = '<link rel="manifest" href="%sveltekit.assets%/manifest.webmanifest" />'


def manifest(*icons: dict[str, str]) -> str:
    """Return a web manifest with those icons."""
    return json.dumps(
        {
            "name": "Web",
            "start_url": "./",
            "icons": list(icons),
            "screenshots": [{"src": "wide.png", "sizes": "1280x720"}],
        }
    )


MANIFEST = manifest(
    {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "icons/icon-512.png", "sizes": "512x512", "purpose": "any"},
    {"src": "icons/icon-512-maskable.png", "sizes": "512x512", "purpose": "maskable"},
    {"src": "/apple.png", "sizes": "180x180"},
)


def write(path: Path, text: str) -> Path:
    """Write a file, creating its folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def spa(root: Path, name: str, sveltekit: bool = True, **files: str) -> Path:
    """Create an SPA with those files."""
    folder = root / name
    kit = '"@sveltejs/kit": "^2.0.0", ' if sveltekit else ""
    write(folder / "package.json", f'{{"devDependencies": {{{kit}"svelte": "^5.0.0"}}}}')
    write(folder / "vite.config.ts", files.pop("vite", ""))
    # A Svelte app without Kit also has its svelte.config.js.
    write(folder / "svelte.config.js", "")
    for relative, text in files.items():
        write(folder / relative.replace("__", "/"), text)
    return folder


def flutter(root: Path, name: str, pubspec: str) -> Path:
    """Create a Flutter app with that pubspec."""
    return write(root / name / "pubspec.yaml", pubspec).parent


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a repo with one app of each shape."""
    spa(
        tmp_path,
        "panel",
        **{
            "src__routes__+layout.svelte": LAYOUT,
            "src__lib__assets__favicon.svg": "<svg>svelte</svg>",
        },
    )
    spa(
        tmp_path,
        "landing",
        **{"src__app.html": '<link rel="icon" href="%sveltekit.assets%/favicon.svg" />'},
    )
    spa(
        tmp_path,
        "externa",
        **{
            "src__routes__+layout.svelte": LAYOUT.replace(
                "$lib/assets/favicon.svg", "$brand/logomark.svg"
            )
        },
    )
    spa(
        tmp_path,
        "pwa",
        vite=VITE_PWA,
        **{"src__app.html": MANIFEST_LINK, "static__manifest.webmanifest": MANIFEST},
    )
    spa(
        tmp_path,
        "vite",
        sveltekit=False,
        **{"index.html": '<link rel="icon" type="image/svg+xml" href="/vite.svg" />'},
    )
    spa(tmp_path, "no_icon")
    flutter(tmp_path, "mobile", PUBSPEC)
    flutter(tmp_path, "suelta", "name: suelta\n")
    flet = tmp_path / "cliente"
    write(flet / "pyproject.toml", "[tool.flet]\n")
    write(flet / "src" / "main.py", "import flet\n")
    (flet / "src" / "assets").mkdir()
    Image.new("RGB", (8, 8)).save(flet / icons.FLET_ICON)
    for name in ("logomark", "foreground", "maskable"):
        write(tmp_path / "brand" / f"{name}.svg", LOGO)
    return tmp_path


def layers(repo: Path, *layer_names: str) -> dict[str, Path]:
    """Create the logo's layers."""
    files = {icons.LOGO: "logomark", icons.FOREGROUND: "foreground", icons.MASKABLE: "maskable"}
    return {c: repo / "brand" / f"{files[c]}.svg" for c in layer_names}


def test_the_section_reads_with_nested_keys_and_without_comments() -> None:
    """The section reads with nested keys and without comments."""
    assert icons.yaml_section(PUBSPEC, "flutter_launcher_icons") == {
        "android": "true",
        "image_path": "assets/launcher_icon/icon.png",
        "adaptive_icon_background": "#0b1224",
        "adaptive_icon_foreground": "assets/launcher_icon/icon_foreground.png",
        "web": "",
        "web.generate": "true",
        "web.image_path": "assets/launcher_icon/icon.png",
    }
    assert icons.yaml_section(PUBSPEC, "dev_dependencies") == {"flutter_launcher_icons": "^0.14.3"}
    assert icons.yaml_section("name: x\n", "flutter_launcher_icons") is None


def test_only_apps_that_say_where_their_icon_goes_are_offered(repo: Path) -> None:
    """Only apps that say where their icon goes are offered."""
    assert [t.name for t in icons.icon_apps(repo)] == [
        "cliente",
        "landing",
        "mobile",
        "panel",
        "pwa",
        "vite",
    ]


def test_each_spa_takes_the_icon_where_it_declares_it(repo: Path) -> None:
    """Each SPA takes the icon where it declares it."""

    def places(name: str) -> list[tuple[str, str, int]]:
        target = icons.targets.pick(repo, icons.ICON_KINDS, name)
        return [
            (p.path.relative_to(repo).as_posix(), p.layer, p.size) for p in icons.places(target)
        ]

    assert places("panel") == [("panel/src/lib/assets/favicon.svg", "logo", 0)]
    assert places("landing") == [("landing/static/favicon.svg", "logo", 0)]
    assert places("vite") == [("vite/public/vite.svg", "logo", 0)]
    # A relative `src` hangs from the manifest's folder; an absolute one
    # from `static/`.
    assert places("pwa") == [
        ("pwa/static/icons/icon-192.png", "logo", 192),
        ("pwa/static/icons/icon-512.png", "logo", 512),
        ("pwa/static/icons/icon-512-maskable.png", "maskable", 512),
        ("pwa/static/apple.png", "logo", 180),
    ]


def test_the_layer_an_app_asks_for_is_required_only_if_it_asks(repo: Path) -> None:
    """The layer an app asks for is required only if it asks."""
    with pytest.raises(MissingConfig) as error:
        icons.plan(repo, "pwa", layers(repo, icons.LOGO))
    assert error.value.keys == ["BRAND_ICON_MASKABLE"]
    with pytest.raises(MissingConfig) as error:
        icons.plan(repo, "mobile", layers(repo, icons.LOGO))
    assert error.value.keys == ["BRAND_ICON_FOREGROUND"]
    assert len(icons.plan(repo, "panel", layers(repo, icons.LOGO)).writes) == 1


def test_flutter_takes_the_pubspec_paths_once_each(repo: Path) -> None:
    """Flutter takes the pubspec's paths once each."""
    layer_names = layers(repo, icons.LOGO, icons.FOREGROUND)
    work = icons.plan(repo, "mobile", layer_names)
    assert work.is_flutter
    assert work.writes == (
        (
            layer_names[icons.LOGO],
            icons.Place(repo / "mobile" / "assets/launcher_icon/icon.png", icons.LOGO, 1024),
        ),
        (
            layer_names[icons.FOREGROUND],
            icons.Place(
                repo / "mobile" / "assets/launcher_icon/icon_foreground.png",
                icons.FOREGROUND,
                1024,
            ),
        ),
    )


def test_flet_receives_the_logo_in_its_icon_png(repo: Path) -> None:
    """Flet receives the logo in its `icon.png`."""
    work = icons.plan(repo, "cliente", layers(repo, icons.LOGO))
    assert [(p.path, p.size) for _, p in work.writes] == [
        (repo / "cliente" / icons.FLET_ICON, 1024)
    ]


@pytest.mark.parametrize(
    ("name", "pubspec", "error"),
    [
        (
            "no_dep",
            PUBSPEC.replace("  flutter_launcher_icons: ^0.14.3", "  flutter_lints: ^5.0.0"),
            "falta flutter_launcher_icons en dev_dependencies",
        ),
        (
            "monocromo",
            PUBSPEC.replace(
                "  android: true\n", '  android: true\n  adaptive_icon_monochrome: "b.png"\n'
            ),
            "adaptive_icon_monochrome",
        ),
        (
            "no_logo",
            "".join(row for row in PUBSPEC.splitlines(keepends=True) if "image_path" not in row),
            "no declara image_path",
        ),
    ],
)
def test_what_consola_cannot_fill_in_flutter_stops(
    repo: Path, name: str, pubspec: str, error: str
) -> None:
    """What Consola cannot fill in Flutter stops."""
    flutter(repo, name, pubspec)
    assert name in [t.name for t in icons.icon_apps(repo)]
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, name, layers(repo, icons.LOGO, icons.FOREGROUND))


@pytest.mark.parametrize(
    ("link", "error"),
    [
        ('<link rel="icon" href="/favicon.png" />', "PNG sin sizes"),
        ('<link rel="apple-touch-icon" sizes="180x120" href="/t.png" />', "no es cuadrado"),
        ('<link rel="icon" href="https://cdn.x/f.svg" />', "apunta fuera de la app"),
        ('<link rel="icon" href="/favicon.gif" />', "solo genera .svg, .png e .ico"),
    ],
)
def test_what_consola_cannot_fill_in_an_spa_stops(repo: Path, link: str, error: str) -> None:
    """What Consola cannot fill in an SPA stops."""
    spa(repo, "rota", **{"src__app.html": link})
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, "rota", layers(repo, icons.LOGO))


@pytest.mark.parametrize(
    ("vite", "statics", "error"),
    [
        (VITE_PWA.replace("manifest: false", "manifest: { icons: [] }"), {}, "genera el manifest"),
        (VITE_PWA.replace(", manifest: false", ""), {}, "genera el manifest"),
        (VITE_PWA, {}, "no existe el manifest"),
        (VITE_PWA, {"static__manifest.webmanifest": '{"icons": ['}, "no es JSON"),
        (
            VITE_PWA,
            {
                "static__manifest.webmanifest": manifest(
                    {"src": "i.png", "sizes": "512x512", "purpose": "any maskable"}
                )
            },
            "cada uno en su archivo",
        ),
        (
            VITE_PWA,
            {"static__manifest.webmanifest": manifest({"sizes": "512x512"})},
            "no tiene src",
        ),
    ],
)
def test_what_consola_cannot_fill_in_a_pwa_stops(
    repo: Path, vite: str, statics: dict[str, Any], error: str
) -> None:
    """What Consola cannot fill in a PWA stops."""
    spa(repo, "rota", vite=vite, **{"src__app.html": MANIFEST_LINK}, **statics)
    assert "rota" in [t.name for t in icons.icon_apps(repo)]
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, "rota", layers(repo, icons.LOGO, icons.MASKABLE))


def test_an_app_without_a_declaration_stops(repo: Path) -> None:
    """An app without a declaration stops."""
    with pytest.raises(TaskError, match="no declara dónde va su ícono"):
        icons.plan(repo, "externa", layers(repo, icons.LOGO))
    with pytest.raises(TaskError, match="no declara dónde va su ícono"):
        icons.plan(repo, "suelta", layers(repo, icons.LOGO))


def test_the_logo_has_to_be_an_existing_svg(repo: Path) -> None:
    """The logo has to be an existing SVG."""
    with pytest.raises(TaskError, match="tiene que ser un SVG"):
        icons.brand_file(repo, "brand/logo.png", "BRAND_ICON")
    with pytest.raises(TaskError, match="No existe BRAND_ICON"):
        icons.brand_file(repo, "brand/otro.svg", "BRAND_ICON")


def test_it_rasterizes_a_square_with_the_logo_color(repo: Path) -> None:
    """It rasterizes a square with the logo's color."""
    image = Image.open(io.BytesIO(raster.svg_to_png(repo / "brand" / "logomark.svg", 256)))
    image = image.convert("RGBA")
    assert image.size == (256, 256)
    assert image.getpixel((128, 128)) == (0x0B, 0x12, 0x24, 255)
    assert image.getchannel("A").getpixel((0, 0)) == 0


def test_the_png_does_not_depend_on_the_monitor(repo: Path) -> None:
    # With the window open, Qt wrote the monitor's resolution in the
    # PNG.
    """The PNG does not depend on the monitor."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    png = raster.svg_to_png(repo / "brand" / "logomark.svg", 64)
    assert Image.open(io.BytesIO(png)).info["dpi"] == pytest.approx((100, 100), abs=0.01)


def test_the_ico_carries_every_side(repo: Path) -> None:
    """The ICO carries every side."""
    ico = Image.open(io.BytesIO(raster.svg_to_ico(repo / "brand" / "logomark.svg")))
    assert sorted(ico.info["sizes"]) == [(n, n) for n in raster.ICO_SIZES]


def test_a_non_square_svg_stops(tmp_path: Path) -> None:
    """A non-square SVG stops."""
    width = write(
        tmp_path / "ancho.svg", LOGO.replace('viewBox="0 0 64 64"', 'viewBox="0 0 128 64"')
    )
    with pytest.raises(TaskError, match="no es cuadrado"):
        raster.svg_to_png(width, 256)


def test_the_run_writes_only_what_changes(repo: Path) -> None:
    """The run writes only what changes."""
    messages = []
    ctx = TaskContext(
        "generate_icons",
        project=Project("repo", str(repo), ""),
        config=Config(
            {"BRAND_ICON": "brand/logomark.svg", "BRAND_ICON_MASKABLE": "brand/maskable.svg"}
        ),
        log_sink=lambda msg, level: messages.append(msg),
    )
    images.generate_icons(ctx, ["panel", "pwa"])
    assert (repo / "panel" / "src/lib/assets/favicon.svg").read_text(encoding="utf-8") == LOGO
    assert Image.open(repo / "pwa" / "static/icons/icon-192.png").size == (192, 192)
    assert "  actualizado: panel/src/lib/assets/favicon.svg" in messages
    assert "  nuevo: pwa/static/icons/icon-512.png" in messages
    images.generate_icons(ctx, ["panel"])
    assert messages[-2] == "  sin cambios: panel/src/lib/assets/favicon.svg"
