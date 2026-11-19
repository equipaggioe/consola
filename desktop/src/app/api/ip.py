"""The services that tell this machine's public IP."""

from app.api import http

SERVICES = ("https://api.ipify.org", "https://ifconfig.me/ip")


def public() -> str:
    """Return the IP of the first service that answers.

    Raises `OSError` when none answers.
    """
    failures = []
    for service in SERVICES:
        try:
            ip = http.request(service, timeout=10).decode("utf-8").strip()
        except OSError as exc:
            failures.append(f"{service}: {exc}")
            continue
        if ip:
            return ip
        failures.append(f"{service}: empty answer")
    raise OSError("; ".join(failures))
