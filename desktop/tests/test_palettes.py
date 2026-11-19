"""Contrast of the per-repository palettes.

Tinting backgrounds with eight hues moves the contrast of everything on
top, and warm hues move it the most. This checks it with numbers and not
by eye: if a recipe in `services/palettes.py` changes, it fails here
before the screen.

Thresholds are WCAG 2.1's: 4.5:1 for text, 3:1 for large text and
interface elements. Elevation steps ask for much less, 1.09:1, because
they separate one panel from another and not text from background; in
dark themes, two backgrounds that differ easily are that far apart
(VSCode's sidebar and editor are 1.1 apart).
"""

import pytest
from PySide6.QtGui import QColor

from app import theme
from app.services import palettes
from app.services.palettes import Palette
from app.theme import Colors

THEMES = list(palettes.THEMES.values())
IDS = [p.key for p in THEMES]


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)

    def lin(channel: int) -> float:
        v = channel / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def contrast(a: str, b: str) -> float:
    """Return the WCAG contrast between two colors."""
    la, lb = _luminance(a), _luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("background", ["bg", "panel", "surface", "surface_alt"])
def test_main_text_is_legible(pal: Palette, background: str) -> None:
    """Main text is legible."""
    assert contrast(Colors.TEXT, getattr(pal, background)) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("background", ["bg", "panel", "surface"])
def test_secondary_text_is_legible(pal: Palette, background: str) -> None:
    """`TEXT_DIM` is labels and section summaries: running text.

    Text is not tinted but the background is, so it has to be checked
    theme by theme.
    """
    assert contrast(Colors.TEXT_DIM, getattr(pal, background)) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("background", ["bg", "panel", "surface", "surface_alt"])
def test_field_labels_are_legible(pal: Palette, background: str) -> None:
    """`TEXT_LABEL` is the labels of the fields.

    Of Parameters and repo settings, and of the «solo favoritos» switch.
    It is the lightest gray after running text: a label has to be read,
    not guessed.
    """
    assert contrast(Colors.TEXT_LABEL, getattr(pal, background)) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize("background", ["bg", "panel", "surface"])
