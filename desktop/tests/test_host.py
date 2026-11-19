"""What changes from one system to another (ADR-0048).

Almost all of it tests on any machine: both classes instantiate on both,
and what only reads paths tests on a temporary folder. What needs the
real system, killing a POSIX process group, skips outside it.
"""

import os
import re
import sys
import time
from pathlib import Path

import pytest

from app.services import host, process
from app.services.errors import TaskError

ROOT = Path(__file__).resolve().parents[1] / "src" / "app"


@pytest.mark.parametrize("cls", [host.WindowsHost, host.PosixHost])
def test_each_system_implements_everything(cls: type[host.Host]) -> None:
    """Each system implements every abstract method."""
    # a class with an unimplemented abstract method cannot be
    # instantiated
    cls()


def test_nobody_else_asks_about_the_system() -> None:
    """Only `services/host.py` asks which system this is."""
    pattern = re.compile(r"\bos\.name\b|\bsys\.platform\b|\bplatform\.system\(")
    culprits = []
    for file in ROOT.glob("**/*.py"):
        if file == ROOT / "services" / "host.py":
            continue
        for n, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if pattern.search(code) and "`" not in code:
                culprits.append(f"{file.relative_to(ROOT)}:{n}: {line.strip()}")
    assert culprits == []


# --- postgres ---


def _install(root: Path, version: str, *tools: str) -> None:
    folder = root / version / "bin"
    folder.mkdir(parents=True)
    for name in tools:
        (folder / name).write_text("", encoding="utf-8")


def test_linux_uses_the_newest_version_by_number(tmp_path: Path) -> None:
    """Linux uses the newest version by number."""
    _install(tmp_path, "9.6", "psql")
    _install(tmp_path, "16", "psql")
    _install(tmp_path, "17")  # 17 without a client does not count
    linux = host.PosixHost()
    linux.PG_ROOT = tmp_path
    assert linux.pg_tool("psql") == tmp_path / "16" / "bin" / "psql"


def test_windows_uses_the_newest_version_by_number(tmp_path: Path) -> None:
    """Windows uses the newest version by number."""
    _install(tmp_path, "9.6", "pg_dump.exe")
    _install(tmp_path, "17", "pg_dump.exe")
    windows = host.WindowsHost()
    windows.PG_ROOT = tmp_path
    assert windows.pg_tool("pg_dump") == tmp_path / "17" / "bin" / "pg_dump.exe"


def test_linux_without_postgres_says_so(tmp_path: Path) -> None:
    """Linux without Postgres says so."""
    linux = host.PosixHost()
    linux.PG_ROOT = tmp_path / "no-existe"
    with pytest.raises(TaskError, match="apt install postgresql"):
        linux.pg_tool("pg_restore")


def test_linux_reads_the_port_of_the_newest_cluster(tmp_path: Path) -> None:
    """Linux reads the port of the newest cluster."""
    for version, port in (("15", 5432), ("17", 5433)):
        conf = tmp_path / version / "main" / "postgresql.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(
            f"#port = 1\nport = {port}\t\t# (change requires restart)\n", encoding="utf-8"
        )
    linux = host.PosixHost()
    linux.PG_CONF_ROOT = tmp_path
    assert linux.pg_port() == 5433


def test_linux_without_configuration_uses_5432(tmp_path: Path) -> None:
    """Linux without configuration uses 5432."""
    linux = host.PosixHost()
    linux.PG_CONF_ROOT = tmp_path
    assert linux.pg_port() == 5432


# --- terminal ---


def test_linux_opens_the_desktop_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux opens the desktop's terminal."""

    def which(name: str) -> str:
        return f"/usr/bin/{name}"

    monkeypatch.setattr(host.shutil, "which", which)
    argv = host.PosixHost().terminal_argv(["ssh", "deploy@1.2.3.4"])
    assert argv == ["/usr/bin/x-terminal-emulator", "-e", "ssh", "deploy@1.2.3.4"]


def test_linux_without_a_terminal_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux without a terminal says so."""

    def which(name: str) -> None:
        return None

    monkeypatch.setattr(host.shutil, "which", which)
    with pytest.raises(TaskError, match="x-terminal-emulator"):
        host.PosixHost().terminal_argv(["ssh", "deploy@1.2.3.4"])


# --- processes (POSIX only) ---

posix_only = pytest.mark.skipif(os.name == "nt", reason="grupos de procesos POSIX")


@posix_only
def test_stopping_a_task_does_not_kill_consola() -> None:
    """Stopping a task does not kill Consola.

    The child used to share Consola's group, and `killpg` killed it:
    with that fault, this test does not fail but kills pytest whole.
    """
    proc = process.spawn(["sleep", "30"])
    process.kill_tree(proc, grace=2)
    assert proc.poll() is not None


@posix_only
def test_stopping_also_kills_the_grandchildren() -> None:
    """Stopping also kills the grandchildren."""
    proc = process.spawn(["sh", "-c", "sleep 30 & echo $!; wait"])
    assert proc.stdout is not None
    grandchild = int(proc.stdout.readline())
    process.kill_tree(proc, grace=2)

    limit = time.monotonic() + 5
    while time.monotonic() < limit:
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"El nieto {grandchild} sigue vivo.")


@posix_only
def test_the_short_query_does_not_change_session() -> None:
    """The short query stays in this session."""
    output = process.capture([sys.executable, "-c", "import os; print(os.getsid(0))"])
    if sys.platform != "win32":
        assert int(output) == os.getsid(0)
    else:
        raise OSError("Solo existe en POSIX.")


def test_spawn_starts_on_this_system() -> None:
    """`spawn` starts on this system."""
    proc = process.spawn([sys.executable, "-c", 'print("ok")'])
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ok"
    assert proc.wait(timeout=10) == 0
