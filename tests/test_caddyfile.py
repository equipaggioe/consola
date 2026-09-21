"""El Caddyfile que sale de una tabla de rutas.

`_caddyfile` no toca red ni disco, asi que se puede comprobar entera contra el
texto que tiene que salir. Es la unica parte de `configure_caddy` que se prueba,
y la que mas duele si sale mal: un Caddyfile con la forma equivocada tira abajo
todo lo que publica el VPS, no una app.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core import vps
from core.errors import TaskError
from core.tasks.vps_setup import _caddyfile


class FakeConfig:
    def __init__(self, **valores):
        self._valores = valores

    def get(self, clave):
        return self._valores.get(clave, '')


def render(config):
    sitios = vps.sites(config)
    destinos = {}
    for _, rutas in sitios:
        for route in rutas:
            destinos[id(route)] = route.target
    return _caddyfile(sites=sitios, destinos=destinos, politicas=vps.csp_by_host(config))


def test_un_host_por_pieza():
    """La forma del ADR-0020 de banditore: cada pieza en su propio host."""
    conf = render(FakeConfig(
        PUBLIC_ROUTES=('api.banditore.equipaggio.net/* proxy 127.0.0.1:8000,'
                       'backoffice.banditore.equipaggio.net/* spa /srv/backoffice,'
                       'banditore.equipaggio.net/* spa /srv/landing'),
        CSP="* default-src 'self'",
    ))
    assert conf.count('encode zstd gzip') == 3, 'un bloque de sitio por host'
    assert 'api.banditore.equipaggio.net {' in conf
    assert 'backoffice.banditore.equipaggio.net {' in conf
    assert 'banditore.equipaggio.net {' in conf
    # Con host propio no hay prefijo que recortar: eso es medio motivo de la decision.
    assert 'strip_prefix' not in conf
    assert 'reverse_proxy 127.0.0.1:8000' in conf


def test_un_patron_sin_host_corta():
    """Antes se deducia de PUBLIC_HOST; ahora falla donde se escribe."""
    for patron in ('*', '/api/*'):
        with pytest.raises(TaskError) as error:
            vps.parse_routes([f'{patron} spa /srv/x'])
        assert 'no es un nombre de host' in str(error.value)


def test_una_csp_sin_host_corta():
    """Una politica pelada se aplicaba callada a todos los sitios."""
    politica = "default-src 'self'; script-src 'self' 'unsafe-inline'"
    with pytest.raises(TaskError) as error:
        vps.csp_by_host(FakeConfig(CSP=politica))
    assert 'no es un nombre de host' in str(error.value)
    # Con el host escrito, la misma politica vale para todos.
    assert vps.csp_by_host(FakeConfig(CSP=f'* {politica}')) == {'*': politica}


def test_varias_rutas_bajo_un_mismo_host():
    """Un repo que publica por subrutas escribe su host en cada regla.

    Es la forma de un repo cuyo propio backend monta las SPA: no hay Caddy de por
    medio, pero la tabla sigue diciendo donde se publica cada una, y de ahi sale
    el `base` con que se compila.
    """
    config = FakeConfig(PUBLIC_ROUTES='ejemplo.net/terminal/* spa terminal,ejemplo.net/* spa clientes')
    assert vps.spa_base(config, 'terminal') == '/terminal'
    assert vps.spa_base(config, 'clientes') == ''
    assert vps.uses_proxy(config) is False
    assert [h for h, _ in vps.sites(config)] == ['ejemplo.net']


def test_csp_por_sitio():
    """Cada host lleva la suya; `*` es la de los demas."""
    conf = render(FakeConfig(
        PUBLIC_ROUTES='back.ejemplo.net/* spa /srv/back,ejemplo.net/* spa /srv/landing',
        CSP=("* default-src 'self',"
             "back.ejemplo.net default-src 'self' https://unpkg.com"),
    ))
    assert "Content-Security-Policy \"default-src 'self' https://unpkg.com\"" in conf
    assert "Content-Security-Policy \"default-src 'self'\"" in conf
    # La permisiva no se le aplica a la landing.
    assert conf.index('back.ejemplo.net {') < conf.index('unpkg.com')


def test_catch_all_por_host_y_no_por_tabla():
    """Dos catch-all seguidos son correctos si son de hosts distintos."""
    vps.parse_routes(['a.ejemplo.net/* spa /srv/a', 'b.ejemplo.net/* spa /srv/b'])

    with pytest.raises(TaskError) as error:
        vps.parse_routes(['a.ejemplo.net/* spa /srv/a', 'a.ejemplo.net/api/* proxy 1:2'])
    assert 'catch-all' in str(error.value)
