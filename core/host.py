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

from .errors import TaskError

"""
Todo lo que cambia de un sistema a otro en ESTA maquina (ADR-0048).

Consola corre en Windows y en Linux. El VPS no pasa por aqui: es siempre Linux y
lo que se le manda son comandos POSIX, se corra Consola donde se corra.

Cada diferencia es un metodo o atributo abstracto de `Host`, con una clase por
sistema. A una clase que le falte uno no se la puede instanciar en ninguna
maquina, asi que `tests/test_host.py` detecta desde Windows la pieza de Linux
que falta, y al reves. Fuera de este archivo nadie pregunta `os.name`: le pide
la respuesta a `HOST`.
"""

# `<version>` es el nombre de la carpeta de cada instalacion de Postgres, en los
# dos sistemas: `C:\Program Files\PostgreSQL\17`, `/usr/lib/postgresql/17`.
_PG_VERSION = re.compile(r'^(\d+)')
_PORT_LINE = re.compile(r"^port\s*=\s*'?(\d+)'?")


def _newest_first(root: Path) -> list[Path]:
    """Las carpetas de version de Postgres, de la mas nueva a la mas vieja.

    Por numero y no por nombre: como texto, `9.6` queda antes que `17`. Una
    maquina con 15 y 17 tiene que usar la 17, porque la 15 se niega a leer un
    servidor 17.
    """
    if not root.is_dir():
        return []
    versiones = [(int(m.group(1)), d) for d in root.iterdir()
                 if d.is_dir() and (m := _PG_VERSION.match(d.name))]
    return [d for _, d in sorted(versiones, key=lambda par: par[0], reverse=True)]


def _port_in(conf: Path) -> int | None:
    for raw in conf.read_text(encoding='utf-8', errors='replace').splitlines():
        match = _PORT_LINE.match(raw.strip())
        if match:
            return int(match.group(1))
    return None


class Host(ABC):
    """Las respuestas que dependen del sistema donde corre Consola."""

    # `platform.system()`: con esto se etiqueta un binario y se decide que
    # plataformas se pueden compilar aqui.
    system: str = platform.system()

    # --- ejecutables -----------------------------------------------------

    @property
    @abstractmethod
    def executable_suffix(self) -> str:
        """Lo que PyInstaller le agrega al ejecutable de `--onefile`."""

    @abstractmethod
    def executable_names(self, name: str) -> list[str]:
        """Los nombres que puede tener en disco el ejecutable `name`."""

    @abstractmethod
    def script_name(self, name: str) -> str:
        """El lanzador de un SDK (`flutter`, `sdkmanager`): en Windows es `.bat`."""

    @abstractmethod
    def venv_bin(self, venv: Path) -> Path:
        """La carpeta de ejecutables de un venv."""

    @abstractmethod
    def venv_python(self, venv: Path) -> Path:
        """El interprete de un venv. Solo ubica: no comprueba que exista."""

    # --- procesos --------------------------------------------------------

    @abstractmethod
    def wrap_script(self, executable: str) -> list[str]:
        """El argv que corre `executable`, que en Windows puede ser un shim."""

    @abstractmethod
    def spawn_options(self, *, detached: bool) -> dict:
        """Argumentos de `Popen` para un proceso que `kill_group` pueda matar."""

    @abstractmethod
    def run_options(self) -> dict:
        """Argumentos de `subprocess.run` para una consulta corta."""

    @abstractmethod
    def kill_group(self, proc: subprocess.Popen) -> None:
        """Termina el proceso y todo lo que lanzo. Puede lanzar `OSError`."""

    @abstractmethod
    def bind_to_app(self, proc: subprocess.Popen) -> None:
        """Hace que el proceso muera con Consola, aunque Consola se caiga."""

    # --- ssh -------------------------------------------------------------

    @property
    @abstractmethod
    def ssh_multiplex(self) -> bool:
        """Si `ssh` puede reusar una conexion entre invocaciones."""

    @abstractmethod
    def terminal_argv(self, argv: list[str]) -> list[str]:
        """`argv` dentro de una terminal nueva, con TTY real."""

    # --- postgres local --------------------------------------------------

    @abstractmethod
    def pg_tool(self, name: str) -> Path:
        """`psql`, `pg_dump` o `pg_restore` de la instalacion mas nueva."""

    @abstractmethod
    def pg_port(self) -> int:
        """El puerto del Postgres local, leido de su propia configuracion."""

    # --- maquina ---------------------------------------------------------

    @property
    @abstractmethod
    def sdk_key(self) -> str:
        """Como nombran a este sistema las descargas de Android y Flutter."""

    @property
    @abstractmethod
    def android_dir_default(self) -> str: ...

    @property
    @abstractmethod
    def flutter_dir_default(self) -> str: ...

    @property
    @abstractmethod
    def unix_modes(self) -> bool:
        """Si los permisos que trae un zip hay que aplicarlos al descomprimir."""

    @property
    @abstractmethod
    def env_store(self) -> str:
        """Donde persiste el entorno del usuario: `registry` o `profile`
        (`core/userenv.py`)."""

    @property
    @abstractmethod
    def emulator_acceleration(self) -> str:
        """`driver` si se instala, `kvm` si solo se verifica
        (`core/tasks/utils.py::install_android_hypervisor`)."""

    @abstractmethod
    def data_dir(self) -> Path:
        """Carpeta de datos de Consola en esta maquina."""

    @abstractmethod
    def memory(self) -> tuple[int, int] | None:
        """RAM disponible y total, en bytes. `None` si no se pudo leer."""


