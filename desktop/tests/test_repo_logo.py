"""A repo's logo in the UI: its `BRAND_ICON`, or the Equipaggio mark."""

from pathlib import Path

import pytest

from app.services import repo_logo

LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
    '<rect x="4" y="4" width="56" height="56" rx="16" fill="#0b1224"/></svg>'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Return a repo with a logo."""
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "logomark.svg").write_text(LOGO, encoding="utf-8")
    return tmp_path


def _config(repo: Path, value: str) -> None:
    (repo / ".consola").mkdir(exist_ok=True)
    (repo / ".consola" / "config.env").write_text(f"BRAND_ICON={value}\n", encoding="utf-8")


def test_the_logo_is_brand_icon(repo: Path) -> None:
    """The logo is `BRAND_ICON`."""
    _config(repo, "brand/logomark.svg")
    assert repo_logo.resolve(str(repo)) == repo_logo.RepoLogo(repo / "brand" / "logomark.svg")


@pytest.mark.parametrize("config", [False, True])
def test_without_a_logo_it_carries_the_equipaggio_mark(repo: Path, config: bool) -> None:
    """Without a logo it carries the Equipaggio mark."""
    if config:
        _config(repo, "")
    assert repo_logo.resolve(str(repo)) == repo_logo.RepoLogo(repo_logo.EQUIPAGGIO)
    assert repo_logo.EQUIPAGGIO.is_file()


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ("brand/otro.svg", "No existe BRAND_ICON"),
        ("brand/logomark.png", "BRAND_ICON tiene que ser un SVG"),
        ("brand/roto.svg", "Qt no pudo leer roto.svg como SVG."),
    ],
)
def test_an_unreadable_logo_shows_the_error(repo: Path, value: str, error: str) -> None:
    """An unreadable logo shows the error."""
    (repo / "brand" / "roto.svg").write_text("no es un svg", encoding="utf-8")
    _config(repo, value)
    logo = repo_logo.resolve(str(repo))
    assert logo.source is None
    assert error in logo.error


def test_the_logo_is_cropped_to_what_is_drawn(repo: Path) -> None:
    # A 56-unit square with a margin of 4 on a canvas of 64.
    """The logo is cropped to what is drawn."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    image = repo_logo.trimmed(repo / "brand" / "logomark.svg")
    side = repo_logo._RASTER * 56 / 64
    assert image.width() == pytest.approx(side, abs=2)
    assert image.height() == pytest.approx(side, abs=2)


def test_the_equipaggio_mark_is_cropped() -> None:
    """The Equipaggio mark is cropped."""
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    # In the 400 PNG the drawing takes 292 wide and 378 high.
    image = repo_logo.trimmed(repo_logo.EQUIPAGGIO)
    assert image.width() == pytest.approx(repo_logo._RASTER * 292 / 400, abs=3)
    assert image.height() == pytest.approx(repo_logo._RASTER * 378 / 400, abs=3)
