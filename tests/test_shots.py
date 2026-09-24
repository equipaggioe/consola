"""El contrato con la camara del repo y el revelado para la landing.

Se arma un repo falso con dos apps (una SPA y una Flutter) para que
`targets.by_kinds` las encuentre como en un repo real.
"""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import shots
from core.errors import TaskError


@pytest.fixture
def repo(tmp_path):
    panel = tmp_path / 'panel'
    panel.mkdir()
    (panel / 'package.json').write_text('{}', encoding='utf-8')
    (panel / 'vite.config.ts').write_text('', encoding='utf-8')
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'pubspec.yaml').write_text('name: app\n', encoding='utf-8')
    return tmp_path


def png(path: Path, width: int, height: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (width, height), (20, 40, 80)).save(path)
    return path


def test_los_argumentos_llevan_la_seleccion_y_el_dispositivo_solo_si_hay():
    salida = Path('/repo/demo/capturas')
    assert shots.camera_args(['panel', 'app'], ['oscuro'], ['es', 'en'], salida) == [
        '--apps', 'panel,app', '--themes', 'oscuro', '--languages', 'es,en',
        '--output', str(salida)]
    assert shots.camera_args(['app'], ['claro'], ['es'], salida, 'emulator-5554')[-2:] == [
        '--device', 'emulator-5554']


def test_una_carpeta_relativa_cuelga_del_repo_y_una_absoluta_va_tal_cual(tmp_path):
    assert shots.resolve_dir(tmp_path, 'demo/capturas') == tmp_path / 'demo' / 'capturas'
    assert shots.resolve_dir(tmp_path, str(tmp_path / 'x')) == tmp_path / 'x'


def test_lee_los_crudos_con_su_tipo_de_app(repo):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 10, 10)
    png(raw / 'app' / 'chats.claro.en.png', 10, 10)
    leidos = {(s.app, s.kind, s.screen, s.theme, s.language) for s in shots.collect(repo, raw)}
    assert leidos == {('panel', 'spa-vite', 'chat', 'oscuro', 'es'),
                      ('app', 'flutter-app', 'chats', 'claro', 'en')}


@pytest.mark.parametrize('nombre', ['chat.png', 'chat.oscuro.png', 'chat.oscuro.es.webp',
                                    'chat.sepia.es.png'])
def test_un_nombre_que_no_sigue_el_contrato_corta(repo, nombre):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 10, 10)
    (raw / 'panel' / nombre).write_bytes(b'')
    with pytest.raises(TaskError):
        shots.collect(repo, raw)


def test_una_carpeta_que_no_es_una_app_del_repo_corta(repo):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'servidor' / 'chat.oscuro.es.png', 10, 10)
    with pytest.raises(TaskError, match='no corresponde'):
        shots.collect(repo, raw)


def test_dice_que_combinaciones_quedaron_sin_captura(repo):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 10, 10)
    sacadas = shots.collect(repo, raw, ['panel'])
    assert shots.missing_combinations(sacadas, ['panel'], ['oscuro', 'claro'], ['es']) == [
        'panel · claro · es']


def test_borrar_la_corrida_anterior_solo_toca_lo_que_se_va_a_volver_a_sacar(repo):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 10, 10)
    queda = png(raw / 'panel' / 'chat.oscuro.en.png', 10, 10)
    assert shots.clear_raw(raw, ['panel'], ['oscuro'], ['es']) == 1
    assert [p.name for p in (raw / 'panel').iterdir()] == [queda.name]


def test_la_landing_achica_al_tope_de_su_tipo_y_nunca_agranda(repo, tmp_path):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 2880, 1800)
    png(raw / 'app' / 'chats.oscuro.es.png', 400, 800)
    preset = shots.load_presets()['landing']
    salida = tmp_path / 'publicado'
    hechos = {s.app: shots.render_landing(s, preset, salida) for s in shots.collect(repo, raw)}

    assert hechos['panel'] == salida / 'panel' / 'chat.oscuro.es.webp'
    with Image.open(hechos['panel']) as imagen:
        assert (imagen.format, imagen.size) == ('WEBP', (1920, 1200))
    with Image.open(hechos['app']) as imagen:
        assert imagen.size == (400, 800)
