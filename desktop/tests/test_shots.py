"""The contract with the repo's camera.

And the development for the landing.

It builds a fake repo with two apps, an SPA and a Flutter one, so
`targets.by_kinds` finds them as in a real repo.
"""

from pathlib import Path

import pytest
from PIL import Image

from app.core import shots
from app.core.errors import TaskError
from app.core.shots import Shot


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a repo with two apps."""
    panel = tmp_path / "panel"
    panel.mkdir()
    (panel / "package.json").write_text("{}", encoding="utf-8")
    (panel / "vite.config.ts").write_text("", encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir()
    (app / "pubspec.yaml").write_text("name: app\n", encoding="utf-8")
    return tmp_path


def png(path: Path, width: int, height: int) -> Path:
    """Write a PNG of that size."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), (20, 40, 80)).save(path)
    return path


def test_the_arguments_carry_the_selection_and_the_device_only_if_any() -> None:
    """The arguments carry the selection, and the device only if any."""
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


def test_the_axes_come_from_what_the_camera_says_it_captures() -> None:
    """The axes come from what the camera says it captures."""
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
def test_what_the_camera_declares_is_checked(text: str, error: str) -> None:
    """What the camera declares is checked."""
    with pytest.raises(TaskError, match=error):
        shots.parse_supported(text)


def test_a_relative_folder_hangs_from_the_repo_and_an_absolute_one_stays(tmp_path: Path) -> None:
    """A relative folder hangs from the repo; an absolute one stays."""
    assert shots.resolve_dir(tmp_path, "demo/capturas") == tmp_path / "demo" / "capturas"
    assert shots.resolve_dir(tmp_path, str(tmp_path / "x")) == tmp_path / "x"


def test_it_reads_the_raw_shots_with_their_app_type(repo: Path) -> None:
    """It reads the raw shots with their app type."""
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
def test_a_name_outside_the_contract_stops(repo: Path, name: str) -> None:
    """A name outside the contract stops."""
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    (raw / "panel" / name).write_bytes(b"")
    with pytest.raises(TaskError):
        shots.collect(repo, raw)


def test_a_folder_that_is_not_an_app_of_the_repo_stops(repo: Path) -> None:
    """A folder that is not an app of the repo stops."""
    raw = repo / "demo" / "capturas"
    png(raw / "servidor" / "chat.oscuro.es.png", 10, 10)
    with pytest.raises(TaskError, match="no corresponde"):
        shots.collect(repo, raw)


def test_it_says_which_combinations_have_no_shot(repo: Path) -> None:
    """It says which combinations have no shot."""
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    taken = shots.collect(repo, raw, ["panel"])
    assert shots.missing_combinations(taken, ["panel"], ["oscuro", "claro"], ["es"]) == [
        "panel · claro · es"
    ]


def test_deleting_the_previous_run_only_touches_what_will_be_taken_again(repo: Path) -> None:
    """Deleting the previous run touches only what is taken again."""
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 10, 10)
    remains = png(raw / "panel" / "chat.oscuro.en.png", 10, 10)
    assert shots.clear_raw(raw, ["panel"], ["oscuro"], ["es"]) == 1
    assert [p.name for p in (raw / "panel").iterdir()] == [remains.name]


def test_the_landing_shrinks_to_its_type_cap_and_never_grows(repo: Path, tmp_path: Path) -> None:
    """The landing shrinks to its type's cap and never grows."""
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
    """Return raw shots taken with that phone size."""
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 2880, 1800)
    png(raw / "app" / "chats.claro.es.png", *phone)
    return shots.collect(repo, raw)


def test_play_rejects_a_phone_longer_than_two_to_one(repo: Path) -> None:
    """Play rejects a phone longer than two to one."""
    with pytest.raises(TaskError, match="2.22:1 pasa de 2:1"):
        shots.plan("Google Play", shots.load_presets()["play"], taken(repo))


