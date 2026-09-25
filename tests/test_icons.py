"""Los iconos que salen del logo del repo.

Se arma un repo falso con las formas que hay en los repos reales: una SPA con
el favicon de la plantilla, una que toma su icono de otro lado, y una app
Flutter con su seccion `flutter_launcher_icons:`.
"""
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
from core.tasks import images

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


def spa(root: Path, name: str, favicon: bool) -> Path:
    carpeta = root / name
    carpeta.mkdir()
    (carpeta / 'package.json').write_text('{}', encoding='utf-8')
    (carpeta / 'vite.config.ts').write_text('', encoding='utf-8')
    if favicon:
        destino = carpeta / icons.SPA_FAVICON
        destino.parent.mkdir(parents=True)
        destino.write_text('<svg>svelte</svg>', encoding='utf-8')
    return carpeta


def flutter(root: Path, name: str, pubspec: str) -> Path:
    carpeta = root / name
    carpeta.mkdir()
    (carpeta / 'pubspec.yaml').write_text(pubspec, encoding='utf-8')
    return carpeta


@pytest.fixture
def repo(tmp_path):
    spa(tmp_path, 'panel', favicon=True)
    spa(tmp_path, 'landing', favicon=False)
    flutter(tmp_path, 'mobile', PUBSPEC)
    flutter(tmp_path, 'suelta', 'name: suelta\n')
    marca = tmp_path / 'brand'
    marca.mkdir()
    (marca / 'logomark.svg').write_text(LOGO, encoding='utf-8')
    (marca / 'foreground.svg').write_text(LOGO, encoding='utf-8')
    return tmp_path


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
    assert [t.name for t in icons.icon_apps(repo)] == ['mobile', 'panel']


def test_la_spa_recibe_el_logo_en_su_favicon(repo):
    logo = repo / 'brand' / 'logomark.svg'
    trabajo = icons.plan(repo, 'panel', logo, None)
    assert trabajo.writes == ((logo, repo / 'panel' / icons.SPA_FAVICON),)


def test_flutter_toma_las_rutas_del_pubspec_una_vez_cada_una(repo):
    logo, frente = repo / 'brand' / 'logomark.svg', repo / 'brand' / 'foreground.svg'
    trabajo = icons.plan(repo, 'mobile', logo, frente)
    assert trabajo.is_flutter
    assert trabajo.writes == (
        (logo, repo / 'mobile' / 'assets/launcher_icon/icon.png'),
        (frente, repo / 'mobile' / 'assets/launcher_icon/icon_foreground.png'),
    )


def test_la_capa_frontal_se_exige_solo_si_el_pubspec_la_pide(repo):
    with pytest.raises(MissingConfig) as error:
        icons.plan(repo, 'mobile', repo / 'brand' / 'logomark.svg', None)
    assert error.value.keys == ['BRAND_ICON_FOREGROUND']
    sin_frente = PUBSPEC.replace('  adaptive_icon_foreground: "assets/launcher_icon/icon_foreground.png"\n', '')
    flutter(repo, 'otra', sin_frente)
    assert len(icons.plan(repo, 'otra', repo / 'brand' / 'logomark.svg', None).writes) == 1


@pytest.mark.parametrize('nombre, pubspec, error', [
    ('suelta', None, 'no tiene sección flutter_launcher_icons'),
    ('sin_dep', PUBSPEC.replace('  flutter_launcher_icons: ^0.14.3', '  flutter_lints: ^5.0.0'),
     'falta flutter_launcher_icons en dev_dependencies'),
    ('monocromo', PUBSPEC.replace('  android: true\n',
                                  '  android: true\n  adaptive_icon_monochrome: "b.png"\n'),
     'adaptive_icon_monochrome'),
    ('sin_logo', ''.join(l for l in PUBSPEC.splitlines(keepends=True) if 'image_path' not in l),
     'no declara image_path'),
])
def test_lo_que_consola_no_sabe_llenar_corta(repo, nombre, pubspec, error):
    if pubspec is not None:
        flutter(repo, nombre, pubspec)
    with pytest.raises(TaskError, match=error):
        icons.plan(repo, nombre, repo / 'brand' / 'logomark.svg', repo / 'brand' / 'foreground.svg')


def test_una_spa_sin_favicon_corta(repo):
    with pytest.raises(TaskError, match='toma su ícono de otro lado'):
        icons.plan(repo, 'landing', repo / 'brand' / 'logomark.svg', None)


def test_el_logo_tiene_que_ser_un_svg_que_exista(repo):
    with pytest.raises(TaskError, match='tiene que ser un SVG'):
        icons.brand_file(repo, 'brand/logo.png', 'BRAND_ICON')
    with pytest.raises(TaskError, match='No existe BRAND_ICON'):
        icons.brand_file(repo, 'brand/otro.svg', 'BRAND_ICON')


def test_rasteriza_cuadrado_con_el_color_del_logo(repo, tmp_path):
    salida = tmp_path / 'icon.png'
    salida.write_bytes(images._rasterize(repo / 'brand' / 'logomark.svg', 256))
    imagen = Image.open(salida).convert('RGBA')
    assert imagen.size == (256, 256)
    assert imagen.getpixel((128, 128)) == (0x0b, 0x12, 0x24, 255)
    assert imagen.getpixel((0, 0))[3] == 0


def test_un_svg_que_no_es_cuadrado_corta(tmp_path):
    ancho = tmp_path / 'ancho.svg'
    ancho.write_text(LOGO.replace('viewBox="0 0 64 64"', 'viewBox="0 0 128 64"'), encoding='utf-8')
    with pytest.raises(TaskError, match='no es cuadrado'):
        images._rasterize(ancho, 256)


def test_la_corrida_escribe_solo_lo_que_cambia(repo):
    mensajes = []
    ctx = TaskContext('generate_icons', project=Project('repo', str(repo), '', ''),
                      config=Config({'BRAND_ICON': 'brand/logomark.svg'}),
                      log_sink=lambda msg, nivel: mensajes.append(msg))
    images.generate_icons(ctx, ['panel'])
    assert (repo / 'panel' / icons.SPA_FAVICON).read_text(encoding='utf-8') == LOGO
    assert '  actualizado: panel/src/lib/assets/favicon.svg' in mensajes
    images.generate_icons(ctx, ['panel'])
    assert mensajes[-2] == '  sin cambios: panel/src/lib/assets/favicon.svg'
