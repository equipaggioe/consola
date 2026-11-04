"""Las unidades de canone que opera Consola.

`resolve_service` no toca red ni disco. Lo que se comprueba aca es que cada valor
del eje `service` nombra la unidad que instala `install.py`.
"""

import pytest

from app.core import vps
from app.core.errors import TaskError


@pytest.mark.parametrize(
    "valor, unidad",
    [
        ("server", "banditore"),
        ("valkey", "valkey-server@banditore"),
        ("sweep", "banditore-sweep"),
        ("purge", "banditore-purge"),
        ("dump", "banditore-dump"),
        ("backup", "banditore-backup"),
        ("caddy", "caddy"),
        ("coturn", "coturn"),
    ],
)
def test_cada_valor_nombra_su_unidad(valor: str, unidad: str) -> None:
    assert vps.resolve_service("banditore", valor) == unidad


def test_sin_valor_es_el_servidor() -> None:
    assert vps.resolve_service("banditore") == "banditore"


def test_cada_valor_tiene_su_etiqueta() -> None:
    valores = [*vps._APP_UNITS, *vps.PACKAGE_SERVICES]
    assert set(valores) == set(vps.SERVICE_LABELS)


def test_servicio_desconocido_en_el_eje() -> None:
    with pytest.raises(TaskError):
        vps.resolve_service("banditore", "proyecto")


def test_systemctl_sin_sudo() -> None:
    """`vps_setup.Access` le pone el `sudo` que pide la contraseña."""
    assert vps.systemctl_command("restart", "banditore") == "systemctl restart banditore"
    assert vps.systemctl_command("daemon-reload", "banditore") == "systemctl daemon-reload"
    assert vps.journal_command("banditore", lines=5).startswith("journalctl -u banditore -n 5")


def test_accion_desconocida() -> None:
    with pytest.raises(TaskError):
        vps.systemctl_command("reboot", "banditore")
