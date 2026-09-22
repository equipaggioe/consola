from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtGui import QColor

from ui.theme import Colors, on_color, tint

"""
Una paleta por repositorio: un tono elegido y toda la escalera de fondos
derivada de el.

El color de un repo no es un acento suelto sobre un lienzo gris: es el tono
con el que se tiñe la escalera entera de superficies, de la mas oscura
(consola) a la mas clara (campos de entrada). Asi el espacio de trabajo se
reconoce de un vistazo —«el repo azul», «el repo verde»— sin saturar nada: la
mezcla mas alta es del 22 %, y el fondo sigue siendo oscuro.

Dos señales, dos herramientas, y no se pisan:

- **el tono** dice en QUE repo estas. Uno solo, presente en todo.
- **la luminosidad** dice QUE PANEL miras. La consola es el escalon mas
  oscuro, el cuerpo de las secciones uno mas claro, las cabeceras otro mas.
  Un tono por seccion anularia la primera señal: si «Parametros» fuera siempre
  verde, el verde dejaria de querer decir «repo verde».

Lo que NO entra aca: `SUCCESS`, `WARNING`, `ERROR` y los LED. Un estado tiene
que significar lo mismo en todos los repos; teñirlos haria que en un repo
verde un exito y un error se parecieran.
"""


def _luminance(c: QColor) -> float:
    """Luminancia relativa (WCAG 2.1). La misma cuenta que hace `on_color`."""
    def lin(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return (0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF())
            + 0.0722 * lin(c.blueF()))


def _tinted(base: str, accent: str, amount: float) -> str:
    """El neutro teñido del tono del repo, **con su misma luminosidad**.

    Toma el tono del acento, una fraccion de su saturacion, y la luminosidad
    de la base sin tocar. Es lo que mantiene separadas las dos señales: el
    color dice de que repo es, la luminosidad dice que panel es, y teñir no
    mueve ningun escalon de sitio.

    Mezclar hacia el acento a secas (interpolar RGB) no servia: los acentos
    son claros, asi que la mezcla aclaraba el fondo y el contraste del texto
    caia — `TEXT_MUTED` sobre una cabecera pasaba de 3.4:1 a 2.5:1.

    Lo que se conserva es la **luminancia** de WCAG, no la «L» de HSL: al ojo
    y a la formula de contraste, un verde y un violeta con la misma L no
    pesan lo mismo (el verde pesa casi el doble). Fijando la L, el verde se
    iba de contraste por arriba y el violeta aplanaba los escalones por
    abajo. Se busca la L que devuelve la luminancia del gris de partida:
    monotona en L, asi que una biseccion la encuentra.
    """
    b, a = QColor(base), QColor(accent)
    objetivo = _luminance(b)
    tono, sat = a.hueF(), min(1.0, a.saturationF() * amount)
    lo, hi = 0.0, 1.0
    for _ in range(24):
        medio = (lo + hi) / 2
        if _luminance(QColor.fromHslF(tono, sat, medio)) < objetivo:
            lo = medio
        else:
            hi = medio
    return QColor.fromHslF(tono, sat, (lo + hi) / 2).name()


# De que neutro sale cada rol y que fraccion de la saturacion del acento
# lleva. Sube con la elevacion: el fondo donde se lee texto casi no se tiñe y
# lo de arriba se tiñe mas, que es como se ve profundidad sin aclarar nada.
_RECIPE: tuple[tuple[str, str, float], ...] = (
    ('chrome',        Colors.CHROME,        0.22),
    ('bg',            Colors.BG,            0.26),
    ('panel',         Colors.PANEL,         0.34),
    ('surface',       Colors.SURFACE,       0.40),
    ('surface_hover', Colors.SURFACE_HOVER, 0.42),
    ('surface_alt',   Colors.SURFACE_ALT,   0.40),
    ('border',        Colors.BORDER,        0.48),
    ('border_light',  Colors.BORDER_LIGHT,  0.48),
)

# El texto NO se tiñe: se queda en los grises de `ui/theme.py` en los ocho
# temas. Tiene que seguir leyendose igual sobre cualquiera de ellos, y un gris
# corrido hacia el mismo tono que su fondo se le acerca en vez de despegarse.


@dataclass(frozen=True)
class Palette:
    """Los fondos de UN repo. Inmutable: cambiar de tema es otra paleta."""
    key: str
    label: str
    accent: str
    chrome: str         # fila de la barra de menu
    bg: str             # consola y lienzo izquierdo: el escalon mas oscuro
    panel: str          # cuerpo de las secciones de la columna derecha
    surface: str        # sub-barra, cabeceras de seccion, pie, barra de estado
    surface_hover: str
    surface_alt: str    # campos, combos, chips
    border: str
    border_light: str

    @property
    def on_accent(self) -> str:
        """Texto legible sobre el acento: lo decide la luminancia, no el tema."""
        return on_color(self.accent)

    def glow(self, alpha: float = 0.18) -> str:
        return tint(self.accent, alpha)


def build(key: str, label: str, accent: str) -> Palette:
    return Palette(key=key, label=label, accent=accent,
                   **{rol: _tinted(base, accent, cantidad)
                      for rol, base, cantidad in _RECIPE})


# Ocho tonos bien separados en el circulo cromatico, todos claros sobre fondo
# oscuro (`tests/test_palettes.py` comprueba el contraste de cada uno).
THEMES: dict[str, Palette] = {p.key: p for p in (
    build('azul',    'Azul',    '#58a6ff'),
    build('cian',    'Cian',    '#39c5cf'),
    build('verde',   'Verde',   '#3fb950'),
    build('lima',    'Lima',    '#9ede4b'),
    build('ambar',   'Ámbar',   '#d29922'),
    build('coral',   'Coral',   '#f47067'),
    build('rosa',    'Rosa',    '#ff7eb6'),
    build('violeta', 'Violeta', '#bc8cff'),
)}

# Sin ningun repo abierto no hay de quien tomar el tono: los neutros pelados.
NEUTRAL = Palette(key='', label='', accent=Colors.ACCENT,
                  chrome=Colors.CHROME, bg=Colors.BG, panel=Colors.PANEL,
                  surface=Colors.SURFACE, surface_hover=Colors.SURFACE_HOVER,
                  surface_alt=Colors.SURFACE_ALT, border=Colors.BORDER,
                  border_light=Colors.BORDER_LIGHT)


def get(key: str) -> Palette:
    """La paleta de ese tema. Revienta si no existe, a proposito: un repo
    guardado con un tema que ya no esta se descarta al cargar
    (`ui/project_store.py`), no se le inventa otro color aca."""
    return THEMES[key]


def first_free(used: Iterable[str]) -> str:
    """El primer tema que ningun repo abierto este usando.

    Deterministico y sin repetir mientras queden temas: dos repos del mismo
    color son dos repos que se confunden, que es justo lo que el color viene a
    evitar. Con mas repos que temas vuelve a empezar por el primero — ahi ya
    no hay color que alcance y se elige a mano.
    """
    en_uso = set(used)
    return next((k for k in THEMES if k not in en_uso), next(iter(THEMES)))
