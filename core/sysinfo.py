from __future__ import annotations
import ctypes
import os

"""
RAM disponible en la maquina, para el indicador de la barra de estado.

Se pide sola, sin depender de psutil (`requirements.txt` no lo trae): en
Windows alcanza con `GlobalMemoryStatusEx`, en Linux/Mac con `/proc/meminfo`.
"""


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


def _windows() -> tuple[int, int] | None:
    status = _MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullAvailPhys, status.ullTotalPhys


def _posix() -> tuple[int, int] | None:
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


def available_ram() -> tuple[float, float] | None:
    """RAM disponible y total, en GB. `None` si no se pudo consultar (Mac sin
    `/proc/meminfo`, por ejemplo: no vale la pena otra rama por tan poco)."""
    par = _windows() if os.name == 'nt' else _posix()
    if not par or not par[0] or not par[1]:
        return None
    disponible, total = par
    return disponible / (1024 ** 3), total / (1024 ** 3)
