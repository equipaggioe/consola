from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import sys
from pathlib import Path
import urllib.parse
import urllib.request

"""
Actualiza un registro DNS A en Cloudflare con la IP pública actual.

Flujo:
1) Detecta la IP pública actual.
2) Obtiene zone_id por dominio.
3) Obtiene record_id por nombre (A).
4) Compara IP actual del DNS vs IP detectada.
5) Si cambió, actualiza el registro.
"""


IP_MODE = "detect" # "detect" | "vps" | "static"

FIXED_IP = ""
IP_DETECTION_URL = "https://api.ipify.org"

DNS_TTL = 1
DNS_PROXIED = True


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        print(f"[ERROR] No existe el archivo .env: {env_path}")
        raise SystemExit(1)

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        k = key.strip()
        v = value.strip()
        if not k:
            continue
        os.environ[k] = v


def _get_token_from_env() -> str:
    return (os.getenv("CF_API_TOKEN") or "").strip()


def _public_ip_from_cloudflare_trace(text: str) -> str | None:
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() == "ip":
            ip = v.strip()
            if ip:
                return ip
    return None


def _fetch_public_ip(url: str) -> str:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8", errors="replace").strip()

    if url.rstrip("/").endswith("cdn-cgi/trace"):
        ip = _public_ip_from_cloudflare_trace(text)
        if not ip:
            raise ValueError("No se pudo leer IP desde cloudflare trace")
        ipaddress.ip_address(ip)
        return ip

    ipaddress.ip_address(text)
    return text


def _fetch_public_ip_with_fallback(urls: list[str]) -> str:
    last_error: Exception | None = None
    for url in urls:
        u = (url or "").strip()
        if not u:
            continue
        try:
            return _fetch_public_ip(u)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"No se pudo obtener IP pública. Último error: {last_error}")


def _cloudflare_request_json(
    *,
    method: str,
    url: str,
    token: str,
    body: dict[str, object] | None = None,
) -> dict[str, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    if not payload.get("success", False):
        err = payload.get("errors") or payload
        raise RuntimeError(f"Cloudflare API falló: {err}")
    return payload


def _cloudflare_find_zone_id(*, token: str, domain_name: str) -> str:
    url = f"https://api.cloudflare.com/client/v4/zones?name={urllib.parse.quote(domain_name)}"
    payload = _cloudflare_request_json(method="GET", url=url, token=token)
    results = payload.get("result") or []
    if not results:
        raise RuntimeError(f"No se encontró zona para {domain_name}")
    return results[0]["id"]


def _cloudflare_find_record_id(*, token: str, zone_id: str, record_name: str, record_type: str = "A") -> str:
    url = (
        "https://api.cloudflare.com/client/v4/zones/"
        f"{zone_id}/dns_records?name={urllib.parse.quote(record_name)}&type={urllib.parse.quote(record_type)}"
    )
    payload = _cloudflare_request_json(method="GET", url=url, token=token)
    results = payload.get("result") or []
    if not results:
        raise RuntimeError(f"No se encontró registro {record_type} para {record_name}")
    return results[0]["id"]


def _cloudflare_get_record_ip(*, token: str, zone_id: str, record_id: str) -> str:
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    payload = _cloudflare_request_json(method="GET", url=url, token=token)
    result = payload.get("result") or {}
    ip = (result.get("content") or "").strip()
    ipaddress.ip_address(ip)
    return ip


def _cloudflare_update_record(
    *,
    token: str,
    zone_id: str,
    record_id: str,
    record_name: str,
    ip: str,
    ttl: int,
    proxied: bool,
) -> None:
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
    _cloudflare_request_json(
        method="PUT",
        url=url,
        token=token,
        body={"type": "A", "name": record_name, "content": ip, "ttl": ttl, "proxied": proxied},
    )


async def run() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    _load_env_file(env_path)

    token = _get_token_from_env()
    domain_name = (os.getenv("CF_DOMAIN_NAME") or "").strip()
    record_name = (os.getenv("CF_RECORD_NAME") or "").strip()

    ip_url = IP_DETECTION_URL.strip()
    ttl = DNS_TTL
    proxied = DNS_PROXIED

    if not token:
        print("[ERROR] DDNS Cloudflare: falta CF_API_TOKEN.")
        raise SystemExit(1)
    if not (domain_name and record_name):
        print("[WARN] DDNS Cloudflare: faltan CF_DOMAIN_NAME/CF_RECORD_NAME")
        return

    try:
        mode = (IP_MODE or "").strip().lower()
        if mode not in {"detect", "vps", "fixed"}:
            print("[ERROR] IP_MODE inválida. Usa: detect | vps | fixed")
            raise SystemExit(1)

        if mode == "fixed":
            ip = (FIXED_IP or "").strip()
            if not ip:
                print("[ERROR] IP_MODE=fixed requiere FIXED_IP.")
                raise SystemExit(1)
            ipaddress.ip_address(ip)
            print(f"[INFO] IP configurada manualmente: {ip}")
        elif mode == "vps":
            ip = (os.getenv("VPS_IP") or "").strip()
            if not ip:
                print("[ERROR] IP_MODE=vps requiere VPS_IP en scripts/.env.")
                raise SystemExit(1)
            ipaddress.ip_address(ip)
            print(f"[INFO] IP tomada de VPS_IP: {ip}")
        else:
            if not ip_url:
                print("[ERROR] IP_MODE=detect requiere IP_DETECTION_URL.")
                raise SystemExit(1)
            ip_urls = [ip_url, "https://cloudflare.com/cdn-cgi/trace"]
            ip = await asyncio.to_thread(_fetch_public_ip_with_fallback, ip_urls)
            print(f"[INFO] IP pública detectada: {ip}")

        zone_id = await asyncio.to_thread(_cloudflare_find_zone_id, token=token, domain_name=domain_name)
        print(f"[INFO] ID de la zona: {zone_id}")

        record_id = await asyncio.to_thread(_cloudflare_find_record_id, token=token, zone_id=zone_id, record_name=record_name)
        print(f"[INFO] ID del registro DNS: {record_id}")

        try:
            current_dns_ip = await asyncio.to_thread(_cloudflare_get_record_ip, token=token, zone_id=zone_id, record_id=record_id)
            print(f"[INFO] IP actual en DNS: {current_dns_ip}")
        except Exception as exc:
            current_dns_ip = None
            print(f"[WARN] No se pudo leer DNS actual ({record_name}): {exc}")

        if current_dns_ip == ip:
            print("[OK] IP sin cambios, no se requiere actualización")
            return

        await asyncio.to_thread(
            _cloudflare_update_record,
            token=token,
            zone_id=zone_id,
            record_id=record_id,
            record_name=record_name,
            ip=ip,
            ttl=ttl,
            proxied=proxied,
        )
        print(f"[OK] DNS actualizado: {record_name} → {ip}")
    except Exception as exc:
        print(f"[ERROR] Error DDNS: {exc}")


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as exc:
        print(f"\n[ERROR] Error fatal: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
