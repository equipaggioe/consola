"""Everything that changes from one system to another on THIS machine.

ADR-0048. Consola runs on Windows and Linux. The VPS does not pass
through here: it is always Linux and receives POSIX commands, wherever
Consola runs.

Each difference is an abstract method or attribute of `Host`, with one
class per system. A class missing one cannot be instantiated on any
machine, so `tests/test_host.py` detects the missing Linux piece from
Windows, and vice versa. Outside this file nobody asks about `os.name`:
they ask `HOST`.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication

from app.services.errors import TaskError

# `<version>` is the folder name of each Postgres install on both
# systems: `C:/Program Files/PostgreSQL/17`, `/usr/lib/postgresql/17`.
_PG_VERSION = re.compile(r"^(\d+)")
_PORT_LINE = re.compile(r"^port\s*=\s*'?(\d+)'?")


def _newest_first(root: Path) -> list[Path]:
    """Return Postgres's version folders, newest first.

    By number and not name: as text, `9.6` comes before `17`. A machine
    with 15 and 17 has to use 17, because 15 refuses to read a 17
    server.
    """
    if not root.is_dir():
        return []
    versions = [
        (int(m.group(1)), d)
        for d in root.iterdir()
        if d.is_dir() and (m := _PG_VERSION.match(d.name))
    ]
    return [d for _, d in sorted(versions, key=lambda par: par[0], reverse=True)]


def _port_in(conf: Path) -> int | None:
    for raw in conf.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _PORT_LINE.match(raw.strip())
        if match:
            return int(match.group(1))
    return None


# Where `ssh` finds the password its `SSH_ASKPASS` prints.
ASKPASS_VARIABLE = "CONSOLA_SSH_PASSWORD"


class Host(ABC):
    """The answers that depend on the system Consola runs on."""

    # `platform.system()`: it labels a binary and decides which
    # platforms can compile here.
    system: str = platform.system()

    # --- executables ---

    @property
    @abstractmethod
    def executable_suffix(self) -> str:
        """What PyInstaller adds to the `--onefile` executable."""

    @abstractmethod
    def executable_names(self, name: str) -> list[str]:
        """Return the names the executable `name` can have on disk."""

    @abstractmethod
    def script_name(self, name: str) -> str:
        """Return an SDK's launcher (`flutter`, `sdkmanager`).

        `.bat` on Windows.
        """

    @abstractmethod
    def venv_bin(self, venv: Path) -> Path:
        """Return a venv's folder of executables."""

    @abstractmethod
    def venv_python(self, venv: Path) -> Path:
        """Return a venv's interpreter.

        It only locates, without checking.
        """

    # --- processes ---

    @abstractmethod
    def wrap_script(self, executable: str) -> list[str]:
        """Return the argv that runs `executable`.

        On Windows it may be a shim.
        """

    @abstractmethod
    def spawn_options(self, *, detached: bool) -> dict[str, Any]:
        """Return `Popen` arguments that let `kill_group` kill it."""

    @abstractmethod
    def run_options(self) -> dict[str, Any]:
        """Return `subprocess.run` arguments for a short query."""

    @abstractmethod
    def kill_group(self, proc: subprocess.Popen[str]) -> None:
        """End the process and all it launched, or raise `OSError`."""

    @abstractmethod
    def bind_to_app(self, proc: subprocess.Popen[str]) -> None:
        """Make the process die with Consola, even on a crash."""

    # --- ssh ---

    @property
    @abstractmethod
    def ssh_multiplex(self) -> bool:
        """Return whether `ssh` can reuse a connection."""

    @abstractmethod
    def terminal_argv(self, argv: list[str]) -> list[str]:
        """Return `argv` inside a new terminal, with a real TTY."""

    # --- local postgres ---

    @abstractmethod
    def pg_tool(self, name: str) -> Path:
        """Return `psql`, `pg_dump` or `pg_restore`.

        It comes from the newest install.
        """

    @abstractmethod
    def pg_port(self) -> int:
        """Return the local Postgres's port, from its configuration."""

    # --- machine ---

    @property
    @abstractmethod
    def sdk_key(self) -> str:
        """Return how Android and Flutter downloads name this system."""

    @property
    @abstractmethod
    def android_dir_default(self) -> str:
        """Return the default folder of the Android SDK."""

    @property
    @abstractmethod
    def flutter_dir_default(self) -> str:
        """Return the default folder of the Flutter SDK."""

    @property
    @abstractmethod
    def unix_modes(self) -> bool:
        """Return whether extracting a zip applies its permissions."""

    @property
    @abstractmethod
    def env_store(self) -> str:
        """Return where the user environment persists.

        `registry` or `profile` (`services/userenv.py`).
        """

    @property
    @abstractmethod
    def emulator_acceleration(self) -> str:
        """Return `driver` if it installs, `kvm` if it only verifies.

        See `services/tasks/utils.py::install_android_hypervisor`.
        """

    @abstractmethod
    def data_dir(self) -> Path:
        """Return Consola's data folder on this machine."""

    @abstractmethod
    def askpass(self, folder: Path) -> Path:
        """Write in folder an `SSH_ASKPASS` that prints the password.

        It prints the variable `ASKPASS_VARIABLE`: the password goes in
        the environment of `ssh` and not in the file, which has nothing
        secret.
        """

    @abstractmethod
    def memory(self) -> tuple[int, int] | None:
        """Return available and total RAM in bytes, or `None`."""


