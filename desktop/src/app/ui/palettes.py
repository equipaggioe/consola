"""One palette per repository.

A chosen hue and the whole ladder of backgrounds **truly** tinted by it.

A repo's color is not a loose accent on a gray canvas: it is the hue the
whole ladder of surfaces paints with, from the darkest (console) to the
lightest (input fields). The workspace reads at a glance, «the blue
repo», «the green repo», because the background is blue or green and not
a gray with a hint: saturation goes from 38 % to 55 % in HSL. It is
still a dark theme; what changes is that the hue shows.

Two signals, two tools, and they do not clash:

- **hue** says WHICH repo you are in. Only one, present in everything.
- **lightness** says WHICH PANEL you look at. The console and the
  section headers are the darkest step, the sections' bodies and the
  runs sub-bar one lighter. A hue per
  section would cancel the first signal: if «Parámetros» were always
  green, green would stop meaning «green repo».

**No background is black.** The darkest is `bg`, the canvas where one
reads; the section headers and the console's (`chrome`) are the most
saturated band. The title bar is painted in the accent, and what
rests on it, the brand and the repo tabs, carries no plate.

What does NOT come in here: `SUCCESS`, `WARNING`, `ERROR` and the LEDs.
A state has to mean the same in every repo; tinting them would make a
success and an error look alike in a green repo.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtGui import QColor

from app.theme import Colors, on_color, tint


def _luminance(c: QColor) -> float:
    """Return relative luminance (WCAG 2.1), like `on_color`."""

    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF())


def _tinted(base: str, accent: str, sat: float) -> str:
    """Return the background: the accent's hue at that saturation.

    The base neutral's lightness stays untouched.

    Two pieces, each with its job. **Saturation** is absolute, not a
    fraction of the accent's: so green (a barely saturated accent) and
    blue (a very saturated one) tint equally strongly, and no repo stays
    gray for having a dull accent. **Luminance** is the neutral's, so
    tinting moves no step: the contrast of everything on top is the same
    in all eight themes.

    Plainly mixing toward the accent (interpolating RGB) does not work:
    accents are light, so the mix lightens the background and text
    contrast falls, with `TEXT_MUTED` over a header going from 3.4:1 to
    2.5:1.

    What is kept is WCAG **luminance**, not HSL's «L»: to the eye and to
    the contrast formula, a green and a violet with the same L do not
    weigh the same (green weighs almost double). Fixing L, green went
    over on contrast and violet flattened the steps. It looks for the L
    that gives back the base gray's luminance: monotonic in L, so a
    bisection finds it.
    """
    target = _luminance(QColor(base))
    hue = QColor(accent).hueF()
    lo, hi = 0.0, 1.0
    for _ in range(24):
        middle = (lo + hi) / 2
        if _luminance(QColor.fromHslF(hue, sat, middle)) < target:
            lo = middle
        else:
            hi = middle
    return QColor.fromHslF(hue, sat, (lo + hi) / 2).name()


# Which neutral each role comes from and how saturated it paints. They
# are colored backgrounds, not hinted grays: below 35 % the hue stops
# reading at screen size and everything looks gray again. The headers
# are the most saturated: they are the band that says at a glance which
# repo this is.
_RECIPE: tuple[tuple[str, str, float], ...] = (
    ("chrome", Colors.CHROME, 0.50),
    ("bg", Colors.BG, 0.38),
    ("panel", Colors.PANEL, 0.42),
    ("surface", Colors.SURFACE, 0.45),
    ("surface_hover", Colors.SURFACE_HOVER, 0.45),
    ("surface_alt", Colors.SURFACE_ALT, 0.45),
    ("border", Colors.BORDER, 0.40),
    ("border_light", Colors.BORDER_LIGHT, 0.38),
)

# Text is NOT tinted: it stays in the grays of `theme.py` in all eight
# themes. It has to read the same over any of them, and a gray shifted
# toward its background's hue moves closer to it instead of standing
# out.


@dataclass(frozen=True)
class Palette:
    """The backgrounds of ONE repo.

    Immutable: changing theme is another palette.
    """

    key: str
    label: str
    accent: str
    chrome: str  # section headers and the console's
    bg: str  # console, left canvas and section headers: the darkest
    panel: str  # sections' bodies, runs sub-bar, menus and dialogs
    surface: str  # sub-bar, section headers, footer, status bar
    surface_hover: str
    surface_alt: str  # fields, combos, chips
    border: str
    border_light: str

    @property
    def on_accent(self) -> str:
        """Return legible text over the accent.

        By luminance and not theme.
        """
        return on_color(self.accent)

    def glow(self, alpha: float = 0.18) -> str:
        """Return the accent as a translucent glow."""
        return tint(self.accent, alpha)


def build(key: str, label: str, accent: str) -> Palette:
    """Return the palette derived from an accent."""
    return Palette(
        key=key,
        label=label,
        accent=accent,
        **{role: _tinted(base, accent, saturation) for role, base, saturation in _RECIPE},
    )


# Eight light hues, in order around the color wheel starting with blue.
# Light on purpose: the accent goes ON TOP of the backgrounds (title
# bar, logo's diamond, stripes, link text) and has to stand out. The hue
# comes from it; `_RECIPE` sets how strongly each background tints, not
# the accent's saturation. `tests/test_palettes.py` checks each one's
# contrast.
THEMES: dict[str, Palette] = {
    p.key: p
    for p in (
        build("blue", "Azul", "#58a6ff"),
        build("indigo", "Índigo", "#8fa0f0"),
        build("violet", "Violeta", "#bc8cff"),
        build("pink", "Rosa", "#dd8fb4"),
        build("coral", "Coral", "#e0907f"),
        build("amber", "Ámbar", "#d4ae6a"),
        build("green", "Verde", "#7cc48a"),
        build("cyan", "Cian", "#6dbecb"),
    )
}

# With no repo open there is nobody to take the hue from: the bare
# neutrals.
NEUTRAL = Palette(
    key="",
    label="",
    accent=Colors.ACCENT,
    chrome=Colors.CHROME,
    bg=Colors.BG,
    panel=Colors.PANEL,
    surface=Colors.SURFACE,
    surface_hover=Colors.SURFACE_HOVER,
    surface_alt=Colors.SURFACE_ALT,
    border=Colors.BORDER,
    border_light=Colors.BORDER_LIGHT,
)


def get(key: str) -> Palette:
    """Return that theme's palette, raising if it does not exist.

    On purpose: a repo saved with a theme that is gone is discarded on
    load (`ui/project_store.py`), and no other color is invented here.
    """
    return THEMES[key]


def first_free(used: Iterable[str]) -> str:
    """Return the first theme no open repo uses.

    Deterministic and without repeats while themes remain: two repos of
    the same color get confused, which is what color exists to avoid.
    With more repos than themes it starts over from the first; by then
    no color is enough and one chooses by hand.
    """
    in_use = set(used)
    return next((k for k in THEMES if k not in in_use), next(iter(THEMES)))
