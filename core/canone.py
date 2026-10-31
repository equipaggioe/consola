from __future__ import annotations
import re
from pathlib import Path

from . import envfile, fields, process
from .envfile import Config
from .errors import TaskError
from .settings import get_setting

"""
Lo que Consola le pasa a los programas de canone (ADR-0059).

canone fija cada programa por su interfaz: `install.py` por sus argumentos,
`credentials.py` por las lineas que lee de stdin, y lo que la maquina tiene que
tener antes de `install.py` (sus paquetes y el swap) lo deja a quien la prepara.
Aca se arma eso desde `config.env` y desde el repo, sin efectos: es lo que se
puede probar sin un VPS.
"""

# Lo que `install.py` da por instalado (despliegue.md de canone, «Maquina»).
BASE_PACKAGES = ('caddy', 'postgresql', 'valkey-server', 'restic', 'sudo', 'python3',
                 'nftables', 'unattended-upgrades', 'systemd-timesyncd', 'ca-certificates')
POSTGIS_PACKAGE = 'postgresql-17-postgis-3'
TURN_PACKAGES = ('coturn',)
LOGS_PACKAGES = ('systemd-journal-remote', 'wireguard-tools')

# Las piezas que `install.py --without` puede dejar fuera, salvo `sweep`: para
# esa no hay una señal en el repo, y la plantilla trae la tarea siempre.
SURFACES = ('web', 'panel', 'landing')
RELEASE = Path('.github') / 'workflows' / 'release.yml'
_DESKTOP = re.compile(r'^  desktop-(linux|windows|macos):', re.M)
_GITHUB = re.compile(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$')


def infra_dir(config: Config) -> Path:
    """`plantilla/infra/` de la copia local de canone (`CANONE_DIR`)."""
    carpeta = Path(config.require('CANONE_DIR')) / 'plantilla' / 'infra'
    if not (carpeta / 'install.py').is_file():
        raise TaskError(f'No hay install.py en {carpeta}: CANONE_DIR tiene que ser la '
                        'carpeta de canone.')
    return carpeta


def origin(root: Path) -> tuple[str, str]:
    """El dueño y el nombre del repo en GitHub, de `git remote get-url origin`.

    El nombre es el `<app>` de canone: nombra la cuenta, la base, las unidades
    y las carpetas del VPS.
    """
    url = process.capture(['git', 'remote', 'get-url', 'origin'], cwd=root)
    encontrado = _GITHUB.search(url.strip())
    if encontrado is None:
        raise TaskError(f'origin no es un repo de GitHub: {url}')
    return encontrado.group(1), encontrado.group(2)


def packages(config: Config) -> list[str]:
    """Los paquetes que la maquina necesita para este repo."""
    paquetes = list(BASE_PACKAGES)
    if 'postgis' in envfile.split_list(config.get('DB_EXTENSIONS')):
        paquetes.append(POSTGIS_PACKAGE)
    if config.flag('TURN'):
        paquetes += TURN_PACKAGES
    if _logs(config):
        paquetes += LOGS_PACKAGES
    return paquetes


def desktops(root: Path) -> list[str]:
    """Cada `desktop-<sistema>` del `release.yml` del repo, o ninguno si no lo tiene."""
    release = root / RELEASE
    if not release.is_file():
        return []
    return _DESKTOP.findall(release.read_text(encoding='utf-8'))


def without(root: Path) -> list[str]:
    """Las piezas que el repo no tiene, por su carpeta en la raiz."""
    return [pieza for pieza in SURFACES if not (root / pieza).is_dir()]


def _logs(config: Config) -> tuple[str, str, str] | None:
    """`--logs`, `--logs-key` y `--logs-ip`: los tres o ninguno (ADR-0100 de canone)."""
    valores = tuple(config.get(k) for k in ('LOGS', 'LOGS_KEY', 'LOGS_IP'))
    if not any(valores):
        return None
    if not all(valores):
        raise TaskError('LOGS, LOGS_KEY y LOGS_IP van los tres juntos o ninguno.')
    return valores


def install_args(root: Path, config: Config, app: str, owner: str,
                 keys: tuple[str, str]) -> list[str]:
    """Los argumentos de `install.py`, sin el programa.

    `keys` son las dos llaves publicas: la de `VPS_KEY_NAME` y la guardada fuera.
    Son las dos `--key` de la cuenta y las dos `--signer` de los releases. En una
    maquina que ya las tiene, `install.py` no agrega nada.
    """
    args = [app, config.require('DOMAIN'), config.require('VALKEY_MEMORY'),
            '--owner', owner, '--admin', config.require('VPS_USER')]
    for llave in keys:
        args += ['--key', llave]
    for llave in keys:
        args += ['--signer', llave]
    if config.flag('PRIVATE'):
        args.append('--private')
    for sistema in desktops(root):
        args += ['--desktop', sistema]
    for pieza in without(root):
        args += ['--without', pieza]
    for funcion in envfile.split_list(config.get('PERMISSIONS_ALLOW')):
        args += ['--allow', funcion]
    for extension in envfile.split_list(config.get('DB_EXTENSIONS')):
        args += ['--extension', extension]
    if config.flag('TURN'):
        args.append('--turn')
        if config.get('TURN_IP'):
            args += ['--turn-ip', config.get('TURN_IP')]
    elif config.get('TURN_IP'):
        raise TaskError('TURN_IP sin TURN: --turn-ip necesita --turn.')
    logs = _logs(config)
    if logs is not None:
        args += ['--logs', logs[0], '--logs-key', logs[1], '--logs-ip', logs[2]]
    return args


def credential_lines(root: Path, config: Config) -> str:
    """Las lineas `campo=valor` que lee `credentials.py`, por la fuente de cada clave (ADR-0063).

    Corta antes de enviar nada si una clave de `config.env` no cae en ninguna
    fuente, o si falta el valor de un campo.
    """
    servidor = root / config.get('SERVER_DIR')
    campos = fields.field_settings(servidor)
    if not campos:
        raise TaskError(f'No hay campos de Settings en {servidor / fields.CONFIG}.')
    conocidas = {s.key for s in campos}
    ajenas = sorted(k for k in envfile.load_config(str(root))
                    if k not in conocidas and get_setting(k) is None)
    if ajenas:
        raise TaskError('Estas claves de config.env no son de Consola ni campos de Settings: '
                        f'{", ".join(ajenas)}. Bórralas antes de cargar las credenciales.')
    pares = [(s.label, s.key) for s in campos]
    pares.append(('restic_password', 'RESTIC_PASSWORD'))
    if config.flag('PRIVATE'):
        pares.append(('github_token', 'GITHUB_TOKEN'))
    faltan = [clave for _, clave in pares if not config.get(clave)]
    if faltan:
        raise TaskError(f'Faltan en config.env: {", ".join(faltan)}.')
    for campo, clave in pares:
        if '\n' in config.get(clave):
            raise TaskError(f'{clave} tiene un salto de linea: credentials.py lee una por linea.')
    return ''.join(f'{campo}={config.get(clave)}\n' for campo, clave in pares)
