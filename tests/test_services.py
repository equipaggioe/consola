"""La tabla de servicios de un repo.

`parse_services`, `services` y `unit_name` no tocan red ni disco. Lo que se
comprueba aca es sobre todo que un repo SIN tabla siga significando lo que
significaba: su unidad no puede renombrarse por un cambio de Consola, porque la
que esta corriendo en el VPS se llama como antes.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import vps
from core.errors import TaskError


class FakeConfig:
    def __init__(self, **valores):
        self._valores = valores

    def get(self, clave, default=''):
        return self._valores.get(clave, default)


def repo(**extra):
    return FakeConfig(GIT_REPO_URL='git@github.com:equipaggio/banditore.git', **extra)


def test_sin_tabla_hay_un_servicio_con_el_nombre_del_repo():
    config = repo()
    tabla = vps.services(config)
    assert len(tabla) == 1
    assert tabla[0].kind == 'uvicorn'
    assert vps.unit_name(config, tabla[0]) == 'banditore'
    assert vps.resolve_service(config, 'proyecto') == 'banditore'
    assert vps.managed_services(config) == ['proyecto', 'coturn', 'caddy']


def test_con_tabla_cada_fila_es_una_unidad():
    config = repo(SERVICES='api uvicorn app.main:app,push python -m app.push_worker')
    tabla = vps.services(config)
    assert [vps.unit_name(config, s) for s in tabla] == ['banditore-api', 'banditore-push']
    assert vps.resolve_service(config, 'push') == 'banditore-push'
    # El eje ofrece los del repo y despues los dos paquetes.
    assert vps.managed_services(config) == ['api', 'push', 'coturn', 'caddy']
    # `proyecto` sigue resolviendo: es el default de systemd_action y view_logs.
    assert vps.resolve_service(config, 'proyecto') == 'banditore-api'


def test_el_destino_de_command_se_toma_entero():
    """`command` lleva la linea con espacios; el sufijo y el tipo son los dos primeros."""
    tabla = vps.parse_services(['cron command /usr/bin/env python -m app.cron --cada 5'])
    assert tabla[0].target == '/usr/bin/env python -m app.cron --cada 5'


def test_filas_invalidas_cortan():
    for mala, esperado in [
        (['api'], 'mal formado'),
        (['api uvicorn'], 'mal formado'),
        (['API uvicorn app.main:app'], 'sufijo'),
        (['api noexiste app.main:app'], 'Tipo desconocido'),
        (['api uvicorn a,api python -m b'.split(',')[0], 'api python -m b'], 'mismo sufijo'),
    ]:
        with pytest.raises(TaskError) as error:
            vps.parse_services(mala)
        assert esperado in str(error.value)


def test_servicio_desconocido_en_el_eje():
    with pytest.raises(TaskError):
        vps.resolve_service(repo(SERVICES='api uvicorn app.main:app'), 'push')
