"""Los iconos que salen del logo del repo.

Se arma un repo falso con las formas que hay en los repos reales: SPA con el
favicon de la plantilla, con `static/favicon.svg` en su `app.html`, con el
logo importado de otro lado y con el manifest estatico de una PWA; una app Flutter con su
seccion `flutter_launcher_icons:`, y una app Flet con su `icon.png`.
"""
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import icons
from core.context import TaskContext
from core.envfile import Config
from core.errors import MissingConfig, TaskError
from core.projects import Project
from core.tasks import images, raster

LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect x="4" y="4" width="56" height="56" rx="16" fill="#0b1224"/></svg>')

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


def manifest(*iconos: dict) -> str:
    return json.dumps({'name': 'Web', 'start_url': './', 'icons': list(iconos),
                       'screenshots': [{'src': 'wide.png', 'sizes': '1280x720'}]})


MANIFEST = manifest(
    {'src': 'icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
    {'src': 'icons/icon-512.png', 'sizes': '512x512', 'purpose': 'any'},
    {'src': 'icons/icon-512-maskable.png', 'sizes': '512x512', 'purpose': 'maskable'},
    {'src': '/apple.png', 'sizes': '180x180'},
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def spa(root: Path, name: str, sveltekit: bool = True, **archivos: str) -> Path:
    carpeta = root / name
    kit = '"@sveltejs/kit": "^2.0.0", ' if sveltekit else ''
    write(carpeta / 'package.json', f'{{"devDependencies": {{{kit}"svelte": "^5.0.0"}}}}')
    write(carpeta / 'vite.config.ts', archivos.pop('vite', ''))
    # Una app de Svelte sin Kit tambien tiene su svelte.config.js.
    write(carpeta / 'svelte.config.js', '')
    for relativo, texto in archivos.items():
        write(carpeta / relativo.replace('__', '/'), texto)
    return carpeta


def flutter(root: Path, name: str, pubspec: str) -> Path:
    return write(root / name / 'pubspec.yaml', pubspec).parent


@pytest.fixture
def repo(tmp_path):
    spa(tmp_path, 'panel', **{'src__routes__+layout.svelte': LAYOUT,
                              'src__lib__assets__favicon.svg': '<svg>svelte</svg>'})
    spa(tmp_path, 'landing', **{'src__app.html':
                                '<link rel="icon" href="%sveltekit.assets%/favicon.svg" />'})
    spa(tmp_path, 'externa', **{'src__routes__+layout.svelte':
                                LAYOUT.replace('$lib/assets/favicon.svg', '$brand/logomark.svg')})
    spa(tmp_path, 'pwa', vite=VITE_PWA, **{'src__app.html': MANIFEST_LINK,
                                          'static__manifest.webmanifest': MANIFEST})
    spa(tmp_path, 'vite', sveltekit=False,
        **{'index.html': '<link rel="icon" type="image/svg+xml" href="/vite.svg" />'})
    spa(tmp_path, 'sin_icono')
    flutter(tmp_path, 'mobile', PUBSPEC)
    flutter(tmp_path, 'suelta', 'name: suelta\n')
    flet = tmp_path / 'cliente'
    write(flet / 'pyproject.toml', '[tool.flet]\n')
    write(flet / 'src' / 'main.py', 'import flet\n')
    (flet / 'src' / 'assets').mkdir()
    Image.new('RGB', (8, 8)).save(flet / icons.FLET_ICON)
    for nombre in ('logomark', 'foreground', 'maskable'):
        write(tmp_path / 'brand' / f'{nombre}.svg', LOGO)
    return tmp_path


def layers(repo: Path, *capas: str) -> dict[str, Path]:
    archivos = {icons.LOGO: 'logomark', icons.FOREGROUND: 'foreground', icons.MASKABLE: 'maskable'}
    return {c: repo / 'brand' / f'{archivos[c]}.svg' for c in capas}


def test_la_seccion_se_lee_con_las_claves_anidadas_y_sin_comentarios():
    assert icons.yaml_section(PUBSPEC, 'flutter_launcher_icons') == {
        'android': 'true',
        'image_path': 'assets/launcher_icon/icon.png',
        'adaptive_icon_background': '#0b1224',
        'adaptive_icon_foreground': 'assets/launcher_icon/icon_foreground.png',
        'web': '',
        'web.generate': 'true',
        'web.image_path': 'assets/launcher_icon/icon.png',
    }
    assert icons.yaml_section(PUBSPEC, 'dev_dependencies') == {
        'flutter_launcher_icons': '^0.14.3'}
    assert icons.yaml_section('name: x\n', 'flutter_launcher_icons') is None


def test_se_ofrecen_solo_las_apps_que_dicen_donde_va_su_icono(repo):
    assert [t.name for t in icons.icon_apps(repo)] == [
        'cliente', 'landing', 'mobile', 'panel', 'pwa', 'vite']


def test_cada_spa_toma_el_icono_donde_lo_declara(repo):
    def lugares(nombre):
        target = icons.targets.pick(repo, icons.ICON_KINDS, nombre)
        return [(p.path.relative_to(repo).as_posix(), p.layer, p.size)
                for p in icons.places(target)]
    assert lugares('panel') == [('panel/src/lib/assets/favicon.svg', 'logo', 0)]
    assert lugares('landing') == [('landing/static/favicon.svg', 'logo', 0)]
    assert lugares('vite') == [('vite/public/vite.svg', 'logo', 0)]
    # Un `src` relativo cuelga de la carpeta del manifest; uno absoluto, de `static/`.
    assert lugares('pwa') == [('pwa/static/icons/icon-192.png', 'logo', 192),
                              ('pwa/static/icons/icon-512.png', 'logo', 512),
                              ('pwa/static/icons/icon-512-maskable.png', 'maskable', 512),
                              ('pwa/static/apple.png', 'logo', 180)]


def test_la_capa_que_pide_la_app_se_exige_solo_si_la_pide(repo):
    with pytest.raises(MissingConfig) as error:
        icons.plan(repo, 'pwa', layers(repo, icons.LOGO))
    assert error.value.keys == ['BRAND_ICON_MASKABLE']
    with pytest.raises(MissingConfig) as error:
        icons.plan(repo, 'mobile', layers(repo, icons.LOGO))
    assert error.value.keys == ['BRAND_ICON_FOREGROUND']
    assert len(icons.plan(repo, 'panel', layers(repo, icons.LOGO)).writes) == 1


def test_flutter_toma_las_rutas_del_pubspec_una_vez_cada_una(repo):
    capas = layers(repo, icons.LOGO, icons.FOREGROUND)
    trabajo = icons.plan(repo, 'mobile', capas)
    assert trabajo.is_flutter
    assert trabajo.writes == (
        (capas[icons.LOGO], icons.Place(repo / 'mobile' / 'assets/launcher_icon/icon.png',
                                        icons.LOGO, 1024)),
        (capas[icons.FOREGROUND], icons.Place(
            repo / 'mobile' / 'assets/launcher_icon/icon_foreground.png', icons.FOREGROUND, 1024)),
    )


def test_flet_recibe_el_logo_en_su_icon_png(repo):
    trabajo = icons.plan(repo, 'cliente', layers(repo, icons.LOGO))
    assert [(p.path, p.size) for _, p in trabajo.writes] == [
        (repo / 'cliente' / icons.FLET_ICON, 1024)]


@pytest.mark.parametrize('nombre, pubspec, error', [
    ('sin_dep', PUBSPEC.replace('  flutter_launcher_icons: ^0.14.3', '  flutter_lints: ^5.0.0'),
     'falta flutter_launcher_icons en dev_dependencies'),
    ('monocromo', PUBSPEC.replace('  android: true\n',
                                  '  android: true\n  adaptive_icon_monochrome: "b.png"\n'),
     'adaptive_icon_monochrome'),
    ('sin_logo', ''.join(l for l in PUBSPEC.splitlines(keepends=True) if 'image_path' not in l),
     'no declara image_path'),
])
def test_lo_que_consola_no_sabe_llenar_en_flutter_corta(repo, nombre, pubspec, error):
    flutter(repo, nombre, pubspec)
    assert nombre in [t.name for t in icons.icon_apps(repo)]
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, nombre, layers(repo, icons.LOGO, icons.FOREGROUND))


@pytest.mark.parametrize('link, error', [
    ('<link rel="icon" href="/favicon.png" />', 'PNG sin sizes'),
    ('<link rel="apple-touch-icon" sizes="180x120" href="/t.png" />', 'no es cuadrado'),
    ('<link rel="icon" href="https://cdn.x/f.svg" />', 'apunta fuera de la app'),
    ('<link rel="icon" href="/favicon.gif" />', 'solo genera .svg, .png e .ico'),
])
def test_lo_que_consola_no_sabe_llenar_en_una_spa_corta(repo, link, error):
    spa(repo, 'rota', **{'src__app.html': link})
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, 'rota', layers(repo, icons.LOGO))


