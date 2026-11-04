"""Contraste de las paletas por repositorio.

Teñir los fondos con ocho tonos distintos mueve el contraste de todo lo que va
encima, y los tonos calidos (ambar, coral, lima) son los que mas lo mueven.
Esto lo comprueba con numeros en vez de a ojo: si una receta de
`ui/palettes.py` se toca, falla aca antes que en la pantalla.

Los umbrales son los de WCAG 2.1: 4.5:1 para texto, 3:1 para texto grande y
elementos de interfaz. Los escalones de elevacion piden mucho menos —1.09:1—
porque no separan texto de fondo sino un panel de otro; en oscuro, dos fondos
que se distinguen sin esfuerzo estan a esa distancia (el salto entre la barra
lateral y el editor de VSCode vale 1.1).
"""

import pytest
from PySide6.QtGui import QColor

from app.theme import Colors
from app.ui import palettes
from app.ui.palettes import Palette

TEMAS = list(palettes.THEMES.values())
IDS = [p.key for p in TEMAS]


def _luminancia(hex_color: str) -> float:
    c = QColor(hex_color)

    def lin(channel: int) -> float:
        v = channel / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def contraste(a: str, b: str) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, oscuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (oscuro + 0.05)


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize("fondo", ["bg", "panel", "surface", "surface_alt"])
def test_texto_principal_legible(pal: Palette, fondo: str) -> None:
    assert contraste(Colors.TEXT, getattr(pal, fondo)) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize("fondo", ["bg", "panel", "surface"])
def test_texto_secundario_legible(pal: Palette, fondo: str) -> None:
    """`TEXT_DIM` son rotulos y resumenes de seccion: texto corrido. El texto
    no se tiñe, pero el fondo si, y hay que comprobarlo tema por tema.
    """
    assert contraste(Colors.TEXT_DIM, getattr(pal, fondo)) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize("fondo", ["bg", "panel", "surface", "surface_alt"])
def test_rotulos_de_campo_legibles(pal: Palette, fondo: str) -> None:
    """`TEXT_LABEL` son los rotulos de los campos de Parametros y de la
    configuracion del repo, y el del interruptor «solo favoritos». Es el gris
    mas claro despues del texto corrido: un rotulo hay que poder leerlo de
    corrido, no adivinarlo.
    """
    assert contraste(Colors.TEXT_LABEL, getattr(pal, fondo)) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize("fondo", ["bg", "panel", "surface"])
