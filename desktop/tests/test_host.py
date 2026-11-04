"""Lo que cambia de un sistema a otro (ADR-0048).

Casi todo se prueba en cualquier maquina: las dos clases se instancian en las
dos, y lo que es solo leer rutas se prueba sobre una carpeta temporal. Lo que
necesita el sistema de verdad —matar un grupo de procesos POSIX— se salta
fuera de el.
"""

import os
import re
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1] / "src" / "app"

from app.core import host, process
from app.core.errors import TaskError


@pytest.mark.parametrize("clase", [host.WindowsHost, host.PosixHost])
def test_cada_sistema_implementa_todo(clase):
    clase()  # a una clase con un abstracto sin implementar no se la puede instanciar


def test_nadie_mas_pregunta_el_sistema():
    patron = re.compile(r"\bos\.name\b|\bsys\.platform\b|\bplatform\.system\(")
    culpables = []
    for archivo in [*RAIZ.glob("core/**/*.py"), *RAIZ.glob("ui/**/*.py"), RAIZ / "main.py"]:
        if archivo == RAIZ / "core" / "host.py":
            continue
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            codigo = linea.split("#", 1)[0]
            if patron.search(codigo) and "`" not in codigo:
                culpables.append(f"{archivo.relative_to(RAIZ)}:{n}: {linea.strip()}")
    assert culpables == []


# --- postgres --------------------------------------------------------------


def _instalar(root: Path, version: str, *herramientas: str) -> None:
    carpeta = root / version / "bin"
    carpeta.mkdir(parents=True)
    for nombre in herramientas:
        (carpeta / nombre).write_text("")


def test_linux_usa_la_version_mas_nueva_por_numero(tmp_path):
    _instalar(tmp_path, "9.6", "psql")
    _instalar(tmp_path, "16", "psql")
    _instalar(tmp_path, "17")  # la 17 sin cliente no cuenta
    linux = host.PosixHost()
    linux.PG_ROOT = tmp_path
    assert linux.pg_tool("psql") == tmp_path / "16" / "bin" / "psql"


def test_windows_usa_la_version_mas_nueva_por_numero(tmp_path):
    _instalar(tmp_path, "9.6", "pg_dump.exe")
    _instalar(tmp_path, "17", "pg_dump.exe")
    windows = host.WindowsHost()
    windows.PG_ROOT = tmp_path
    assert windows.pg_tool("pg_dump") == tmp_path / "17" / "bin" / "pg_dump.exe"


def test_linux_sin_postgres_lo_dice(tmp_path):
    linux = host.PosixHost()
    linux.PG_ROOT = tmp_path / "no-existe"
    with pytest.raises(TaskError, match="apt install postgresql"):
        linux.pg_tool("pg_restore")


def test_linux_lee_el_puerto_del_cluster_mas_nuevo(tmp_path):
    for version, puerto in (("15", 5432), ("17", 5433)):
        conf = tmp_path / version / "main" / "postgresql.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(f"#port = 1\nport = {puerto}\t\t# (change requires restart)\n")
    linux = host.PosixHost()
    linux.PG_CONF_ROOT = tmp_path
    assert linux.pg_port() == 5433


def test_linux_sin_configuracion_usa_5432(tmp_path):
    linux = host.PosixHost()
    linux.PG_CONF_ROOT = tmp_path
    assert linux.pg_port() == 5432


# --- terminal ---------------------------------------------------------------


def test_linux_abre_la_terminal_del_escritorio(monkeypatch):
    monkeypatch.setattr(host.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
    argv = host.PosixHost().terminal_argv(["ssh", "deploy@1.2.3.4"])
    assert argv == ["/usr/bin/x-terminal-emulator", "-e", "ssh", "deploy@1.2.3.4"]


def test_linux_sin_terminal_lo_dice(monkeypatch):
    monkeypatch.setattr(host.shutil, "which", lambda nombre: None)
    with pytest.raises(TaskError, match="x-terminal-emulator"):
        host.PosixHost().terminal_argv(["ssh", "deploy@1.2.3.4"])


# --- procesos (solo POSIX) --------------------------------------------------

solo_posix = pytest.mark.skipif(os.name == "nt", reason="grupos de procesos POSIX")


@solo_posix
def test_detener_una_tarea_no_mata_a_consola():
    """Antes el hijo compartia el grupo de Consola y `killpg` la mataba a ella:
    con la falla, esta prueba no falla: mata a pytest entero.
    """
    proc = process.spawn(["sleep", "30"])
    process.kill_tree(proc, grace=2)
    assert proc.poll() is not None


@solo_posix
def test_detener_mata_tambien_a_los_nietos():
    proc = process.spawn(["sh", "-c", "sleep 30 & echo $!; wait"])
    nieto = int(proc.stdout.readline())
    process.kill_tree(proc, grace=2)

    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        try:
            os.kill(nieto, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"El nieto {nieto} sigue vivo.")


@solo_posix
def test_la_consulta_corta_no_cambia_de_sesion():
    salida = process.capture([sys.executable, "-c", "import os; print(os.getsid(0))"])
    assert int(salida) == os.getsid(0)


def test_spawn_arranca_en_este_sistema():
    proc = process.spawn([sys.executable, "-c", 'print("ok")'])
    assert proc.stdout.readline().strip() == "ok"
    assert proc.wait(timeout=10) == 0
