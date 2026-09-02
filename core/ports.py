from __future__ import annotations
import socket
import time
from urllib.parse import urlsplit

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


def is_serving(port: int, *, host: str = '127.0.0.1', timeout: float = 0.4) -> bool:
    """Si algo acepta conexiones en ese puerto **ahora mismo**.

    Distinto de `is_free`, que pregunta si se puede escuchar ahi. Este pregunta
    si alguien ya contesta: un puerto elegido y todavia sin servidor encima da
    `False` en los dos.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_until_serving(port: int, *, host: str = '127.0.0.1', timeout: float = 60.0,
                       cancel=None) -> bool:
    """Espera a que el servidor conteste de verdad. Devuelve si llego a hacerlo.

    Elegir el puerto (`resolve_port`) no es lo mismo que estar sirviendo: entre
    las dos cosas hay un `npm run dev` que tarda dos segundos o un uvicorn que
    tarda diez. Sin esta espera, el navegador de la pestana abriria la URL antes
    de que exista y mostraria un error que no es tal (docs/launchers.md 2.2).

    `cancel` es el `threading.Event` de la tarea: detenerla no debe dejar este
    bucle vivo hasta que se cumpla el timeout.
    """
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if cancel is not None and cancel.is_set():
            return False
        if is_serving(port, host=host):
            return True
        time.sleep(0.25)
    return False


def split_host_port(url: str) -> tuple[str, int]:
    """Host y puerto de una URL, con el puerto por defecto de su esquema.

    `localhost` se traduce a `127.0.0.1` porque el sondeo abre un socket IPv4:
    resolver `localhost` puede dar `::1` primero y un servidor que solo escucha
    en IPv4 se leeria como caido.
    """
    partes = urlsplit(url)
    host = partes.hostname or '127.0.0.1'
    if host in ('localhost', '0.0.0.0', '::'):
        host = '127.0.0.1'
    puerto = partes.port or (443 if partes.scheme == 'https' else 80)
    return host, puerto
