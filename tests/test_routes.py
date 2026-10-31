"""La tabla de rutas publicas.

`parse_routes` y `spa_base` no tocan red ni disco. De la tabla sale el `base`
con que se compila cada SPA: si no coincide con donde se publica, el navegador
pide los assets en otro lado y lo que se ve es una pagina en blanco.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core import vps
from core.errors import TaskError


class FakeConfig:
    def __init__(self, **valores):
        self._valores = valores

    def get(self, clave):
        return self._valores.get(clave, '')


def test_un_patron_sin_host_corta():
    """Antes se deducia de otra clave; ahora falla donde se escribe."""
    for patron in ('*', '/api/*'):
        with pytest.raises(TaskError) as error:
            vps.parse_routes([f'{patron} spa /srv/x'])
        assert 'no es un nombre de host' in str(error.value)


def test_varias_rutas_bajo_un_mismo_host():
    """Un repo que publica por subrutas escribe su host en cada regla.

    Es la forma de un repo cuyo propio backend monta las SPA: no hay proxy de
    por medio, pero la tabla sigue diciendo donde se publica cada una, y de ahi
    sale el `base` con que se compila.
    """
    config = FakeConfig(PUBLIC_ROUTES='ejemplo.net/terminal/* spa terminal,ejemplo.net/* spa clientes')
    assert vps.spa_base(config, 'terminal') == '/terminal'
    assert vps.spa_base(config, 'clientes') == ''


def test_sin_tabla_no_hay_base():
    """Un repo que no declaro su tabla no dijo bajo que ruta publica nada."""
    assert vps.spa_base(FakeConfig(), 'panel') is None


def test_catch_all_por_host_y_no_por_tabla():
    """Dos catch-all seguidos son correctos si son de hosts distintos."""
    vps.parse_routes(['a.ejemplo.net/* spa /srv/a', 'b.ejemplo.net/* spa /srv/b'])

    with pytest.raises(TaskError) as error:
        vps.parse_routes(['a.ejemplo.net/* spa /srv/a', 'a.ejemplo.net/api/* proxy 1:2'])
    assert 'catch-all' in str(error.value)
