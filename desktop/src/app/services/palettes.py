"""The color theme of each repository.

A repo chooses one of the color themes of `brand/tokens/`, generated in
`colors.py`, and its whole workspace paints with it (ADR-0092). The hue
says which repo you are in; it shows in the accent, in the band of the
section headers (`primary_container`) and in that of the menu row
(`secondary_container`). The surfaces, the text and the states are the
same in every theme: a success and an error have to mean the same in
every repo.

The theme without a repo, the initial one of `brand/tokens/`, is not
chosen: it paints the window while no repo is open.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.colors import INITIAL, ColorTheme
from app.services.language import QT_TRANSLATE_NOOP
from app.theme import tint


@dataclass(frozen=True)
class Palette:
    """The colors of ONE repo: the dark scheme of its theme.

    Immutable: changing theme is another palette.
    """

    key: str
    label: str
    colors: dict[str, str]

    @property
    def accent(self) -> str:
        """Return the color of the repo."""
        return self.colors["primary"]

    def glow(self, alpha: float = 0.18) -> str:
        """Return the accent as a translucent glow."""
        return tint(self.accent, alpha)


# The themes a repo chooses from, in order around the color wheel
# starting with blue.
_LABELS = {
    ColorTheme.BLUE: QT_TRANSLATE_NOOP("palettes", "Azul"),
    ColorTheme.INDIGO: QT_TRANSLATE_NOOP("palettes", "Índigo"),
    ColorTheme.VIOLET: QT_TRANSLATE_NOOP("palettes", "Violeta"),
    ColorTheme.PINK: QT_TRANSLATE_NOOP("palettes", "Rosa"),
    ColorTheme.CORAL: QT_TRANSLATE_NOOP("palettes", "Coral"),
    ColorTheme.AMBER: QT_TRANSLATE_NOOP("palettes", "Ámbar"),
    ColorTheme.GREEN: QT_TRANSLATE_NOOP("palettes", "Verde"),
    ColorTheme.CYAN: QT_TRANSLATE_NOOP("palettes", "Cian"),
}

THEMES: dict[str, Palette] = {
    theme.name.lower(): Palette(theme.name.lower(), label, theme.dark)
    for theme, label in _LABELS.items()
}

# With no repo open there is nobody to take the hue from.
NEUTRAL = Palette(key="", label="", colors=INITIAL.dark)


def get(key: str) -> Palette:
    """Return that theme's palette, raising if it does not exist.

    On purpose: a repo saved with a theme that is gone is discarded on
    load (`services/project_store.py`), and no other color is invented
    here.
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
