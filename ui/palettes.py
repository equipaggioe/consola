from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtGui import QColor

from ui.theme import Colors, on_color, tint

"""
Una paleta por repositorio: un tono elegido y toda la escalera de fondos
teñida de el **de verdad**.

El color de un repo no es un acento suelto sobre un lienzo gris: es el tono
con el que se pinta la escalera entera de superficies, de la mas oscura
(consola) a la mas clara (campos de entrada). El espacio de trabajo se
reconoce de un vistazo —«el repo azul», «el repo verde»— porque el fondo es
azul o verde, no un gris con una insinuacion: la saturacion va del 38 % al
55 % en HSL. Sigue siendo un tema oscuro; lo que cambia es que el tono se ve.

Dos señales, dos herramientas, y no se pisan:

- **el tono** dice en QUE repo estas. Uno solo, presente en todo.
- **la luminosidad** dice QUE PANEL miras. La consola es el escalon mas
  oscuro, el cuerpo de las secciones uno mas claro, las cabeceras otro mas.
  Un tono por seccion anularia la primera señal: si «Parametros» fuera siempre
  verde, el verde dejaria de querer decir «repo verde».

Hay **un solo fondo casi negro**, `brand`: la placa del logo y la de las
pestañas de repo inactivas, ambas sobre la barra de titulo pintada del acento.
La fila de la barra de menu (`chrome`) no es negra — es la banda mas clara de
la escalera de fondos, y la mas saturada de todas.

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


def _tinted(base: str, accent: str, sat: float) -> str:
    """El fondo del repo: el tono del acento a esa saturacion, con la
    luminosidad del neutro de partida sin tocar.

    Dos piezas, cada una con su trabajo. La **saturacion** es absoluta, no una
    fraccion de la del acento: asi el verde (acento poco saturado) y el azul
    (acento saturadisimo) tiñen igual de fuerte, y ningun repo queda gris
    porque le toco un acento apagado. La **luminancia** es la del neutro, y
    por eso teñir no mueve ningun escalon de sitio: el contraste de todo lo
    que va encima es el mismo en los ocho temas.

    Mezclar hacia el acento a secas (interpolar RGB) no sirve: los acentos son
    claros, asi que la mezcla aclara el fondo y el contraste del texto cae —
    `TEXT_MUTED` sobre una cabecera pasaba de 3.4:1 a 2.5:1.

    Lo que se conserva es la **luminancia** de WCAG, no la «L» de HSL: al ojo
    y a la formula de contraste, un verde y un violeta con la misma L no
    pesan lo mismo (el verde pesa casi el doble). Fijando la L, el verde se
    iba de contraste por arriba y el violeta aplanaba los escalones por
    abajo. Se busca la L que devuelve la luminancia del gris de partida:
    monotona en L, asi que una biseccion la encuentra.
    """
    objetivo = _luminance(QColor(base))
    tono = QColor(accent).hueF()
    lo, hi = 0.0, 1.0
    for _ in range(24):
        medio = (lo + hi) / 2
        if _luminance(QColor.fromHslF(tono, sat, medio)) < objetivo:
            lo = medio
        else:
            hi = medio
    return QColor.fromHslF(tono, sat, (lo + hi) / 2).name()


# De que neutro sale cada rol y con cuanta saturacion se pinta. Son fondos de
# color, no grises insinuados: por debajo del 35 % el tono deja de leerse a
# tamaño de pantalla y todo vuelve a parecer gris. Las dos franjas que van
# sobre la barra de titulo —la placa del logo y la fila del menu— son las mas
# saturadas, porque son las que dicen de un vistazo en que repo estas.
_RECIPE: tuple[tuple[str, str, float], ...] = (
    ('brand',         Colors.BRAND,         0.55),
    ('chrome',        Colors.CHROME,        0.50),
    ('bg',            Colors.BG,            0.38),
    ('panel',         Colors.PANEL,         0.42),
    ('surface',       Colors.SURFACE,       0.45),
    ('surface_hover', Colors.SURFACE_HOVER, 0.45),
    ('surface_alt',   Colors.SURFACE_ALT,   0.45),
    ('border',        Colors.BORDER,        0.40),
    ('border_light',  Colors.BORDER_LIGHT,  0.38),
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
    brand: str          # placa del logo y de las pestanas inactivas: el unico casi negro
    chrome: str         # fila de la barra de menu: la banda mas clara y mas saturada
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
                   **{rol: _tinted(base, accent, saturacion)
                      for rol, base, saturacion in _RECIPE})


# Ocho tonos claros, en orden por el circulo cromatico y empezando por el azul.
# Claros a proposito: el acento es lo que va ENCIMA de los fondos —la barra de
# titulo, el rombo del logo, los filetes, el texto de enlace— y tiene que
# despegarse de ellos. De el sale el tono; la fuerza con la que se tiñe cada
# fondo la pone `_RECIPE`, no la saturacion del acento. El contraste de cada
# uno lo comprueba `tests/test_palettes.py`.
THEMES: dict[str, Palette] = {p.key: p for p in (
    build('azul',    'Azul',    '#58a6ff'),
    build('indigo',  'Índigo',  '#8fa0f0'),
    build('violeta', 'Violeta', '#bc8cff'),
    build('rosa',    'Rosa',    '#dd8fb4'),
    build('coral',   'Coral',   '#e0907f'),
    build('ambar',   'Ámbar',   '#d4ae6a'),
    build('verde',   'Verde',   '#7cc48a'),
    build('cian',    'Cian',    '#6dbecb'),
)}

# Sin ningun repo abierto no hay de quien tomar el tono: los neutros pelados.
NEUTRAL = Palette(key='', label='', accent=Colors.ACCENT,
                  brand=Colors.BRAND, chrome=Colors.CHROME,
                  bg=Colors.BG, panel=Colors.PANEL,
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
