"""What a backup restores, and how SSH enters a new VPS."""

from pathlib import Path

from app.services import ssh
from app.services.tasks.database import _without_extensions


def test_the_restore_does_not_touch_extensions() -> None:
    """The restore leaves extensions out."""
    content = (
        "; Archive created\n"
        "215; 1259 16400 TABLE public dato prueba\n"
        "3; 3079 16385 EXTENSION - pg_trgm\n"
        "4000; 0 0 COMMENT - EXTENSION pg_trgm\n"
        "3900; 0 16400 TABLE DATA public dato prueba\n"
    )
    assert _without_extensions(content) == (
        "; Archive created\n"
        "215; 1259 16400 TABLE public dato prueba\n"
        "3900; 0 16400 TABLE DATA public dato prueba\n"
    )


def test_a_new_vps_records_its_fingerprint_and_a_different_one_stops() -> None:
    """SSH accepts a new fingerprint and rejects a changed one."""
    remote = ssh.Remote("192.0.2.1", "admin", Path("llave"))
    assert "StrictHostKeyChecking=accept-new" in remote.argv("true")
    assert "StrictHostKeyChecking=accept-new" in remote.scp_argv(Path("a"), "/b")
