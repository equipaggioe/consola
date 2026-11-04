"""El contrato con la camara del repo y el revelado para la landing.

Se arma un repo falso con dos apps (una SPA y una Flutter) para que
`targets.by_kinds` las encuentre como en un repo real.
"""

from pathlib import Path

import pytest
from PIL import Image

from app.core import shots
from app.core.errors import TaskError
from app.core.shots import Shot


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    panel = tmp_path / "panel"
    panel.mkdir()
    (panel / "package.json").write_text("{}", encoding="utf-8")
    (panel / "vite.config.ts").write_text("", encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir()
    (app / "pubspec.yaml").write_text("name: app\n", encoding="utf-8")
    return tmp_path


def png(path: Path, width: int, height: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (20, 40, 80)).save(path)
    return path


def test_los_argumentos_llevan_la_seleccion_y_el_dispositivo_solo_si_hay() -> None:
    output = Path("/repo/demo/capturas")
    assert shots.camera_args(["panel", "app"], ["oscuro"], ["es", "en"], output) == [
        "--apps",
        "panel,app",
        "--themes",
        "oscuro",
        "--languages",
        "es,en",
        "--output",
        str(output),
        "--kit",
        str(shots.KIT),
    ]
    assert shots.KIT.is_file()
    assert shots.camera_args(["app"], ["claro"], ["es"], output, "emulator-5554")[-2:] == [
        "--device",
        "emulator-5554",
    ]


def test_los_ejes_salen_de_lo_que_la_camara_dice_que_captura() -> None:
    declared = shots.parse_supported(
        '{"panel": {"themes": ["oscuro"], "languages": ["es"]},'
        ' "app": {"themes": ["oscuro", "claro"], "languages": ["es", "en"], "mobile": true}}'
    )
    assert shots.supported_values(declared, "apps") == ["panel", "app"]
    assert shots.supported_values(declared, "themes") == ["claro", "oscuro"]
    assert shots.supported_values(declared, "languages") == ["es", "en"]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("listo", "no contestó JSON"),
        ("{}", "ninguna app"),
        ('{"panel": {"themes": ["oscuro"]}}', "panel sin temas o sin idiomas"),
        ('{"panel": {"themes": ["sepia"], "languages": ["es"]}}', "fuera del contrato: sepia"),
    ],
)
def test_lo_que_declara_la_camara_se_revisa(text: str, error: str) -> None:
    with pytest.raises(TaskError, match=error):
        shots.parse_supported(text)


def test_una_carpeta_relativa_cuelga_del_repo_y_una_absoluta_va_tal_cual(tmp_path: Path) -> None:
    assert shots.resolve_dir(tmp_path, "demo/capturas") == tmp_path / "demo" / "capturas"
    assert shots.resolve_dir(tmp_path, str(tmp_path / "x")) == tmp_path / "x"