@pytest.mark.parametrize('vite, estaticos, error', [
    (VITE_PWA.replace('manifest: false', 'manifest: { icons: [] }'), {}, 'genera el manifest'),
    (VITE_PWA.replace(', manifest: false', ''), {}, 'genera el manifest'),
    (VITE_PWA, {}, 'no existe el manifest'),
    (VITE_PWA, {'static__manifest.webmanifest': '{"icons": ['}, 'no es JSON'),
    (VITE_PWA, {'static__manifest.webmanifest': manifest(
        {'src': 'i.png', 'sizes': '512x512', 'purpose': 'any maskable'})}, 'cada uno en su archivo'),
    (VITE_PWA, {'static__manifest.webmanifest': manifest({'sizes': '512x512'})}, 'no tiene src'),
])
def test_lo_que_consola_no_sabe_llenar_en_una_pwa_corta(repo, vite, estaticos, error):
    spa(repo, 'rota', vite=vite, **{'src__app.html': MANIFEST_LINK}, **estaticos)
    assert 'rota' in [t.name for t in icons.icon_apps(repo)]
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, 'rota', layers(repo, icons.LOGO, icons.MASKABLE))


def test_una_app_sin_declaracion_corta(repo):
    with pytest.raises(TaskError, match='no declara dónde va su ícono'):
        icons.plan(repo, 'externa', layers(repo, icons.LOGO))
    with pytest.raises(TaskError, match='no declara dónde va su ícono'):
        icons.plan(repo, 'suelta', layers(repo, icons.LOGO))