def test_texto_apagado_legible(pal: Palette, fondo: str) -> None:
    """`TEXT_MUTED` son pistas cortas y rutas: umbral de texto grande."""
    assert contraste(Colors.TEXT_MUTED, getattr(pal, fondo)) >= 3.0


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_acento_legible_sobre_los_fondos(pal: Palette) -> None:
    """El acento se usa como texto e icono (rombo, estrella, filetes)."""
    for fondo in (pal.bg, pal.panel, pal.surface):
        assert contraste(pal.accent, fondo) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_texto_sobre_el_acento(pal: Palette) -> None:
    """La barra de titulo se pinta entera del acento (`ui/title_bar.py`)."""
    assert contraste(pal.on_accent, pal.accent) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_bordes_se_ven_sobre_su_fondo(pal: Palette) -> None:
    assert contraste(pal.border, pal.surface) >= 1.5
    assert contraste(pal.border, pal.panel) >= 1.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize(
    "abajo,arriba", [("bg", "panel"), ("panel", "surface"), ("surface", "surface_alt")]
)
def test_los_escalones_se_distinguen(pal: Palette, abajo: str, arriba: str) -> None:
    """La separacion entre paneles es este salto: si se aplana, la columna
    derecha vuelve a ser una sola mancha. `chrome` no esta en la lista: la
    fila del menu se separa del lienzo con un borde, no con luminancia.

    El piso es 1.09 y no el 1.106 del gris de partida porque el hex final
    tiene 8 bits por canal: redondear el tono corre el escalon un milesimo.
    """
    assert contraste(getattr(pal, arriba), getattr(pal, abajo)) >= 1.09


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize(
    "rol", ["chrome", "bg", "panel", "surface", "surface_hover", "surface_alt"]
)
def test_tenir_no_mueve_el_escalon(pal: Palette, rol: str) -> None:
    """Teñir cambia el tono, no la profundidad: cada fondo conserva la
    luminancia de su neutro de partida. Es lo que garantiza que el contraste
    de todo lo que va encima sea el mismo en los ocho temas.
    """
    base = {
        "chrome": Colors.CHROME,
        "bg": Colors.BG,
        "panel": Colors.PANEL,
        "surface": Colors.SURFACE,
        "surface_hover": Colors.SURFACE_HOVER,
        "surface_alt": Colors.SURFACE_ALT,
    }[rol]
    assert _luminancia(getattr(pal, rol)) == pytest.approx(_luminancia(base), abs=0.001)


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_los_fondos_siguen_siendo_oscuros(pal: Palette) -> None:
    """El tema oscuro es el punto de partida, no algo que se negocie tono a
    tono: ningun fondo puede irse a claro.
    """
    assert _luminancia(pal.surface_alt) < 0.08


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
@pytest.mark.parametrize(
    "rol", ["chrome", "bg", "panel", "surface", "surface_hover", "surface_alt"]
)
def test_los_fondos_llevan_color_de_verdad(pal: Palette, rol: str) -> None:
    """El fondo tiene que leerse como el color del repo, no como un gris.

    Por debajo del 35 % de saturacion HSL el tono se pierde a tamaño de
    pantalla y la ventana vuelve a parecer gris — que es justo lo que este
    diseño viene a corregir. El piso es 0.35 y no la saturacion nominal de la
    receta porque el hex final tiene 8 bits por canal: redondear un fondo muy
    oscuro se come unas centesimas.
    """
    assert QColor(getattr(pal, rol)).saturationF() >= 0.35


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_la_barra_de_menu_no_es_negra(pal: Palette) -> None:
    """`chrome` es la banda de la fila del menu, y es la mas clara de la
    escalera de fondos, no la mas oscura: por encima del cuerpo de las
    secciones y de las cabeceras.
    """
    assert _luminancia(pal.chrome) > _luminancia(pal.surface)


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_la_pestana_seleccionada_se_lee(pal: Palette) -> None:
    """La pestana del repo seleccionado se pinta de `chrome` —el color de la
    fila del menu, la de justo debajo— con el nombre en el acento
    (`ui/project_tabs.py`).
    """
    assert contraste(pal.accent, pal.chrome) >= 4.5


@pytest.mark.parametrize("pal", TEMAS, ids=IDS)
def test_las_pestanas_se_leen_sobre_la_barra(pal: Palette) -> None:
    """Todas las pestanas de repo llevan el acento del repo activo de fondo
    —el color con el que queda pintada la barra de titulo— y el nombre, el
    contorno y la marca `◇ CONSOLA` van en `on_accent` encima
    (`ui/project_tabs.py`, `ui/title_bar.py`).
    """
    assert contraste(pal.on_accent, pal.accent) >= 4.5


def test_los_estados_no_se_tiñen() -> None:
    """Un exito y un error significan lo mismo en todos los repos: ningun
    color semantico sale de una paleta.
    """
    campos = set(palettes.Palette.__dataclass_fields__)
    assert {"success", "warning", "error"}.isdisjoint(campos)


def test_cada_tema_tiene_su_clave() -> None:
    assert all(clave == pal.key for clave, pal in palettes.THEMES.items())


def test_no_repite_mientras_queden_temas() -> None:
    usados: list[str] = []
    for _ in palettes.THEMES:
        clave = palettes.first_free(usados)
        assert clave not in usados
        usados.append(clave)
    # Agotados los ocho, vuelve al primero en vez de quedarse sin respuesta.
    assert palettes.first_free(usados) == next(iter(palettes.THEMES))