class WindowsHost(Host):
    """The answers on Windows."""

    PG_ROOT = Path(r"C:\Program Files\PostgreSQL")

    _NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
    _NEW_PROCESS_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP

    executable_suffix = ".exe"
    # Win32-OpenSSH's ControlMaster emulates Unix sockets with pipes and
    # fails to reuse the socket between invocations.
    ssh_multiplex = False
    sdk_key = "windows"
    android_dir_default = r"D:\Android"
    flutter_dir_default = r"D:\flutter"
    unix_modes = False
    env_store = "registry"
    emulator_acceleration = "driver"

    def __init__(self) -> None:
        """Start with no job object yet."""
        self._job: int | None = None
        self._job_lock = threading.Lock()

    def executable_names(self, name: str) -> list[str]:
        """Return the name with Windows's executable extensions."""
        return [f"{name}.exe", f"{name}.bat", f"{name}.cmd"]

    def script_name(self, name: str) -> str:
        """Return the script's `.bat` name."""
        return f"{name}.bat"

    def venv_bin(self, venv: Path) -> Path:
        """Return the venv's `Scripts` folder."""
        return venv / "Scripts"

    def venv_python(self, venv: Path) -> Path:
        """Return the venv's `python.exe`."""
        return self.venv_bin(venv) / "python.exe"

    def wrap_script(self, executable: str) -> list[str]:
        # `flutter.bat` or `pnpm.cmd` are not real executables: they
        # only run through `cmd.exe /c`.
        """Return the argv that runs it, through `cmd.exe` if a shim."""
        if executable.lower().endswith((".bat", ".cmd")):
            return ["cmd.exe", "/c", executable]
        return [executable]

    def spawn_options(self, *, detached: bool) -> dict[str, Any]:
        """Return the process-group and window flags."""
        flags = self._NO_WINDOW | (self._NEW_PROCESS_GROUP if detached else 0)
        return {"creationflags": flags}

    def run_options(self) -> dict[str, Any]:
        """Return the flag that hides the console window."""
        return {"creationflags": self._NO_WINDOW}

    def kill_group(self, proc: subprocess.Popen[str]) -> None:
        """Run `taskkill /T` over the process tree."""
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=self._NO_WINDOW,
        )

    def bind_to_app(self, proc: subprocess.Popen[str]) -> None:
        """Add the process to a Job Object with KILL_ON_JOB_CLOSE.

        Only this process holds the job's handle, and when it dies the
        system closes the handle and kills what is inside.
        """
        import ctypes
        from ctypes import wintypes

        if sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = wintypes.HANDLE
            kernel32.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

            with self._job_lock:
                if self._job is None:

                    class _Basic(ctypes.Structure):
                        _fields_ = [
                            ("PerProcessUserTimeLimit", ctypes.c_int64),
                            ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD),
                            ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t),
                            ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t),
                            ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD),
                        ]

                    class _Io(ctypes.Structure):
                        _fields_ = [
                            (n, ctypes.c_uint64)
                            for n in (
                                "ReadOperationCount",
                                "WriteOperationCount",
                                "OtherOperationCount",
                                "ReadTransferCount",
                                "WriteTransferCount",
                                "OtherTransferCount",
                            )
                        ]

                    class _Extended(ctypes.Structure):
                        _fields_ = [
                            ("BasicLimitInformation", _Basic),
                            ("IoInfo", _Io),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t),
                        ]

                    job = kernel32.CreateJobObjectW(None, None)
                    if not job:
                        return
                    info = _Extended()
                    # KILL_ON_JOB_CLOSE
                    info.BasicLimitInformation.LimitFlags = 0x2000
                    if not kernel32.SetInformationJobObject(
                        job,
                        9,
                        ctypes.byref(info),  # Extended
                        ctypes.sizeof(info),
                    ):
                        kernel32.CloseHandle(job)
                        return
                    self._job = job
                kernel32.AssignProcessToJobObject(self._job, int(getattr(proc, "_handle")))
        else:
            raise OSError("Solo existe en Windows.")

    def terminal_argv(self, argv: list[str]) -> list[str]:
        """Return `argv` in a new console window."""
        return ["wt.exe", *argv]

    def pg_tool(self, name: str) -> Path:
        """Return the tool from the newest `Program Files` install."""
        for version_dir in _newest_first(self.PG_ROOT):
            candidate = version_dir / "bin" / f"{name}.exe"
            if candidate.is_file():
                return candidate
        raise TaskError(
            QCoreApplication.translate(
                "WindowsHost", "No se encontro {0}.exe en {1}: instala PostgreSQL en esta maquina."
            ).format(name, self.PG_ROOT)
        )

    def pg_port(self) -> int:
        """Return the port in the newest `postgresql.conf`."""
        for version_dir in _newest_first(self.PG_ROOT):
            conf = version_dir / "data" / "postgresql.conf"
            if conf.is_file() and (port := _port_in(conf)) is not None:
                return port
        return 5432

    def data_dir(self) -> Path:
        """Return `%LOCALAPPDATA%/Consola`."""
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "Consola"

    def askpass(self, folder: Path) -> Path:
        """Write a `.cmd` that has PowerShell print the variable.

        Not `echo %VAR%`: cmd expands `%`, `^`, `&` and `!` of the
        password itself.
        """
        helper = folder / "askpass.cmd"
        folder.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "@powershell -NoProfile -NonInteractive -Command "
            f'"[Console]::Out.Write($env:{ASKPASS_VARIABLE})"\r\n',
            encoding="utf-8",
            newline="",
        )
        return helper

    def memory(self) -> tuple[int, int] | None:
        """Return RAM from `GlobalMemoryStatusEx`."""
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if sys.platform == "win32":
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return status.ullAvailPhys, status.ullTotalPhys
        else:
            raise OSError("Solo existe en Windows.")


