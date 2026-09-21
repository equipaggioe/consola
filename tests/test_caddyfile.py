"""El Caddyfile que sale de una tabla de rutas.

`_caddyfile` no toca red ni disco, asi que se puede comprobar entera contra el
texto que tiene que salir. Es la unica parte de `configure_caddy` que se prueba,
y la que mas duele si sale mal: un Caddyfile con la forma equivocada tira abajo
todo lo que publica el VPS, no una app.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import vps
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


def test_tabla_vieja_sin_host_sigue_significando_lo_mismo():
    """Una tabla escrita cuando el host no se podia nombrar usa `PUBLIC_HOST`."""
    conf = render(FakeConfig(
        PUBLIC_HOST='ejemplo.net',
        PUBLIC_ROUTES='/api/* proxy 127.0.0.1:8000,/admin/* spa /srv/admin,* spa /srv/pwa',
    ))
    assert conf.count('encode zstd gzip') == 1, 'un solo host, un solo bloque'
    assert conf.startswith('ejemplo.net {')
    assert 'handle /api/*' in conf
    assert 'uri strip_prefix /admin' in conf
    assert 'Content-Security-Policy' not in conf, 'sin CSP cargada no se emite'


def test_csp_por_sitio():
    """Cada host lleva la suya; `*` es la de los demas."""
    conf = render(FakeConfig(
        PUBLIC_ROUTES=('back.ejemplo.net/* spa /srv/back,ejemplo.net/* spa /srv/landing'),
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

    try:
        vps.parse_routes(['a.ejemplo.net/* spa /srv/a', 'a.ejemplo.net/api/* proxy 1:2'])
    except Exception as error:
        assert 'catch-all' in str(error)
    else:
        raise AssertionError('dos reglas del mismo host con el catch-all primero tienen que fallar')


def test_csp_sin_host_es_la_de_todos_los_sitios():
    """La forma en que ya estaba escrita antes de que `CSP` fuera una tabla.

    Se distingue sin ambiguedad porque una politica empieza siempre con una
    directiva y ninguna lleva punto, mientras que un host exige al menos uno.
    """
    politica = ("default-src 'self'; img-src 'self' data: blob:; "
                "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
    conf = render(FakeConfig(
        PUBLIC_HOST='concordia.ejemplo.net',
        PUBLIC_ROUTES='/api/* proxy 127.0.0.1:8000,/backoffice/* spa /srv/back,* spa /srv/landing',
        CSP=politica,
    ))
    assert f'Content-Security-Policy "{politica}"' in conf


def test_una_tabla_por_rutas_sigue_dando_un_solo_sitio():
    """Un repo publicado por subrutas no cambia de forma al poder nombrar hosts."""
    conf = render(FakeConfig(
        PUBLIC_HOST='concordia.ejemplo.net',
        PUBLIC_ROUTES=('/api/* proxy 127.0.0.1:8000,/ws/* proxy 127.0.0.1:8000,'
                       '/media/* static /var/storage/public,/backoffice/* spa /srv/back,'
                       '/pwa/* spa /srv/pwa,* spa /srv/landing'),
    ))
    assert conf.count('encode zstd gzip') == 1
    assert conf.startswith('concordia.ejemplo.net {')
    assert 'uri strip_prefix /backoffice' in conf
    assert 'uri strip_prefix /pwa' in conf
    # El catch-all de la landing no recorta nada.
    assert conf.rstrip().endswith('}')