class WindowsHost(Host):
    PG_ROOT = Path(r'C:\Program Files\PostgreSQL')

    _NO_WINDOW = 0x08000000             # CREATE_NO_WINDOW
    _NEW_PROCESS_GROUP = 0x00000200     # CREATE_NEW_PROCESS_GROUP

    executable_suffix = '.exe'
    # El ControlMaster de Win32-OpenSSH emula sockets Unix con pipes y falla al
    # reusar el socket entre invocaciones.
    ssh_multiplex = False
    sdk_key = 'windows'
    android_dir_default = r'D:\Android'
    flutter_dir_default = r'D:\flutter'
    unix_modes = False
    env_store = 'registry'
    emulator_acceleration = 'driver'

    def __init__(self) -> None:
        self._job = None
        self._job_lock = threading.Lock()

    def executable_names(self, name: str) -> list[str]:
        return [f'{name}.exe', f'{name}.bat', f'{name}.cmd']

    def script_name(self, name: str) -> str:
        return f'{name}.bat'

    def venv_bin(self, venv: Path) -> Path:
        return venv / 'Scripts'

    def venv_python(self, venv: Path) -> Path:
        return self.venv_bin(venv) / 'python.exe'

    def wrap_script(self, executable: str) -> list[str]:
        # `flutter.bat` o `npm.cmd` no son ejecutables reales: solo corren a
        # traves de `cmd.exe /c`.
        if executable.lower().endswith(('.bat', '.cmd')):
            return ['cmd.exe', '/c', executable]
        return [executable]

    def spawn_options(self, *, detached: bool) -> dict:
        flags = self._NO_WINDOW | (self._NEW_PROCESS_GROUP if detached else 0)
        return {'creationflags': flags}

    def run_options(self) -> dict:
        return {'creationflags': self._NO_WINDOW}

    def kill_group(self, proc: subprocess.Popen) -> None:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                       capture_output=True, creationflags=self._NO_WINDOW)

    def bind_to_app(self, proc: subprocess.Popen) -> None:
        """Un Job Object con KILL_ON_JOB_CLOSE: el handle del job lo tiene solo
        este proceso, y cuando muere el sistema cierra el handle y mata lo que
        hay adentro."""
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                     ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        with self._job_lock:
            if self._job is None:
                class _Basic(ctypes.Structure):
                    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                                ('PerJobUserTimeLimit', ctypes.c_int64),
                                ('LimitFlags', wintypes.DWORD),
                                ('MinimumWorkingSetSize', ctypes.c_size_t),
                                ('MaximumWorkingSetSize', ctypes.c_size_t),
                                ('ActiveProcessLimit', wintypes.DWORD),
                                ('Affinity', ctypes.c_size_t),
                                ('PriorityClass', wintypes.DWORD),
                                ('SchedulingClass', wintypes.DWORD)]

                class _Io(ctypes.Structure):
                    _fields_ = [(n, ctypes.c_uint64) for n in (
                        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

                class _Extended(ctypes.Structure):
                    _fields_ = [('BasicLimitInformation', _Basic), ('IoInfo', _Io),
                                ('ProcessMemoryLimit', ctypes.c_size_t),
                                ('JobMemoryLimit', ctypes.c_size_t),
                                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                                ('PeakJobMemoryUsed', ctypes.c_size_t)]

                job = kernel32.CreateJobObjectW(None, None)
                if not job:
                    return
                info = _Extended()
                info.BasicLimitInformation.LimitFlags = 0x2000   # KILL_ON_JOB_CLOSE
                if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info),  # Extended
                                                        ctypes.sizeof(info)):
                    kernel32.CloseHandle(job)
                    return
                self._job = job
            kernel32.AssignProcessToJobObject(self._job, int(proc._handle))

    def terminal_argv(self, argv: list[str]) -> list[str]:
        return ['wt.exe', *argv]

    def pg_tool(self, name: str) -> Path:
        for version_dir in _newest_first(self.PG_ROOT):
            candidate = version_dir / 'bin' / f'{name}.exe'
            if candidate.is_file():
                return candidate
        raise TaskError(f'No se encontro {name}.exe en {self.PG_ROOT}: '
                        'instala PostgreSQL en esta maquina.')

    def pg_port(self) -> int:
        for version_dir in _newest_first(self.PG_ROOT):
            conf = version_dir / 'data' / 'postgresql.conf'
            if conf.is_file() and (port := _port_in(conf)) is not None:
                return port
        return 5432

    def data_dir(self) -> Path:
        base = os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')
        return Path(base) / 'Consola'

    def memory(self) -> tuple[int, int] | None:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]

        status = _MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.ullAvailPhys, status.ullTotalPhys