def test_play_leaves_the_raw_shot_at_its_size_and_without_alpha(
    repo: Path, tmp_path: Path
) -> None:
    """Play leaves the raw shot at its size and without alpha."""
    raws = taken(repo, phone=(1080, 1920))
    phone = next(s for s in raws if s.app == "app")
    Image.new("RGBA", (1080, 1920), (1, 2, 3, 255)).save(phone.path)
    pairs = shots.plan("Google Play", shots.load_presets()["play"], raws)
    assert [(s.app, m) for s, m in pairs] == [("app", None)]
    done = shots.render_sized(*pairs[0], tmp_path, "play")
    assert done.path == tmp_path / "es" / "app" / "chats.claro.png"
    with Image.open(done.path) as image:
        assert (image.mode, image.size) == ("RGB", (1080, 1920))


def test_app_store_sends_the_phone_to_iphone_and_the_tablet_to_ipad(
    repo: Path, tmp_path: Path
) -> None:
    """App Store sends the phone to iPhone and the tablet to iPad."""
    preset = shots.load_presets()["appstore"]
    phone = shots.plan("App Store", preset, taken(repo))
    assert [m and m["name"] for _, m in phone] == ["iphone"]
    done = shots.render_sized(*phone[0], tmp_path, "appstore")
    with Image.open(done.path) as image:
        assert image.size == (1290, 2796)
    tablet = shots.plan("App Store", preset, taken(repo, phone=(1600, 2134)))
    assert [m and m["name"] for _, m in tablet] == ["ipad"]


def test_app_store_stops_if_it_has_to_crop_too_much(repo: Path) -> None:
    """App Store stops if it has to crop too much."""
    with pytest.raises(TaskError, match="no llega a"):
        shots.plan("App Store", shots.load_presets()["appstore"], taken(repo, (1080, 1920)))


def test_open_graph_only_takes_desktop_and_social_crops_what_it_must(repo: Path) -> None:
    """Open Graph only takes desktop, and social crops what it must."""
    raws = taken(repo)
    presets = shots.load_presets()
    assert {s.app for s, _ in shots.plan("og", presets["og"], raws)} == {"panel"}
    assert sorted(
        (s.app, m and m["name"]) for s, m in shots.plan("social", presets["social"], raws)
    ) == [("app", "square"), ("app", "story"), ("panel", "square")]


def test_a_destination_without_raw_shots_of_its_type_stops(repo: Path) -> None:
    """A destination without raw shots of its type stops."""
    raw = repo / "demo" / "capturas"
    png(raw / "panel" / "chat.oscuro.es.png", 2880, 1800)
    with pytest.raises(TaskError, match="ninguna captura"):
        shots.plan("Google Play", shots.load_presets()["play"], shots.collect(repo, raw))


def test_the_manual_leaves_the_png_at_native_resolution(repo: Path, tmp_path: Path) -> None:
    """The manual leaves the PNG at native resolution."""
    pairs = shots.plan("Manual", shots.load_presets()["manual"], taken(repo))
    assert all(m is None for _, m in pairs)
    done = shots.render_sized(pairs[0][0], None, tmp_path, "manual")
    assert done.path == tmp_path / "es" / "app" / "chats.claro.png"
    assert (done.width, done.height) == (1080, 2400)


def test_the_press_kit_keeps_the_raw_shots_uncompressed(repo: Path, tmp_path: Path) -> None:
    """The press kit keeps the raw shots uncompressed."""
    import zipfile

    derived = shots.render_archive(taken(repo), tmp_path, "presskit")
    with zipfile.ZipFile(tmp_path / "capturas.zip") as zip_:
        assert sorted(zip_.namelist()) == ["app/chats.claro.es.png", "panel/chat.oscuro.es.png"]
        assert {i.compress_type for i in zip_.infolist()} == {zipfile.ZIP_STORED}
    assert {d.archive for d in derived} == {"app/chats.claro.es.png", "panel/chat.oscuro.es.png"}


def test_the_manifest_is_stable_and_says_what_changed_since_the_last_run(
    repo: Path, tmp_path: Path
) -> None:
    """The manifest is stable and says what changed since last run."""
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
    # same size, another screen
    Image.new("RGB", (2880, 1800), (200, 0, 0)).save(panel.path)
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
