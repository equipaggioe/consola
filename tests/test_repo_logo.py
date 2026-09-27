"""El logo de un repo en la UI: su `BRAND_ICON`, o la marca de Equipaggio."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import repo_logo

LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect x="4" y="4" width="56" height="56" rx="16" fill="#0b1224"/></svg>')


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'brand').mkdir()
    (tmp_path / 'brand' / 'logomark.svg').write_text(LOGO, encoding='utf-8')
    return tmp_path


def _config(repo: Path, value: str) -> None:
    (repo / '.consola').mkdir(exist_ok=True)
    (repo / '.consola' / 'config.env').write_text(f'BRAND_ICON={value}\n', encoding='utf-8')


def test_el_logo_es_brand_icon(repo):
    _config(repo, 'brand/logomark.svg')
    assert repo_logo.resolve(str(repo)) == repo_logo.RepoLogo(repo / 'brand' / 'logomark.svg')


@pytest.mark.parametrize('config', [False, True])
def test_sin_logo_lleva_la_marca_de_equipaggio(repo, config):
    if config:
        _config(repo, '')
    assert repo_logo.resolve(str(repo)) == repo_logo.RepoLogo(repo_logo.EQUIPAGGIO)
    assert repo_logo.EQUIPAGGIO.is_file()


@pytest.mark.parametrize('value, error', [
    ('brand/otro.svg', 'No existe BRAND_ICON'),
    ('brand/logomark.png', 'BRAND_ICON tiene que ser un SVG'),
    ('brand/roto.svg', 'Qt no pudo leer roto.svg como SVG.'),
])
def test_un_logo_que_no_se_lee_muestra_el_error(repo, value, error):
    (repo / 'brand' / 'roto.svg').write_text('no es un svg', encoding='utf-8')
    _config(repo, value)
    logo = repo_logo.resolve(str(repo))
    assert logo.source is None
    assert error in logo.error


def test_el_logo_se_recorta_a_lo_que_se_dibuja(repo):
    # Como el de vettore: un cuadrado de 56 con 4 de margen en un lienzo de 64.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    imagen = repo_logo.trimmed(repo / 'brand' / 'logomark.svg')
    lado = repo_logo._RASTER * 56 / 64
    assert imagen.width() == pytest.approx(lado, abs=2)
    assert imagen.height() == pytest.approx(lado, abs=2)


def test_la_marca_de_equipaggio_se_recorta():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    # En el PNG de 400 el dibujo ocupa 292 de ancho y 378 de alto.
    imagen = repo_logo.trimmed(repo_logo.EQUIPAGGIO)
    assert imagen.width() == pytest.approx(repo_logo._RASTER * 292 / 400, abs=3)
    assert imagen.height() == pytest.approx(repo_logo._RASTER * 378 / 400, abs=3)
