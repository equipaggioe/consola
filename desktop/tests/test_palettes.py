"""The color theme of each repository and the parts of `theme.py`.

`scripts/tokens.py --check` holds the contrast of each role in every
theme. This checks what is Consola's: that a theme changes only the
hue, that the hue shows, and that each part reads in every theme.
"""

import pytest
from PySide6.QtGui import QColor

from app import theme
from app.colors import INITIAL, ColorTheme
from app.services import palettes
from app.services.palettes import Palette

THEMES = list(palettes.THEMES.values())
IDS = [p.key for p in THEMES]

# The roles that take the hue of the theme.
TINTED = {
    "primary",
    "primary_container",
    "primary_fixed",
    "primary_fixed_dim",
    "inverse_primary",
    "secondary",
    "secondary_container",
    "secondary_fixed",
    "secondary_fixed_dim",
    "surface_tint",
}


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)

    def lin(channel: int) -> float:
        v = channel / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def contrast(a: str, b: str) -> float:
    """Return the WCAG contrast between two colors."""
    la, lb = _luminance(a), _luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


def test_every_theme_but_the_initial_is_chosen() -> None:
    """A repo chooses from every theme in `brand/tokens/` but one.

    The initial one paints the window while no repo is open.
    """
    chosen = {pal.key for pal in THEMES}
    assert chosen == {t.name.lower() for t in ColorTheme if t is not INITIAL}


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_only_the_hue_changes(pal: Palette) -> None:
    """The surfaces, the text and the states are the same in every repo.

    A success and an error have to mean the same in a green repo as in
    a red one.
    """
    fixed = {role for role in pal.colors if role not in TINTED}
    assert {r: pal.colors[r] for r in fixed} == {r: palettes.NEUTRAL.colors[r] for r in fixed}


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("role", ["primary_container", "secondary_container"])
def test_tinting_does_not_move_the_step(pal: Palette, role: str) -> None:
    """A band keeps the luminance of the theme without a repo.

    The color says which repo it is, and the lightness which panel.
    """
    expected = _luminance(palettes.NEUTRAL.colors[role])
    assert _luminance(pal.colors[role]) == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("role", ["primary_container", "secondary_container"])
def test_bands_carry_real_color(pal: Palette, role: str) -> None:
    """A band has to read as the repo's color, not as gray.

    Below 35 % HSL saturation the hue gets lost at screen size.
    """
    assert QColor(pal.colors[role]).saturationF() >= 0.35


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_the_menu_bar_is_not_black(pal: Palette) -> None:
    """The menu row's band is lighter than the section headers."""
    bar = theme.MENU_BAR.on(pal).bg
    assert _luminance(bar) > _luminance(theme.SECTION_HEADER.on(pal).bg)


def test_each_theme_has_its_key() -> None:
    """Each theme has its key."""
    assert all(key == pal.key for key, pal in palettes.THEMES.items())


def test_it_does_not_repeat_while_themes_remain() -> None:
    """It does not repeat while themes remain."""
    used: list[str] = []
    for _ in palettes.THEMES:
        key = palettes.first_free(used)
        assert key not in used
        used.append(key)
    # With all eight used, it returns to the first instead of having no
    # answer.
    assert palettes.first_free(used) == next(iter(palettes.THEMES))


def test_each_role_is_in_the_scheme() -> None:
    """Every `Role` names a role of `colors.py`."""
    assert {role.value for role in theme.Role} <= set(INITIAL.dark)


PARTS = {name: look for name, look in vars(theme).items() if isinstance(look, theme.Look)}


@pytest.mark.parametrize("pal", [*THEMES, palettes.NEUTRAL], ids=[*IDS, "neutral"])
@pytest.mark.parametrize("name", PARTS)
def test_each_part_resolves(pal: Palette, name: str) -> None:
    """Every slot a part declares gives a color in every theme."""
    paint = PARTS[name].on(pal)
    for slot in PARTS[name].slots():
        assert QColor(getattr(paint, slot)).isValid()


@pytest.mark.parametrize("pal", [*THEMES, palettes.NEUTRAL], ids=[*IDS, "neutral"])
@pytest.mark.parametrize(
    "name", [n for n, look in PARTS.items() if look.bg and look.fg and n != "RUN_BUTTON_OFF"]
)
def test_the_text_of_each_part_reads(pal: Palette, name: str) -> None:
    """A part's text reads over its own background (`theme.py`).

    4.5:1, as `transversal.md` asks of all text. Ejecutar off is left
    out: WCAG asks no contrast of a disabled control, and its faint
    text is what says it is off.
    """
    paint = PARTS[name].on(pal)
    assert contrast(paint.fg, paint.bg) >= 4.5


def test_a_slot_not_declared_raises() -> None:
    """Asking for a slot the part does not paint fails."""
    with pytest.raises(LookupError):
        _ = theme.CANVAS.on(palettes.NEUTRAL).fg


def test_a_layer_blends_its_roles() -> None:
    """A layer lays its role on the other at its opacity."""
    assert theme.blend("#ffffff", "#000000", 0.5) == "#808080"
