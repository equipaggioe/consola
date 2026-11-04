"""The canone units Consola operates.

`resolve_service` touches no network or disk. This checks that each
value of the `service` axis names the unit `install.py` installs.
"""

import pytest

from app.core import vps
from app.core.errors import TaskError


@pytest.mark.parametrize(
    ("value", "unit"),
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
def test_each_value_names_its_unit(value: str, unit: str) -> None:
    """Each value names its unit."""
    assert vps.resolve_service("banditore", value) == unit


def test_no_value_is_the_server() -> None:
    """No value means the server."""
    assert vps.resolve_service("banditore") == "banditore"


def test_each_value_has_its_label() -> None:
    """Each value has its label."""
    values = [*vps._APP_UNITS, *vps.PACKAGE_SERVICES]
    assert set(values) == set(vps.SERVICE_LABELS)


def test_unknown_service_on_the_axis() -> None:
    """An unknown service stops."""
    with pytest.raises(TaskError):
        vps.resolve_service("banditore", "proyecto")


def test_systemctl_without_sudo() -> None:
    """`vps_setup.Access` adds the `sudo` that asks for the password."""
    assert vps.systemctl_command("restart", "banditore") == "systemctl restart banditore"
    assert vps.systemctl_command("daemon-reload", "banditore") == "systemctl daemon-reload"
    assert vps.journal_command("banditore", lines=5).startswith("journalctl -u banditore -n 5")


def test_unknown_action() -> None:
    """An unknown action stops."""
    with pytest.raises(TaskError):
        vps.systemctl_command("reboot", "banditore")
