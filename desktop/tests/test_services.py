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


def test_a_java_piece_names_its_instance() -> None:
    """A piece in Java names its instance of `<app>-java@`."""
    unit = vps.resolve_service("presenze", "java:server-fingerprint")
    assert unit == "presenze-java@server-fingerprint"


def test_a_java_piece_with_a_name_canone_does_not_allow() -> None:
    """A piece named outside `scripts/java.py`'s pattern stops."""
    with pytest.raises(TaskError):
        vps.resolve_service("presenze", "java:x; reboot")


def test_a_java_piece_has_its_label() -> None:
    """Each piece in Java has its label."""
    labels = vps.service_labels(["server", "java:server-fingerprint"])
    assert labels["java:server-fingerprint"] == "Java: server-fingerprint"


def test_a_task_names_its_instance_and_has_its_label() -> None:
    """A task with its own timer names its instance of `<app>-task@`."""
    assert vps.resolve_service("concordia", "task:safety") == "concordia-task@safety"
    assert vps.service_labels(["task:safety"])["task:safety"] == "Tarea: safety"
    with pytest.raises(TaskError):
        vps.resolve_service("concordia", "task:x; reboot")


def test_a_browser_task_names_its_instance_and_has_its_label() -> None:
    """A task that drives Chromium names its `<app>-browser@` unit."""
    assert vps.resolve_service("bot", "browser:attempt") == "bot-browser@attempt"
    labels = vps.service_labels(["browser:attempt"])
    assert labels["browser:attempt"] == "Tarea con navegador: attempt"
    with pytest.raises(TaskError):
        vps.resolve_service("bot", "browser:x; reboot")


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("presenze", "server"),
        ("coturn", "coturn"),
        ("presenze-java@server-fingerprint.service", "java:server-fingerprint"),
        ("otra-java@server-fingerprint.service", ""),
        ("presenze-task@safety.timer", "task:safety"),
        ("presenze-task@safety.service", ""),
        ("otra-task@safety.timer", ""),
        ("presenze-browser@attempt.timer", "browser:attempt"),
        ("presenze-browser@attempt.service", ""),
    ],
)
def test_each_unit_the_vps_answers(line: str, value: str) -> None:
    """Each line the VPS answers becomes its axis value, or none."""
    names = {unit: v for v, unit in vps._fixed_units("presenze").items()}
    assert vps._axis_value("presenze", line, names) == value


def test_systemctl_without_sudo() -> None:
    """`vps_setup.Access` adds the `sudo` that asks for the password."""
    assert vps.systemctl_command("restart", "banditore") == "systemctl restart banditore"
    assert vps.systemctl_command("daemon-reload", "banditore") == "systemctl daemon-reload"
    assert vps.journal_command("banditore", lines=5).startswith("journalctl -u banditore -n 5")


def test_unknown_action() -> None:
    """An unknown action stops."""
    with pytest.raises(TaskError):
        vps.systemctl_command("reboot", "banditore")
