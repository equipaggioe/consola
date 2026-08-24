from __future__ import annotations
import socket

from .errors import TaskError


def is_free(port: int, *, host: str = '0.0.0.0') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def resolve_port(preferred: int, *, search: bool = True, label: str = 'puerto') -> int:
    """Devuelve `preferred` si esta libre; si no y `search`, el siguiente libre.

    Los scripts guardaban el resultado en el .env para que el proceso siguiente
    lo leyera. Aca el puerto es estado de sesion (PLAN.md 7, caso 4): lo publica
    quien arranca el servicio y lo lee quien arranca despues, sin tocar disco.
    """
    if is_free(preferred):
        return preferred
    if not search:
        raise TaskError(f'El {label} {preferred} esta ocupado.')

    for port in range(preferred + 1, 65536):
        if is_free(port):
            return port
    raise TaskError('No quedan puertos libres.')