def test_lee_los_crudos_con_su_tipo_de_app(repo: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    png(raw / "app" / "chats.claro.en.png", 10, 10)
    read = {(s.app, s.kind, s.screen, s.theme, s.language) for s in shots.collect(repo, raw)}
    assert read == {
        ("panel", "spa-vite", "chat", "oscuro", "es"),
        ("app", "flutter-app", "chats", "claro", "en"),
    }


@pytest.mark.parametrize(
    "name", ["chat.png", "chat.oscuro.png", "chat.oscuro.es.webp", "chat.sepia.es.png"]
)
def test_un_nombre_que_no_sigue_el_contrato_corta(repo: Path, name: str) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    (raw / "panel" / name).write_bytes(b"")
    with pytest.raises(TaskError):
        shots.collect(repo, raw)


def test_una_carpeta_que_no_es_una_app_del_repo_corta(repo: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "servidor" / "chat.oscuro.es.png", 10, 10)
    with pytest.raises(TaskError, match="no corresponde"):
        shots.collect(repo, raw)


def test_dice_que_combinaciones_quedaron_sin_captura(repo: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    taken = shots.collect(repo, raw, ["panel"])
    assert shots.missing_combinations(taken, ["panel"], ["oscuro", "claro"], ["es"]) == [
        "panel · claro · es"
    ]


def test_borrar_la_corrida_anterior_solo_toca_lo_que_se_va_a_volver_a_sacar(repo: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    remains = png(raw / "panel" / "chat.oscuro.en.png", 10, 10)
    assert shots.clear_raw(raw, ["panel"], ["oscuro"], ["es"]) == 1
    assert [p.name for p in (raw / "panel").iterdir()] == [remains.name]


def test_la_landing_achica_al_tope_de_su_tipo_y_nunca_agranda(repo: Path, tmp_path: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 2880, 1800)
    png(raw / "app" / "chats.oscuro.es.png", 400, 800)
    preset = shots.load_presets()["landing"]
    output = tmp_path / "publicado"
    done = {s.app: shots.render_landing(s, preset, output).path for s in shots.collect(repo, raw)}

    assert done["panel"] == output / "panel" / "chat.oscuro.es.webp"
    with Image.open(done["panel"]) as image:
        assert (image.format, image.size) == ("WEBP", (1920, 1200))
    with Image.open(done["app"]) as image:
        assert image.size == (400, 800)


def taken(repo: Path, phone: tuple[int, int] = (1080, 2400)) -> list[Shot]:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 2880, 1800)
    png(raw / "app" / "chats.claro.es.png", *phone)
    return shots.collect(repo, raw)


def test_play_no_acepta_un_telefono_mas_largo_que_dos_a_uno(repo: Path) -> None:
    with pytest.raises(TaskError, match="2.22:1 pasa de 2:1"):
        shots.plan("Google Play", shots.load_presets()["play"], taken(repo))


def test_play_deja_el_crudo_en_su_medida_y_sin_alfa(repo: Path, tmp_path: Path) -> None:
    raws = taken(repo, phone=(1080, 1920))
    phone = next(s for s in raws if s.app == "app")
    Image.new("RGBA", (1080, 1920), (1, 2, 3, 255)).save(phone.path)
    pairs = shots.plan("Google Play", shots.load_presets()["play"], raws)
    assert [(s.app, m) for s, m in pairs] == [("app", None)]
    done = shots.render_sized(*pairs[0], tmp_path, "play")
    assert done.path == tmp_path / "es" / "app" / "chats.claro.png"
    with Image.open(done.path) as image:
        assert (image.mode, image.size) == ("RGB", (1080, 1920))


def test_app_store_manda_el_telefono_a_iphone_y_la_tablet_a_ipad(
    repo: Path, tmp_path: Path
) -> None:
    preset = shots.load_presets()["appstore"]
    phone = shots.plan("App Store", preset, taken(repo))
    assert [m and m["name"] for _, m in phone] == ["iphone"]
    done = shots.render_sized(*phone[0], tmp_path, "appstore")
    with Image.open(done.path) as image:
        assert image.size == (1290, 2796)
    tablet = shots.plan("App Store", preset, taken(repo, phone=(1600, 2134)))
    assert [m and m["name"] for _, m in tablet] == ["ipad"]


def test_app_store_corta_si_hay_que_recortar_de_mas(repo: Path) -> None:
    with pytest.raises(TaskError, match="no llega a"):
        shots.plan("App Store", shots.load_presets()["appstore"], taken(repo, (1080, 1920)))


def test_open_graph_solo_de_escritorio_y_redes_recortan_lo_que_haga_falta(repo: Path) -> None:
    raws = taken(repo)
    presets = shots.load_presets()
    assert {s.app for s, _ in shots.plan("og", presets["og"], raws)} == {"panel"}
    assert sorted(
        (s.app, m and m["name"]) for s, m in shots.plan("social", presets["social"], raws)
    ) == [("app", "square"), ("app", "story"), ("panel", "square")]


def test_un_destino_sin_crudos_de_su_tipo_corta(repo: Path) -> None:
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 2880, 1800)
    with pytest.raises(TaskError, match="ninguna captura"):
        shots.plan("Google Play", shots.load_presets()["play"], shots.collect(repo, raw))


def test_el_manual_deja_el_png_a_resolucion_nativa(repo: Path, tmp_path: Path) -> None:
    pairs = shots.plan("Manual", shots.load_presets()["manual"], taken(repo))
    assert all(m is None for _, m in pairs)
    done = shots.render_sized(pairs[0][0], None, tmp_path, "manual")
    assert done.path == tmp_path / "es" / "app" / "chats.claro.png"
    assert (done.width, done.height) == (1080, 2400)


def test_el_press_kit_guarda_los_crudos_sin_comprimir(repo: Path, tmp_path: Path) -> None:
    import zipfile

    derived = shots.render_archive(taken(repo), tmp_path, "presskit")
    with zipfile.ZipFile(tmp_path / "capturas.zip") as zip_:
        assert sorted(zip_.namelist()) == ["app/chats.claro.es.png", "panel/chat.oscuro.es.png"]
        assert {i.compress_type for i in zip_.infolist()} == {zipfile.ZIP_STORED}
    assert {d.archive for d in derived} == {"app/chats.claro.es.png", "panel/chat.oscuro.es.png"}


def test_el_manifiesto_es_estable_y_dice_que_cambio_desde_la_corrida_anterior(
    repo: Path, tmp_path: Path
) -> None:
    import json

    preset = shots.load_presets()["landing"]
    raws = taken(repo)
    derived = [shots.render_landing(s, preset, tmp_path) for s in raws]
    first = shots.write_manifest(tmp_path, "landing", derived)
    assert first.added == ["app/chats.claro.es.webp", "panel/chat.oscuro.es.webp"]
    text = (tmp_path / shots.MANIFEST).read_text(encoding="utf-8")

    same = shots.write_manifest(tmp_path, "landing", list(reversed(derived)))
    assert (same.changed, same.added, same.removed) == ([], [], [])
    assert (tmp_path / shots.MANIFEST).read_text(encoding="utf-8") == text

    panel = next(s for s in raws if s.app == "panel")
    Image.new("RGB", (2880, 1800), (200, 0, 0)).save(panel.path)  # misma medida, otra pantalla
    other = [shots.render_landing(panel, preset, tmp_path)]
    changes = shots.write_manifest(tmp_path, "landing", other)
    assert (changes.changed, changes.removed) == (
        ["panel/chat.oscuro.es.webp"],
        ["app/chats.claro.es.webp"],
    )
    assert (
        json.loads((tmp_path / shots.MANIFEST).read_text(encoding="utf-8"))["items"][0]["file"]
        == "panel/chat.oscuro.es.webp"
    )
