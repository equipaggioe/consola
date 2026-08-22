from __future__ import annotations

import secrets
import sys
from pathlib import Path

"""
Instala y configura coturn (servidor TURN) en el VPS, para que las llamadas
detras de NAT simetrico/CGNAT puedan conectar (D2 de
docs/llamadas_videollamadas.md).

Flujo:
1) Calcula la raiz del repo y carga scripts/.env.
2) Lee VPS_IP, VPS_USER, VPS_KEY_NAME (config SSH) y CF_DOMAIN_NAME (realm).
3) Instala el paquete `coturn` por apt (idempotente). Va primero para fallar
   rapido si el VPS no es alcanzable o no tiene apt/sudo, antes de mutar nada
   local.
4) Genera un `TURN_SECRET` aleatorio si `server/.env` todavia no tiene uno, y lo
   guarda ahi junto con `TURN_URLS` — el mismo archivo que ya sube
   `update_remote.py` en el proximo deploy, asi que este script no toca nada
   remoto que ese flujo no vaya a sincronizar de todos modos.
5) Escribe /etc/turnserver.conf con `use-auth-secret` (credenciales efimeras,
   nunca credenciales estaticas — ver D2) y lo habilita en
   /etc/default/coturn (el paquete de Debian viene deshabilitado por defecto).
6) Reinicia el servicio y muestra su estado.
7) Si ufw esta activo, abre los puertos que coturn necesita. Si no lo esta,
   solo los imprime para que se abran donde corresponda (proveedor del VPS,
   firewall externo, etc).

No toca el servidor de Vettore ni corre migraciones: es aprovisionamiento de
infraestructura, separado a proposito de update_remote.py.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (  # noqa: E402
    find_project_root,
    load_vps_config,
    optional_env,
    print_header,
    run_ssh,
    run_ssh_checked,
    upsert_env_var,
)

# =========================================================
# SETTINGS
# =========================================================

TURN_PORT = 3478
# Rango de puertos de relay UDP. coturn necesita uno por sesion de medios
# activa; 200 puertos alcanza para uso normal sin abrir el rango entero.
RELAY_PORT_MIN = 49160
RELAY_PORT_MAX = 49360


def _generate_secret() -> str:
    return secrets.token_hex(32)


def _load_or_create_turn_secret(server_env_path: Path) -> str:
    existing = None
    if server_env_path.exists():
        for line in server_env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TURN_SECRET="):
                existing = line.split("=", 1)[1].strip()
                break
    if existing:
        print("[INFO] TURN_SECRET ya existia en server/.env, se reusa.")
        return existing

    secret = _generate_secret()
    upsert_env_var(server_env_path, key="TURN_SECRET", value=secret)
    print("[INFO] TURN_SECRET generado y guardado en server/.env.")
    return secret


def _turnserver_conf(*, realm: str, secret: str, external_ip: str) -> str:
    # lt-cred-mech + use-auth-secret: el unico modo compatible con
    # credenciales efimeras derivadas por HMAC (ver
    # app/services/turn_credentials.py). no-cli cierra la consola de
    # administracion remota, que no se usa y no debe quedar expuesta.
    return f"""
listening-port={TURN_PORT}
external-ip={external_ip}
realm={realm}
use-auth-secret
static-auth-secret={secret}
lt-cred-mech
min-port={RELAY_PORT_MIN}
max-port={RELAY_PORT_MAX}
fingerprint
no-cli
no-tlsv1
no-tlsv1_1
# coturn puede repetir como relay hacia rangos privados si no se lo prohibe
# explicitamente; sin esto un cliente malicioso podria usarlo para alcanzar
# la red interna del VPS.
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=100.64.0.0-100.127.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.0.0.0-192.0.0.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=198.18.0.0-198.19.255.255
""".strip()


def main() -> None:
    print_header("Aprovisionando coturn")

    repo_root = find_project_root(Path(__file__).resolve().parent)
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    realm = optional_env("CF_DOMAIN_NAME", vps_ip)

    print("[INFO] Instalando el paquete coturn...")
    run_ssh_checked(
        "export DEBIAN_FRONTEND=noninteractive; "
        "sudo -n /usr/bin/apt-get update; "
        "sudo -n /usr/bin/apt-get -y install coturn",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
    )

    server_env_path = repo_root / "server" / ".env"
    secret = _load_or_create_turn_secret(server_env_path)

    turn_urls = [
        f"turn:{realm}:{TURN_PORT}?transport=udp",
        f"turn:{realm}:{TURN_PORT}?transport=tcp",
    ]
    upsert_env_var(server_env_path, key="TURN_URLS", value=",".join(turn_urls))
    print(f"[INFO] TURN_URLS guardado en server/.env: {turn_urls}")

    conf = _turnserver_conf(realm=realm, secret=secret, external_ip=vps_ip)
    print("[INFO] Escribiendo /etc/turnserver.conf...")
    write_conf_command = f"""
sudo tee /etc/turnserver.conf >/dev/null <<'CONF'
{conf}
CONF
sudo sed -i 's/^#\\?TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn
grep -q '^TURNSERVER_ENABLED=1' /etc/default/coturn || echo 'TURNSERVER_ENABLED=1' | sudo tee -a /etc/default/coturn >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable coturn
sudo systemctl restart coturn
"""
    run_ssh_checked(write_conf_command, identity_file=identity_file, user=vps_user, host=vps_ip)

    status = run_ssh(
        "sudo systemctl is-active coturn",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
    )
    print(f"[INFO] Estado de coturn: {status.stdout.strip() or status.stderr.strip()}")
    if status.returncode != 0:
        journal = run_ssh(
            "sudo journalctl -u coturn -n 100 --no-pager",
            identity_file=identity_file,
            user=vps_user,
            host=vps_ip,
        )
        print(journal.stdout)
        raise SystemExit("[ERROR] coturn no quedo activo. Ver logs arriba.")

    print("[INFO] Revisando ufw...")
    ufw_active = run_ssh(
        "sudo -n ufw status | head -n1 | grep -qi 'Status: active' && echo YES || echo NO",
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
    ).stdout.strip()

    ports_needed = (
        f"{TURN_PORT}/udp, {TURN_PORT}/tcp y el rango de relay "
        f"{RELAY_PORT_MIN}-{RELAY_PORT_MAX}/udp"
    )
    if ufw_active == "YES":
        print(f"[INFO] ufw activo: abriendo {ports_needed}...")
        run_ssh(
            f"sudo -n ufw allow {TURN_PORT}/udp && "
            f"sudo -n ufw allow {TURN_PORT}/tcp && "
            f"sudo -n ufw allow {RELAY_PORT_MIN}:{RELAY_PORT_MAX}/udp",
            identity_file=identity_file,
            user=vps_user,
            host=vps_ip,
        )
    else:
        print(
            f"[AVISO] ufw no esta activo en este VPS. Asegurate de que {ports_needed} "
            "esten abiertos en el firewall que corresponda (proveedor del VPS u otro)."
        )

    print_header("coturn listo")
    print(
        "Falta: redeployar el backend (update_remote.py) para que suba el "
        "server/.env con TURN_SECRET/TURN_URLS nuevos y el servidor empiece a "
        "devolverlos en GET /calls/ice-servers."
    )


if __name__ == "__main__":
    main()