def test_el_logo_tiene_que_ser_un_svg_que_exista(repo):
    with pytest.raises(TaskError, match='tiene que ser un SVG'):
        icons.brand_file(repo, 'brand/logo.png', 'BRAND_ICON')
    with pytest.raises(TaskError, match='No existe BRAND_ICON'):
        icons.brand_file(repo, 'brand/otro.svg', 'BRAND_ICON')


def test_rasteriza_cuadrado_con_el_color_del_logo(repo):
    imagen = Image.open(io.BytesIO(raster.svg_to_png(repo / 'brand' / 'logomark.svg', 256)))
    imagen = imagen.convert('RGBA')
    assert imagen.size == (256, 256)
    assert imagen.getpixel((128, 128)) == (0x0b, 0x12, 0x24, 255)
    assert imagen.getpixel((0, 0))[3] == 0


def test_el_ico_lleva_todos_los_lados(repo):
    ico = Image.open(io.BytesIO(raster.svg_to_ico(repo / 'brand' / 'logomark.svg')))
    assert sorted(ico.info['sizes']) == [(n, n) for n in raster.ICO_SIZES]


def test_un_svg_que_no_es_cuadrado_corta(tmp_path):
    ancho = write(tmp_path / 'ancho.svg', LOGO.replace('viewBox="0 0 64 64"', 'viewBox="0 0 128 64"'))
    with pytest.raises(TaskError, match='no es cuadrado'):
        raster.svg_to_png(ancho, 256)


def test_la_corrida_escribe_solo_lo_que_cambia(repo):
    mensajes = []
    ctx = TaskContext('generate_icons', project=Project('repo', str(repo), ''),
                      config=Config({'BRAND_ICON': 'brand/logomark.svg',
                                     'BRAND_ICON_MASKABLE': 'brand/maskable.svg'}),
                      log_sink=lambda msg, nivel: mensajes.append(msg))
    images.generate_icons(ctx, ['panel', 'pwa'])
    assert (repo / 'panel' / 'src/lib/assets/favicon.svg').read_text(encoding='utf-8') == LOGO
    assert Image.open(repo / 'pwa' / 'static/icons/icon-192.png').size == (192, 192)
    assert '  actualizado: panel/src/lib/assets/favicon.svg' in mensajes
    assert '  nuevo: pwa/static/icons/icon-512.png' in mensajes
    images.generate_icons(ctx, ['panel'])
    assert mensajes[-2] == '  sin cambios: panel/src/lib/assets/favicon.svg'
