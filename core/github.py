from __future__ import annotations
import json
import urllib.error
import urllib.request

from .errors import TaskError

API = 'https://api.github.com'


def request(method: str, path: str, *, token: str, body: dict | None = None) -> tuple[int, object]:
    """Llamada cruda a la API de GitHub. Devuelve (status, payload) sin levantar.

    Los errores HTTP se devuelven como estado, no como excepcion: casi todos los
    llamantes distinguen 404 (no existe, seguir) de 401 (token malo, frenar).
    """
    url = path if path.startswith('http') else f'{API}{path}'
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    if data is not None:
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except json.JSONDecodeError:
            return exc.code, raw
    except urllib.error.URLError as exc:
        raise TaskError(f'No se pudo alcanzar la API de GitHub: {exc.reason}') from exc


def _checked(method: str, path: str, *, token: str, body: dict | None = None) -> object:
    status, payload = request(method, path, token=token, body=body)
    if status >= 400:
        detalle = payload.get('message') if isinstance(payload, dict) else payload
        raise TaskError(f'GitHub respondio {status}: {detalle}')
    return payload


def list_keys(token: str) -> list[dict]:
    payload = _checked('GET', '/user/keys', token=token)
    return payload if isinstance(payload, list) else []


def find_key(token: str, title: str) -> dict | None:
    """Busca una llave por titulo: es el identificador que maneja el usuario."""
    for key in list_keys(token):
        if key.get('title') == title:
            return key
    return None


def register_key(ctx, token: str, *, title: str, public_key: str) -> dict:
    """Sube la llave publica del VPS a la cuenta de GitHub.

    Idempotente: si ya hay una con ese titulo y la misma llave, no hace nada;
    si el contenido cambio, reemplaza la vieja en vez de dejar dos homonimas.
    """
    existing = find_key(token, title)
    if existing:
        if existing.get('key', '').split()[:2] == public_key.split()[:2]:
            ctx.ok(f'La llave "{title}" ya estaba registrada en GitHub.')
            return existing
        ctx.warn(f'La llave "{title}" existe con otro contenido: se reemplaza.')
        _checked('DELETE', f'/user/keys/{existing["id"]}', token=token)

    created = _checked('POST', '/user/keys', token=token,
                       body={'title': title, 'key': public_key})
    ctx.ok(f'Llave "{title}" registrada en GitHub.')
    return created if isinstance(created, dict) else {}


def revoke_key(ctx, token: str, *, title: str) -> bool:
    """Borra la llave por titulo. Devuelve False si no habia nada que borrar."""
    existing = find_key(token, title)
    if not existing:
        ctx.info(f'No hay ninguna llave "{title}" en GitHub; no se revoca nada.')
        return False
    _checked('DELETE', f'/user/keys/{existing["id"]}', token=token)
    ctx.ok(f'Llave "{title}" revocada de GitHub.')
    return True