def test_muted_text_is_legible(pal: Palette, background: str) -> None:
    """`TEXT_MUTED` is hints and paths: large text threshold."""
    assert contrast(Colors.TEXT_MUTED, getattr(pal, background)) >= 3.0


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_the_accent_is_legible_over_the_backgrounds(pal: Palette) -> None:
    """The accent is used as text and icon (diamond, star, stripes)."""
    for background in (pal.bg, pal.panel, pal.surface):
        assert contrast(pal.accent, background) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_text_over_the_accent(pal: Palette) -> None:
    """The title bar paints in the accent (`widgets/title_bar.py`)."""
    assert contrast(pal.on_accent, pal.accent) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_borders_show_on_their_background(pal: Palette) -> None:
    """Borders show on their background."""
    assert contrast(pal.border, pal.surface) >= 1.5
    assert contrast(pal.border, pal.panel) >= 1.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize(
    ("below", "above"), [("bg", "panel"), ("panel", "surface"), ("surface", "surface_alt")]
)
def test_the_steps_differ(pal: Palette, below: str, above: str) -> None:
    """The separation between panels is this jump.

    If it flattens, the right column is one stain again. `chrome` is not
    on the list: the menu row separates from the canvas with a border,
    not luminance.

    The floor is 1.09 and not the base gray's 1.106 because the final
    hex has 8 bits per channel: rounding the hue moves the step a
    thousandth.
    """
    assert contrast(getattr(pal, above), getattr(pal, below)) >= 1.09


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize(
    "role", ["chrome", "bg", "panel", "surface", "surface_hover", "surface_alt"]
)
def test_tinting_does_not_move_the_step(pal: Palette, role: str) -> None:
    """Tinting changes hue, not depth.

    Each background keeps the luminance of its neutral base. That
    guarantees the contrast of everything on top is the same in all
    eight themes.
    """
    base = {
        "chrome": Colors.CHROME,
        "bg": Colors.BG,
        "panel": Colors.PANEL,
        "surface": Colors.SURFACE,
        "surface_hover": Colors.SURFACE_HOVER,
        "surface_alt": Colors.SURFACE_ALT,
    }[role]
    assert _luminance(getattr(pal, role)) == pytest.approx(_luminance(base), abs=0.001)


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_backgrounds_stay_dark(pal: Palette) -> None:
    """The dark theme is the starting point.

    Not something to negotiate hue by hue: no background may go light.
    """
    assert _luminance(pal.surface_alt) < 0.08


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize(
    "role", ["chrome", "bg", "panel", "surface", "surface_hover", "surface_alt"]
)
def test_backgrounds_carry_real_color(pal: Palette, role: str) -> None:
    """A background has to read as the repo's color, not as gray.

    Below 35 % HSL saturation the hue gets lost at screen size and the
    window looks gray again. The floor is 0.35 and not the recipe's
    nominal saturation because the final hex has 8 bits per channel:
    rounding a very dark background eats a few hundredths.
    """
    assert QColor(getattr(pal, role)).saturationF() >= 0.35


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_the_menu_bar_is_not_black(pal: Palette) -> None:
    """The menu row's band is light, not dark.

    Above the sections' body and headers (`theme.py`).
    """
    bar = theme.MENU_BAR.on(pal).bg
    assert _luminance(bar) > _luminance(theme.SECTION_HEADER.on(pal).bg)


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_the_selected_tab_reads(pal: Palette) -> None:
    """The selected repo's tab paints in the menu row's band.

    The color of the row just below, with the name in the accent
    (`theme.py`, `widgets/project_tab_bar.py`). 4.5 and not the parts'
    3:1: the name is running text.
    """
    tab = theme.REPO_TAB_SELECTED.on(pal)
    assert contrast(tab.fg, tab.bg) >= 4.5


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
def test_the_tabs_read_on_the_bar(pal: Palette) -> None:
    """All repo tabs have the active repo's accent as background.

    The color of the title bar, and the name, outline and `◇ CONSOLA`
    mark go on top in `on_accent` (`widgets/project_tab_bar.py`,
    `widgets/title_bar.py`).
    """
    assert contrast(pal.on_accent, pal.accent) >= 4.5


def test_states_are_not_tinted() -> None:
    """A success and an error mean the same in every repo.

    No semantic color comes from a palette.
    """
    fields = set(palettes.Palette.__dataclass_fields__)
    assert {"success", "warning", "error"}.isdisjoint(fields)


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


PARTS = {name: look for name, look in vars(theme).items() if isinstance(look, theme.Look)}


@pytest.mark.parametrize("pal", [*THEMES, palettes.NEUTRAL], ids=[*IDS, "neutral"])
@pytest.mark.parametrize("name", PARTS)
def test_each_part_resolves(pal: Palette, name: str) -> None:
    """Every slot a part declares gives a color in every theme."""
    paint = PARTS[name].on(pal)
    for slot in PARTS[name].slots():
        assert QColor(getattr(paint, slot)).isValid()


@pytest.mark.parametrize("pal", THEMES, ids=IDS)
@pytest.mark.parametrize(
    "name", [n for n, look in PARTS.items() if look.bg and look.fg and n != "RUN_BUTTON_OFF"]
)
def test_the_text_of_each_part_reads(pal: Palette, name: str) -> None:
    """A part's text reads over its own background (`theme.py`).

    3:1, WCAG's floor for interface elements: changing a role in the
    table can drop a part below it, and it has to show here. Ejecutar
    off is left out: WCAG asks no contrast of a disabled control, and
    its muted text is what says it is off.
    """
    paint = PARTS[name].on(pal)
    assert contrast(paint.fg, paint.bg) >= 3.0


def test_a_slot_not_declared_raises() -> None:
    """Asking for a slot the part does not paint fails."""
    with pytest.raises(LookupError):
        _ = theme.CANVAS.on(palettes.NEUTRAL).fg
