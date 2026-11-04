"""Lo que se restaura de un respaldo, y como entra SSH a un VPS nuevo."""

from pathlib import Path

from app.core import ssh
from app.core.tasks.database import _without_extensions


def test_la_restauracion_no_toca_las_extensiones() -> None:
    contenido = (
        "; Archive created\n"
        "215; 1259 16400 TABLE public dato prueba\n"
        "3; 3079 16385 EXTENSION - pg_trgm\n"
        "4000; 0 0 COMMENT - EXTENSION pg_trgm\n"
        "3900; 0 16400 TABLE DATA public dato prueba\n"
    )
    assert _without_extensions(contenido) == (
        "; Archive created\n"
        "215; 1259 16400 TABLE public dato prueba\n"
        "3900; 0 16400 TABLE DATA public dato prueba\n"
    )


def test_un_vps_nuevo_anota_su_huella_y_una_distinta_corta() -> None:
    remote = ssh.Remote("192.0.2.1", "admin", Path("llave"))
    assert "StrictHostKeyChecking=accept-new" in remote.argv("true")
    assert "StrictHostKeyChecking=accept-new" in remote.scp_argv(Path("a"), "/b")