class PosixHost(Host):
    # Debian and Ubuntu's paths: `postgresql-common` installs each
    # version in its folder and leaves one `main` cluster per version
    # (ADR-0048).
    """The answers on Linux."""

    PG_ROOT = Path("/usr/lib/postgresql")
    PG_CONF_ROOT = Path("/etc/postgresql")
    TERMINAL = "x-terminal-emulator"

    executable_suffix = ""
    ssh_multiplex = True
    android_dir_default = "~/Android/Sdk"
    flutter_dir_default = "~/flutter"
    unix_modes = True
    env_store = "profile"
    emulator_acceleration = "kvm"

    @property
    def sdk_key(self) -> str:
        """Return how Android and Flutter downloads name Linux."""
        return "mac" if sys.platform == "darwin" else "linux"

    def executable_names(self, name: str) -> list[str]:
        """Return the name as is."""
        return [name]

    def script_name(self, name: str) -> str:
        """Return the script's name as is."""
        return name

    def venv_bin(self, venv: Path) -> Path:
        """Return the venv's `bin` folder."""
        return venv / "bin"

    def venv_python(self, venv: Path) -> Path:
        """Return the venv's `python`."""
        return self.venv_bin(venv) / "python"

    def wrap_script(self, executable: str) -> list[str]:
        """Return the executable as is."""
        return [executable]

    def spawn_options(self, *, detached: bool) -> dict[str, Any]:
        # Always in a session of its own, not only when detached:
        # `kill_group` signals the process's group, and a child sharing
        # Consola's group would pass it on to Consola. Stopping a task
        # closed the whole application.
        """Return `start_new_session`."""
        return {"start_new_session": True}

    def run_options(self) -> dict[str, Any]:
        """Return no extra options."""
        return {}

    def kill_group(self, proc: subprocess.Popen[str]) -> None:
        # With `start_new_session` the process leads its group: its pid
        # is the group's.
        """Send SIGTERM to the process's group."""
        if sys.platform != "win32":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            raise OSError("Solo existe en POSIX.")

    def bind_to_app(self, proc: subprocess.Popen[str]) -> None:
        """Do nothing: there is no equivalent yet.

        If Consola crashes, the process stays alive
        (docs/arquitectura/30_riesgos_y_pendientes.md). On a normal
        close `TabPanel.shutdown()` stops it.
        """

    def terminal_argv(self, argv: list[str]) -> list[str]:
        # Debian's alternative: it points to the desktop's terminal, and
        # Debian's policy requires accepting `-e program arguments...`.
        """Return `argv` in the desktop's terminal."""
        terminal = shutil.which(self.TERMINAL)
        if not terminal:
            raise TaskError(
                QCoreApplication.translate(
                    "PosixHost",
                    "No se encontro {0}: instala una terminal (gnome-terminal, konsole, "
                    "xterm) o configura la alternativa con update-alternatives --config {1}.",
                ).format(self.TERMINAL, self.TERMINAL)
            )
        return [terminal, "-e", *argv]

    def pg_tool(self, name: str) -> Path:
        """Return the tool from the newest cluster's folder."""
        for version_dir in _newest_first(self.PG_ROOT):
            candidate = version_dir / "bin" / name
            if candidate.is_file():
                return candidate
        raise TaskError(
            QCoreApplication.translate(
                "PosixHost",
                "No se encontro {0} en {1}: instala PostgreSQL en esta maquina (apt "
                "install postgresql).",
            ).format(name, self.PG_ROOT)
        )

    def pg_port(self) -> int:
        """Return the port in the newest `postgresql.conf`."""
        for version_dir in _newest_first(self.PG_CONF_ROOT):
            conf = version_dir / "main" / "postgresql.conf"
            if conf.is_file() and (port := _port_in(conf)) is not None:
                return port
        return 5432

    def data_dir(self) -> Path:
        """Return `$XDG_CACHE_HOME/consola` or `~/.cache/consola`."""
        base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
        return Path(base) / "consola"

    def askpass(self, folder: Path) -> Path:
        """Write an executable `sh` that prints the variable."""
        helper = folder / "askpass.sh"
        folder.mkdir(parents=True, exist_ok=True)
        helper.write_text(f'#!/bin/sh\nprintf "%s\\n" "${ASKPASS_VARIABLE}"\n', encoding="utf-8")
        helper.chmod(0o700)
        return helper

    def memory(self) -> tuple[int, int] | None:
        """Return RAM from `/proc/meminfo`."""
        try:
            with open("/proc/meminfo") as f:
                data: dict[str, int] = {}
                for line in f:
                    key, _, rest = line.partition(":")
                    if key in ("MemAvailable", "MemTotal"):
                        data[key] = int(rest.strip().split()[0]) * 1024
            return data["MemAvailable"], data["MemTotal"]
        except OSError:
            return None


HOST: Host = WindowsHost() if os.name == "nt" else PosixHost()
