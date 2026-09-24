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
        '--output', str(salida), '--kit', str(shots.KIT)]
    assert shots.KIT.is_file()
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
    hechos = {s.app: shots.render_landing(s, preset, salida).path
              for s in shots.collect(repo, raw)}

    assert hechos['panel'] == salida / 'panel' / 'chat.oscuro.es.webp'
    with Image.open(hechos['panel']) as imagen:
        assert (imagen.format, imagen.size) == ('WEBP', (1920, 1200))
    with Image.open(hechos['app']) as imagen:
        assert imagen.size == (400, 800)



def sacadas(repo, telefono=(1080, 2400)):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 2880, 1800)
    png(raw / 'app' / 'chats.claro.es.png', *telefono)
    return shots.collect(repo, raw)


def test_play_no_acepta_un_telefono_mas_largo_que_dos_a_uno(repo):
    with pytest.raises(TaskError, match='2.22:1 pasa de 2:1'):
        shots.plan('Google Play', shots.load_presets()['play'], sacadas(repo))


def test_play_deja_el_crudo_en_su_medida_y_sin_alfa(repo, tmp_path):
    crudos = sacadas(repo, telefono=(1080, 1920))
    telefono = next(s for s in crudos if s.app == 'app')
    Image.new('RGBA', (1080, 1920), (1, 2, 3, 255)).save(telefono.path)
    pares = shots.plan('Google Play', shots.load_presets()['play'], crudos)
    assert [(s.app, m) for s, m in pares] == [('app', None)]
    hecho = shots.render_sized(*pares[0], tmp_path, 'play')
    assert hecho.path == tmp_path / 'es' / 'app' / 'chats.claro.png'
    with Image.open(hecho.path) as imagen:
        assert (imagen.mode, imagen.size) == ('RGB', (1080, 1920))


def test_app_store_manda_el_telefono_a_iphone_y_la_tablet_a_ipad(repo, tmp_path):
    preset = shots.load_presets()['appstore']
    telefono = shots.plan('App Store', preset, sacadas(repo))
    assert [m['name'] for _, m in telefono] == ['iphone']
    hecho = shots.render_sized(*telefono[0], tmp_path, 'appstore')
    with Image.open(hecho.path) as imagen:
        assert imagen.size == (1290, 2796)
    tablet = shots.plan('App Store', preset, sacadas(repo, telefono=(1600, 2134)))
    assert [m['name'] for _, m in tablet] == ['ipad']


def test_app_store_corta_si_hay_que_recortar_de_mas(repo):
    with pytest.raises(TaskError, match='no llega a'):
        shots.plan('App Store', shots.load_presets()['appstore'], sacadas(repo, (1080, 1920)))


def test_open_graph_solo_de_escritorio_y_redes_recortan_lo_que_haga_falta(repo):
    crudos = sacadas(repo)
    presets = shots.load_presets()
    assert {s.app for s, _ in shots.plan('og', presets['og'], crudos)} == {'panel'}
    assert sorted((s.app, m['name']) for s, m in shots.plan('social', presets['social'], crudos)) == [
        ('app', 'square'), ('app', 'story'), ('panel', 'square')]


def test_un_destino_sin_crudos_de_su_tipo_corta(repo):
    raw = repo / 'demo' / 'capturas'
    png(raw / 'panel' / 'chat.oscuro.es.png', 2880, 1800)
    with pytest.raises(TaskError, match='ninguna captura'):
        shots.plan('Google Play', shots.load_presets()['play'], shots.collect(repo, raw))


def test_el_manual_deja_el_png_a_resolucion_nativa(repo, tmp_path):
    pares = shots.plan('Manual', shots.load_presets()['manual'], sacadas(repo))
    assert all(m is None for _, m in pares)
    hecho = shots.render_sized(pares[0][0], None, tmp_path, 'manual')
    assert hecho.path == tmp_path / 'es' / 'app' / 'chats.claro.png'
    assert (hecho.width, hecho.height) == (1080, 2400)


def test_el_press_kit_guarda_los_crudos_sin_comprimir(repo, tmp_path):
    import zipfile
    derivados = shots.render_archive(sacadas(repo), tmp_path, 'presskit')
    with zipfile.ZipFile(tmp_path / 'capturas.zip') as zip_:
        assert sorted(zip_.namelist()) == ['app/chats.claro.es.png', 'panel/chat.oscuro.es.png']
        assert {i.compress_type for i in zip_.infolist()} == {zipfile.ZIP_STORED}
    assert {d.archive for d in derivados} == {'app/chats.claro.es.png', 'panel/chat.oscuro.es.png'}


def test_el_manifiesto_es_estable_y_dice_que_cambio_desde_la_corrida_anterior(repo, tmp_path):
    import json
    preset = shots.load_presets()['landing']
    crudos = sacadas(repo)
    derivados = [shots.render_landing(s, preset, tmp_path) for s in crudos]
    primera = shots.write_manifest(tmp_path, 'landing', derivados)
    assert primera.added == ['app/chats.claro.es.webp', 'panel/chat.oscuro.es.webp']
    texto = (tmp_path / shots.MANIFEST).read_text(encoding='utf-8')

    igual = shots.write_manifest(tmp_path, 'landing', list(reversed(derivados)))
    assert (igual.changed, igual.added, igual.removed) == ([], [], [])
    assert (tmp_path / shots.MANIFEST).read_text(encoding='utf-8') == texto

    panel = next(s for s in crudos if s.app == 'panel')
    Image.new('RGB', (2880, 1800), (200, 0, 0)).save(panel.path)  # misma medida, otra pantalla
    otra = [shots.render_landing(panel, preset, tmp_path)]
    cambios = shots.write_manifest(tmp_path, 'landing', otra)
    assert (cambios.changed, cambios.removed) == (['panel/chat.oscuro.es.webp'],
                                                  ['app/chats.claro.es.webp'])
    assert json.loads((tmp_path / shots.MANIFEST).read_text(encoding='utf-8'))['items'][0][
        'file'] == 'panel/chat.oscuro.es.webp'