class PosixHost(Host):
    # Las rutas de Debian y Ubuntu: `postgresql-common` instala cada version
    # en su carpeta y deja un cluster `main` por version (ADR-0048).
    PG_ROOT = Path('/usr/lib/postgresql')
    PG_CONF_ROOT = Path('/etc/postgresql')
    TERMINAL = 'x-terminal-emulator'

    executable_suffix = ''
    ssh_multiplex = True
    android_dir_default = '~/Android/Sdk'
    flutter_dir_default = '~/flutter'
    unix_modes = True
    env_store = 'profile'
    emulator_acceleration = 'kvm'

    @property
    def sdk_key(self) -> str:
        return 'mac' if sys.platform == 'darwin' else 'linux'

    def executable_names(self, name: str) -> list[str]:
        return [name]

    def script_name(self, name: str) -> str:
        return name

    def venv_bin(self, venv: Path) -> Path:
        return venv / 'bin'

    def venv_python(self, venv: Path) -> Path:
        return self.venv_bin(venv) / 'python'

    def wrap_script(self, executable: str) -> list[str]:
        return [executable]

    def spawn_options(self, *, detached: bool) -> dict:
        # Siempre en una sesion propia, no solo lo desacoplado: `kill_group`
        # manda la senal al grupo del proceso, y un hijo que comparte el grupo
        # de Consola se la haria llegar a Consola tambien. Detener una tarea
        # cerraba la aplicacion entera.
        return {'start_new_session': True}

    def run_options(self) -> dict:
        return {}

    def kill_group(self, proc: subprocess.Popen) -> None:
        # Con `start_new_session` el proceso es lider de su grupo: su pid es el
        # del grupo.
        os.killpg(proc.pid, signal.SIGTERM)

    def bind_to_app(self, proc: subprocess.Popen) -> None:
        """Sin equivalente todavia: si Consola se cae de golpe, el proceso
        sigue vivo (docs/arquitectura/30_riesgos_y_pendientes.md). Al cerrarla
        normalmente lo apaga `TabPanel.shutdown()`."""

    def terminal_argv(self, argv: list[str]) -> list[str]:
        # La alternativa de Debian: apunta a la terminal que tenga el escritorio,
        # y la politica de Debian obliga a que acepte `-e programa argumentos...`.
        terminal = shutil.which(self.TERMINAL)
        if not terminal:
            raise TaskError(f'No se encontro {self.TERMINAL}: instala una terminal '
                            '(gnome-terminal, konsole, xterm) o configura la alternativa '
                            f'con update-alternatives --config {self.TERMINAL}.')
        return [terminal, '-e', *argv]

    def pg_tool(self, name: str) -> Path:
        for version_dir in _newest_first(self.PG_ROOT):
            candidate = version_dir / 'bin' / name
            if candidate.is_file():
                return candidate
        raise TaskError(f'No se encontro {name} en {self.PG_ROOT}: '
                        'instala PostgreSQL en esta maquina (apt install postgresql).')

    def pg_port(self) -> int:
        for version_dir in _newest_first(self.PG_CONF_ROOT):
            conf = version_dir / 'main' / 'postgresql.conf'
            if conf.is_file() and (port := _port_in(conf)) is not None:
                return port
        return 5432

    def data_dir(self) -> Path:
        base = os.environ.get('XDG_CACHE_HOME') or (Path.home() / '.cache')
        return Path(base) / 'consola'

    def memory(self) -> tuple[int, int] | None:
        try:
            with open('/proc/meminfo') as f:
                datos = {}
                for linea in f:
                    clave, _, resto = linea.partition(':')
                    if clave in ('MemAvailable', 'MemTotal'):
                        datos[clave] = int(resto.strip().split()[0]) * 1024
            return datos.get('MemAvailable'), datos.get('MemTotal')
        except OSError:
            return None


HOST: Host = WindowsHost() if os.name == 'nt' else PosixHost()
