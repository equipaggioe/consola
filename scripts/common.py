from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

"""
Funciones compartidas por los scripts de scripts/.

1) find_project_root(): busca .git subiendo desde el archivo que llama, para ubicar la raíz del repo.
2) load_env_file(): carga variables desde un archivo .env a os.environ.
   - Si una variable ya existe en el entorno con un valor distinto, pregunta por consola
     cuál usar (por defecto, se mantiene el valor del entorno).
   - peek_env_value(): lee un solo valor de un .env sin tocar os.environ (mismo parser,
     misma distinción de mayúsculas/minúsculas que load_env_file).
3) require_env(): lee y valida una variable de entorno requerida.
4) require_port_env(): lee y valida una variable de entorno entera de puerto (1-65535).
5) require_bool_env(): lee y valida una variable de entorno booleana (true/false, 1/0, yes/no, on/off).
6) optional_env(): lee una variable de entorno opcional, con default si falta o está vacía.
7) repo_name_from_git_url(): extrae el nombre del repo desde una URL de git.
8) require_identity_file(): resuelve y valida la llave privada local en ~/.ssh/<key_name>.
9) load_vps_ip_user(): carga scripts/.env y resuelve VPS_IP y VPS_USER (default: nombre del repo
   si no está definida), sin exigir la llave privada local.
   load_vps_config(): igual que load_vps_ip_user(), pero además resuelve y valida la llave
   privada local (VPS_KEY_NAME).
10) ssh_argv(): arma el argv de "ssh" hacia el VPS (usado por run_ssh() y por callers que necesitan
    stream/interactivo en vez de capturar la salida).
11) run_ssh() / run_ssh_checked(): ejecutan un comando remoto por SSH y devuelven el resultado.
12) scp_transfer(): corre un scp de bajo nivel (subida o bajada) entre un path local y uno remoto.
    copy_to_vps(): sube un archivo o directorio local al VPS preservando la ruta relativa del repo
    (usa scp_transfer() por dentro; opcionalmente crea el directorio remoto y aplica chmod).
13) is_port_free() / pick_port(): validan disponibilidad de puertos locales.
14) bump_semver(): aplica un incremento SemVer (major/minor/patch/none).
15) reversible_write(): context manager que revierte un archivo a su contenido original si falla el bloque.
16) github_api_request(): llama a la API de GitHub con el token de autorización.
17) resolve_flutter_cmd(): ubica el ejecutable de Flutter (PATH o FLUTTER_BIN).
18) detect_os() / print_header() / run_logged() / sdk_root_from_env(): utilidades genéricas de shell.
19) resolve_android_tool(): ubica un ejecutable del Android SDK (ANDROID_SDK_ROOT/ANDROID_HOME o PATH).
20) venv_python(): ubica el Python de un venv (Windows/Linux) y opcionalmente reinicia el proceso con él.
21) upsert_env_var(): reemplaza o agrega una línea KEY=value en un archivo .env.
22) resolve_flet_cmd(): ubica el ejecutable de Flet (PATH o FLET_BIN).
23) detect_app_project_type(): detecta si un directorio de proyecto es Flutter (pubspec.yaml) o Flet
    (pyproject.toml con 'flet' como dependencia).
24) run_flutter_devices_machine() / pick_android_emulator_id(): detectan el emulador Android activo
    vía `flutter devices --machine` (usado por run_flutter.py y run_flet.py).
25) windows_postgres_port(): lee el puerto de Postgres local desde postgresql.conf (Windows).
26) remote_postgres_port(): consulta por SSH el puerto real de Postgres en el VPS (SHOW port).
27) start_ssh_tunnel(): abre un túnel SSH -L en background (subprocess.Popen, no bloquea).
28) resolve_database_url(): decide BD local vs BD remota del VPS según RUN_REMOTE (scripts/.env;
   misma variable que usa maybe_dispatch_remote(), ver 29).
   Si RUN_REMOTE=true, abre un túnel SSH y devuelve la URL apuntando al túnel (avisando
   claramente que se está usando la BD remota). Si ya hay DATABASE_URL en el entorno (por
   ejemplo, un script padre que ya lo resolvió y llama a otro script como subproceso), lo
   reusa tal cual y no abre un túnel nuevo.
29) maybe_dispatch_remote(): si RUN_REMOTE=true (scripts/.env), reenvía la ejecución de este
   mismo script al VPS por SSH (con streaming en vivo de stdout/stderr) y termina el proceso
   local con el mismo exit code. El caller declara en env_keys qué variables de scripts/.env
   necesita su rama remota; solo esas se reenvían inline (nunca se copia el .env completo ni
   se escribe nada a disco en el VPS). Usa un centinela de entorno (no persistido en ningún
   .env) para no volver a despacharse si el .env se copió al VPS y RUN_REMOTE también quedó
   true ahí; del lado remoto, ese mismo centinela dispara un aviso de que está corriendo en
   el VPS y qué variables recibió.
30) force_env_vars(): fuerza valores en el entorno del proceso actual (no toca el .env en
    disco). Úsalo antes de lanzar un script hijo por subprocess (sin pasar env=, hereda
    os.environ) cuando ese hijo decide su comportamiento según una variable de scripts/.env
    (ej. RUN_REMOTE) y quieres garantizar el valor sin importar lo que tenga el .env local.
"""


def find_project_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("No se encontró la raíz del proyecto (.git no encontrado).")


def _iter_env_pairs(env_path: Path) -> Iterator[tuple[str, str]]:
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        k = key.strip()
        v = value.strip()
        if not k:
            continue

        yield k, v


def load_env_file(env_path: Path) -> None:
    if not env_path.is_file():
        if os.environ.get(_REMOTE_DISPATCH_SENTINEL) == "1":
            return
        raise FileNotFoundError(f"No existe el archivo .env: {env_path}")

    for k, v in _iter_env_pairs(env_path):
        if k in os.environ and os.environ[k] != v:
            respuesta = input(
                f"[?] {k} ya existe en el entorno ({os.environ[k]!r}). "
                f"Usar el valor de .env ({v!r}) en vez del valor del entorno? [s/N]: "
            ).strip().lower()
            if respuesta in ("s", "si", "sí", "y", "yes"):
                os.environ[k] = v
            continue

        if k not in os.environ:
            os.environ[k] = v


def peek_env_value(env_path: Path, key: str) -> str | None:
    if not env_path.is_file():
        return None
    for k, v in _iter_env_pairs(env_path):
        if k == key:
            return v
    return None


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        print(f"[ERROR] Falta variable de entorno: {name}")
        raise SystemExit(1)
    return value.strip()


def require_port_env(name: str) -> int:
    raw = require_env(name)
    try:
        value = int(raw)
    except ValueError as exc:
        print(f"[ERROR] {name} no es numérico: {raw}")
        raise SystemExit(1) from exc
    if value < 1 or value > 65535:
        print(f"[ERROR] {name} fuera de rango: {value}")
        raise SystemExit(1)
    return value


def optional_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def require_bool_env(name: str) -> bool:
    raw = require_env(name).lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    print(f"[ERROR] {name} inválido (usa true/false, 1/0, yes/no, on/off): {raw}")
    raise SystemExit(1)


def force_env_vars(overrides: dict[str, str]) -> None:
    """Fuerza estos valores en el entorno del proceso actual (no modifica scripts/.env).

    Los scripts hijos lanzados después con subprocess (sin pasar env=) heredan os.environ,
    así que van a ver estos valores. Si más adelante alguien llama a load_env_file() con un
    .env que trae un valor distinto para la misma clave, va a preguntar por consola cuál usar
    (por defecto, se mantiene el valor forzado acá).
    """

    for key, value in overrides.items():
        print(f"[INFO] Forzando {key}={value} para esta corrida (no se modifica scripts/.env).")
        os.environ[key] = value


def repo_name_from_git_url(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail.removesuffix(".git")


def local_identity_file_path(key_name: str) -> Path:
    return Path.home() / ".ssh" / key_name


def require_identity_file(key_name: str) -> Path:
    identity_file = local_identity_file_path(key_name)
    if not identity_file.is_file():
        print(f"[ERROR] No existe la llave privada local: {identity_file}")
        raise SystemExit(1)
    return identity_file


def load_vps_ip_user(repo_root: Path) -> tuple[str, str]:
    load_env_file(repo_root / "scripts" / ".env")
    vps_ip = require_env("VPS_IP")
    vps_user = optional_env("VPS_USER", repo_root.name)
    return vps_ip, vps_user


def load_vps_config(repo_root: Path) -> tuple[str, str, Path]:
    vps_ip, vps_user = load_vps_ip_user(repo_root)
    identity_file = require_identity_file(require_env("VPS_KEY_NAME"))
    return vps_ip, vps_user, identity_file


def _ssh_control_path(*, identity_file: Path, user: str, host: str) -> Path:
    """Ruta corta y estable para el socket de control de una conexión SSH multiplexada.

    Se hashea user@host+identity_file para evitar el límite de longitud de ControlPath
    (~104 chars en muchos sistemas) y para no colisionar entre distintos VPS/llaves.
    """
    key = f"{user}@{host}:{identity_file}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    control_dir = Path(tempfile.gettempdir()) / "vettore_ssh_mux"
    control_dir.mkdir(parents=True, exist_ok=True)
    return control_dir / f"{digest}.sock"


def multiplex_ssh_args(*, identity_file: Path, user: str, host: str) -> list[str]:
    """Flags de multiplexación SSH: reusa una única conexión TCP para todos los comandos
    ssh/scp hacia el mismo user@host+identity_file en una ventana corta de tiempo.

    Evita que ráfagas de múltiples ssh/scp seguidos (p.ej. subir varios archivos) abran
    una conexión nueva por cada uno, lo que puede disparar rate-limiting/fail2ban en el
    VPS y colgar el cliente indefinidamente (no hay timeout en subprocess.run acá).

    Deshabilitado en Windows: el ControlMaster de Win32-OpenSSH (pipes con nombre
    emulando sockets Unix) es poco confiable y falla con errores como
    "getsockname failed: Not a socket" al reusar el socket de control entre
    invocaciones separadas.
    """
    if os.name == "nt":
        return []

    control_path = _ssh_control_path(identity_file=identity_file, user=user, host=host)
    return [
        "-o", "ControlMaster=auto",
        "-o", f"ControlPath={control_path}",
        "-o", "ControlPersist=60s",
    ]


CONNECT_TIMEOUT_ARGS = ["-o", "ConnectTimeout=15"]


def ssh_argv(
    command: str,
    *,
    identity_file: Path,
    user: str,
    host: str,
    extra_ssh_args: list[str] | None = None,
) -> list[str]:
    mux = multiplex_ssh_args(identity_file=identity_file, user=user, host=host)
    return [
        "ssh", *CONNECT_TIMEOUT_ARGS, *mux, *(extra_ssh_args or []),
        "-i", str(identity_file), f"{user}@{host}", command,
    ]


def run_ssh(
    command: str,
    *,
    identity_file: Path,
    user: str,
    host: str,
    timeout: float | None = None,
    extra_ssh_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ssh_argv(command, identity_file=identity_file, user=user, host=host, extra_ssh_args=extra_ssh_args)
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Comando SSH excedió timeout ({timeout}s): {command}") from exc


def run_ssh_checked(
    command: str,
    *,
    identity_file: Path,
    user: str,
    host: str,
    timeout: float | None = None,
    extra_ssh_args: list[str] | None = None,
) -> str:
    result = run_ssh(
        command,
        identity_file=identity_file,
        user=user,
        host=host,
        timeout=timeout,
        extra_ssh_args=extra_ssh_args,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Comando remoto falló: {result.stderr.strip()}")
    return result.stdout.strip()


def systemd_service_exists(
    repo_name: str,
    run: Callable[[str], subprocess.CompletedProcess[str]],
) -> bool:
    result = run(f'[ -f "/etc/systemd/system/{repo_name}.service" ] && echo YES')
    return "YES" in result.stdout


def restart_systemd_service(
    repo_name: str,
    run: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    """Reinicia un servicio systemd (por nombre de repo) usando el runner dado.

    `run` recibe el comando shell y devuelve un CompletedProcess (local o vía SSH,
    según lo que pase el llamante); acá solo vive la lógica común de chequear
    existencia, reiniciar e imprimir resultado, sin acoplarse a un mecanismo de
    ejecución en particular.
    """
    if not systemd_service_exists(repo_name, run):
        print(
            f"[WARN] El servicio {repo_name} todavía no existe (falta correr "
            "install_systemd_service.py); no se reinicia nada."
        )
        return

    print("Reiniciando servicio...")
    result = run(f"sudo -n systemctl restart {repo_name}")
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
    if result.returncode != 0:
        raise SystemExit(f"[ERROR] Falló el reinicio del servicio (exit {result.returncode}).")
    print(f"[OK] Servicio {repo_name} reiniciado.")


def scp_transfer(
    local_path: Path,
    remote_path: str,
    *,
    vps_ip: str,
    vps_user: str,
    identity_file: Path,
    direction: str = "upload",
    is_dir: bool = False,
    extra_ssh_args: list[str] | None = None,
) -> None:
    if direction not in ("upload", "download"):
        raise ValueError(f"direction inválido: {direction!r}. Usa 'upload' | 'download'")

    if direction == "upload":
        if is_dir:
            if not local_path.is_dir():
                raise FileNotFoundError(f"No existe el directorio local: {local_path}")
        elif not local_path.is_file():
            raise FileNotFoundError(f"No existe el archivo local: {local_path}")

    extra = extra_ssh_args or []
    mux = multiplex_ssh_args(identity_file=identity_file, user=vps_user, host=vps_ip)
    target = f"{vps_user}@{vps_ip}"
    remote_spec = f"{target}:{remote_path}"

    cmd = ["scp", *(["-r"] if is_dir else []), *CONNECT_TIMEOUT_ARGS, *mux, *extra, "-i", str(identity_file)]
    if direction == "upload":
        cmd.extend([str(local_path), remote_spec])
    else:
        cmd.extend([remote_spec, str(local_path)])

    subprocess.run(cmd, check=True)


def copy_to_vps(
    local_path: Path,
    *,
    remote_rel_path: str,
    remote_dir_base: str,
    git_repo_url: str,
    vps_ip: str,
    vps_user: str,
    identity_file: Path,
    is_dir: bool = False,
    extra_ssh_args: list[str] | None = None,
    chmod_after: str | None = None,
    ensure_remote_dir: bool = True,
) -> str:
    """Sube local_path al VPS. ensure_remote_dir=False salta el 'mkdir -p' remoto (útil
    cuando el caller ya creó todos los directorios de antemano en una sola conexión, para
    subir varios archivos sin abrir una conexión ssh extra por cada uno)."""
    if is_dir:
        if not local_path.is_dir():
            raise FileNotFoundError(f"No existe el directorio local: {local_path}")
    elif not local_path.is_file():
        raise FileNotFoundError(f"No existe el archivo local: {local_path}")

    repo_name = repo_name_from_git_url(git_repo_url)
    remote_repo_path = f"{remote_dir_base}/{repo_name}"
    remote_rel_posix = Path(remote_rel_path).as_posix()
    remote_full_path = f"{remote_repo_path}/{remote_rel_posix}"
    remote_parent = f"{remote_repo_path}/{Path(remote_rel_posix).parent.as_posix()}"

    extra = extra_ssh_args or []
    mux = multiplex_ssh_args(identity_file=identity_file, user=vps_user, host=vps_ip)
    target = f"{vps_user}@{vps_ip}"

    if ensure_remote_dir:
        subprocess.run(
            ["ssh", *CONNECT_TIMEOUT_ARGS, *mux, *extra, "-i", str(identity_file), target,
             f'mkdir -p "{remote_parent}"'],
            check=True,
        )

    scp_transfer(
        local_path,
        remote_parent if is_dir else remote_full_path,
        vps_ip=vps_ip,
        vps_user=vps_user,
        identity_file=identity_file,
        direction="upload",
        is_dir=is_dir,
        extra_ssh_args=extra_ssh_args,
    )

    if chmod_after is not None:
        subprocess.run(
            ["ssh", *CONNECT_TIMEOUT_ARGS, *mux, *extra, "-i", str(identity_file), target,
             f'chmod {chmod_after} "{remote_full_path}"'],
            check=True,
        )

    return remote_full_path


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
        return True


def pick_port(*, preferred_port: int, search_if_busy: bool, port_name: str = "PREFERRED_PORT") -> int:
    if is_port_free(preferred_port):
        return preferred_port

    if not search_if_busy:
        print(f"[ERROR] Puerto en uso: {port_name}={preferred_port}")
        raise SystemExit(1)

    for port in range(preferred_port + 1, 65536):
        if is_port_free(port):
            return port

    print("[ERROR] No se encontró ningún puerto disponible.")
    raise SystemExit(1)


def bump_semver(major: int, minor: int, patch: int, *, mode: str) -> tuple[int, int, int]:
    mode = mode.strip()
    if mode == "none":
        return major, minor, patch
    if mode == "major":
        return major + 1, 0, 0
    if mode == "minor":
        return major, minor + 1, 0
    if mode == "patch":
        return major, minor, patch + 1
    raise ValueError(f"VERSION_BUMP_MODE inválido: {mode!r}. Usa: major | minor | patch | none")


@contextmanager
def reversible_write(path: Path) -> Iterator[None]:
    original = path.read_text(encoding="utf-8")
    try:
        yield
    except BaseException:
        path.write_text(original, encoding="utf-8")
        raise


def github_api_request(
    method: str,
    url: str,
    *,
    token: str,
    body: dict[str, object] | None = None,
) -> tuple[int, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            payload = json.loads(raw.decode("utf-8")) if raw else None
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def upsert_env_var(env_path: Path, *, key: str, value: str) -> str:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{key}="
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{key}={value}")
    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return "updated" if replaced else "added"


def venv_python(venv_dir: Path, *, label: str = "venv", restart: bool = False) -> Path:
    subdir = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    target_python = (venv_dir / subdir[0] / subdir[1]).resolve()
    if not target_python.exists():
        print(f"[ERROR] No existe el Python del {label}: {target_python}")
        raise SystemExit(1)

    if restart:
        current_python = Path(sys.executable).resolve()
        if os.path.normcase(str(current_python)) != os.path.normcase(str(target_python)):
            print(f"[INFO] Reiniciando con el Python del {label}: {target_python}")
            os.execv(str(target_python), [str(target_python), *sys.argv])

    return target_python


def detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    print(f"[ERROR] Sistema operativo no soportado: {sys.platform}")
    raise SystemExit(1)


def sdk_root_from_env() -> str | None:
    for var in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return None


def resolve_android_tool(*, sdk_subpath: tuple[str, ...], windows_name: str, other_name: str) -> str:
    import shutil

    os_key = detect_os()
    exe_name = windows_name if os_key == "windows" else other_name
    sdk_root = sdk_root_from_env()

    if sdk_root:
        candidate = os.path.join(sdk_root, *sdk_subpath, exe_name)
        if os.path.exists(candidate):
            return candidate
        print(f"[ERROR] ANDROID_SDK_ROOT/ANDROID_HOME está definido pero no se encontró '{exe_name}' en la ruta esperada.")
        print(f"[ERROR] SDK root: {sdk_root}")
        print(f"[ERROR] Esperado: {candidate}")
        raise SystemExit(1)

    found = shutil.which(exe_name)
    if found:
        return found

    print(f"[ERROR] No se pudo localizar '{exe_name}'.")
    print("[ERROR] Define ANDROID_SDK_ROOT o ANDROID_HOME, o agrega la herramienta al PATH.")
    raise SystemExit(1)


def print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def resolve_flutter_cmd() -> list[str]:
    import shutil

    configured = os.getenv("FLUTTER_BIN")
    if configured is not None and configured.strip():
        p = Path(configured.strip()).expanduser()
        if p.is_file():
            return [str(p)]
        raise FileNotFoundError(f"FLUTTER_BIN apunta a un archivo que no existe: {p}")

    candidates = ["flutter", "flutter.bat", "flutter.cmd", "flutter.exe"]
    resolved = ""
    for c in candidates:
        found = shutil.which(c)
        if found:
            resolved = found
            break

    if not resolved:
        raise FileNotFoundError("No se encontró flutter en PATH y no está definido FLUTTER_BIN.")

    lower = resolved.lower()
    if os.name == "nt" and (lower.endswith(".bat") or lower.endswith(".cmd")):
        return ["cmd.exe", "/c", resolved]
    return [resolved]


def run_flutter_devices_machine(*, cwd: Path, flutter_cmd: list[str]) -> list[dict]:
    """Corre `flutter devices --machine` y devuelve la lista de dispositivos (JSON parseado).

    Compartido por run_flutter.py y run_flet.py: Flet no tiene su propio mecanismo de
    detección de dispositivos (el comando `flet devices` internamente llama a
    `flutter devices` sin --machine y parsea texto para mostrar una tabla), así que para
    autodetección confiable ambos scripts usan directamente el Flutter subyacente.
    """
    import json

    try:
        out = subprocess.check_output(
            [*flutter_cmd, "devices", "--machine"],
            cwd=str(cwd),
            stderr=subprocess.STDOUT,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print("[ERROR] Falló `flutter devices --machine`.")
        print(exc.output)
        raise SystemExit(exc.returncode or 1) from exc

    try:
        decoded = json.loads(out)
    except json.JSONDecodeError:
        print("[ERROR] Respuesta inválida de `flutter devices --machine`.")
        print(out)
        raise SystemExit(1)

    if not isinstance(decoded, list):
        print("[ERROR] Respuesta inesperada de `flutter devices --machine` (se esperaba lista).")
        raise SystemExit(1)

    return [d for d in decoded if isinstance(d, dict)]


def windows_postgres_port(*, version: str = "17") -> str:
    conf_path = Path(r"C:\Program Files\PostgreSQL") / version / "data" / "postgresql.conf"
    if not conf_path.is_file():
        raise FileNotFoundError(f"No se encontró postgresql.conf en la ruta esperada: {conf_path}")

    for raw_line in conf_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"port\s*=\s*'?(\d+)'?", line)
        if m:
            return m.group(1)

    raise RuntimeError(f"No se pudo determinar 'port' en {conf_path}.")


def remote_postgres_port(*, identity_file: Path, user: str, host: str) -> str:
    port = run_ssh_checked(
        'sudo -n -u postgres psql -tAc "SHOW port;"',
        identity_file=identity_file,
        user=user,
        host=host,
    ).strip()
    if not port or not port.isdigit():
        raise RuntimeError(f"No se pudo obtener el puerto de Postgres remoto (respuesta: {port!r}).")
    return port


def start_ssh_tunnel(
    *,
    identity_file: Path,
    user: str,
    host: str,
    local_port: int,
    remote_port: int,
    local_host: str = "127.0.0.1",
    remote_host: str = "127.0.0.1",
) -> subprocess.Popen:
    forward = f"{local_host}:{local_port}:{remote_host}:{remote_port}"
    mux = multiplex_ssh_args(identity_file=identity_file, user=user, host=host)
    cmd = ["ssh", *mux, "-i", str(identity_file), "-N", "-L", forward, f"{user}@{host}"]
    return subprocess.Popen(cmd)


def _local_database_url(*, db_user: str, db_password: str, db_name: str) -> str | None:
    try:
        port = windows_postgres_port()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[WARN] No se pudo leer el puerto de Postgres local: {exc}")
        return None
    return f"postgresql://{db_user}:{db_password}@127.0.0.1:{port}/{db_name}"


def _remote_database_url(
    *, repo_root: Path, db_user: str, db_password: str, db_name: str
) -> tuple[str, subprocess.Popen]:
    vps_ip, vps_user, identity_file = load_vps_config(repo_root)

    remote_port = int(remote_postgres_port(identity_file=identity_file, user=vps_user, host=vps_ip))
    local_port = pick_port(preferred_port=remote_port, search_if_busy=True, port_name="DB_TUNNEL_PORT")

    print(f"[INFO] Abriendo túnel SSH hacia el VPS: 127.0.0.1:{local_port} -> {vps_ip}:{remote_port}")
    tunnel = start_ssh_tunnel(
        identity_file=identity_file,
        user=vps_user,
        host=vps_ip,
        local_port=local_port,
        remote_port=remote_port,
    )

    url = f"postgresql://{db_user}:{db_password}@127.0.0.1:{local_port}/{db_name}"
    return url, tunnel


def resolve_database_url(repo_root: Path) -> tuple[str, subprocess.Popen | None]:
    already_resolved = os.environ.get("DATABASE_URL")
    if already_resolved:
        return already_resolved, None

    run_remote = require_bool_env("RUN_REMOTE")
    db_user = optional_env("VPS_USER", repo_root.name)
    db_password = require_env("DB_PASSWORD")
    db_name = optional_env("DB_NAME", f"{db_user}_db")

    if not run_remote:
        database_url = _local_database_url(db_user=db_user, db_password=db_password, db_name=db_name)
        if database_url is not None:
            print("[INFO] Base de datos: LOCAL")
            return database_url, None

        print("=" * 80)
        print("[WARN] RUN_REMOTE=false pero no se encontró Postgres local instalado.")
        print("[WARN] Fallback automático: usando la BD remota del VPS (túnel SSH).")
        print("=" * 80)

    database_url, tunnel = _remote_database_url(
        repo_root=repo_root, db_user=db_user, db_password=db_password, db_name=db_name
    )
    print("=" * 80)
    print("[INFO] BASE DE DATOS REMOTA (VPS, vía túnel SSH): los cambios afectan al VPS.")
    print("=" * 80)
    return database_url, tunnel


def pick_android_emulator_id(devices: list[dict]) -> str:
    for d in devices:
        device_id = str(d.get("id") or "").strip()
        if not device_id:
            continue
        target_platform = str(d.get("targetPlatform") or "").strip().lower()
        is_emulator = bool(d.get("emulator"))
        if target_platform.startswith("android") and (is_emulator or device_id.startswith("emulator-")):
            return device_id
    return ""


def resolve_flet_cmd() -> list[str]:
    import shutil

    configured = os.getenv("FLET_BIN")
    if configured is not None and configured.strip():
        p = Path(configured.strip()).expanduser()
        if p.is_file():
            return [str(p)]
        raise FileNotFoundError(f"FLET_BIN apunta a un archivo que no existe: {p}")

    candidates = ["flet", "flet.bat", "flet.cmd", "flet.exe"]
    resolved = ""
    for c in candidates:
        found = shutil.which(c)
        if found:
            resolved = found
            break

    if not resolved:
        raise FileNotFoundError("No se encontró flet en PATH y no está definido FLET_BIN.")

    lower = resolved.lower()
    if os.name == "nt" and (lower.endswith(".bat") or lower.endswith(".cmd")):
        return ["cmd.exe", "/c", resolved]
    return [resolved]


def detect_app_project_type(project_dir: Path) -> str:
    """Detecta si project_dir es un proyecto Flutter o Flet.

    Flutter: tiene pubspec.yaml.
    Flet: tiene pyproject.toml con 'flet' listado como dependencia.
    """
    pubspec = project_dir / "pubspec.yaml"
    pyproject = project_dir / "pyproject.toml"

    if pubspec.is_file() and pyproject.is_file():
        raise RuntimeError(
            f"Se encontraron pubspec.yaml y pyproject.toml en {project_dir}; "
            "no se puede detectar el tipo de proyecto automáticamente. Define PROJECT_TYPE."
        )

    if pubspec.is_file():
        return "flutter"

    if pyproject.is_file():
        content = pyproject.read_text(encoding="utf-8", errors="replace").lower()
        if "flet" not in content:
            raise RuntimeError(
                f"Se encontró pyproject.toml en {project_dir} pero no parece ser un proyecto Flet "
                "(no se encontró 'flet' como dependencia)."
            )
        return "flet"

    raise RuntimeError(
        f"No se encontró pubspec.yaml ni pyproject.toml en {project_dir}; "
        "no se puede detectar el tipo de proyecto."
    )


def run_logged(
    cmd: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    print(f"\n>>> {' '.join(cmd)}\n")
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture_output,
        input=input_text,
    )


_REMOTE_DISPATCH_SENTINEL = "REMOTE_DISPATCH_ACTIVE"


def maybe_dispatch_remote(script_path: Path, argv: list[str], env_keys: set[str]) -> None:
    """Si RUN_REMOTE=true, reenvía la ejecución de script_path al VPS por SSH.

    env_keys: nombres de variables de scripts/.env que el propio script (rama remota/Linux)
    necesita; se declaran en el script llamante, no acá, para que vivan al lado del código
    que las usa. Se reenvían solo esas, nunca el .env completo.
    """
    if os.environ.get(_REMOTE_DISPATCH_SENTINEL) == "1":
        received = sorted(k for k in env_keys if k in os.environ)
        print(
            f"[INFO] Corriendo en el VPS (despachado por RUN_REMOTE). "
            f"Variables recibidas: {', '.join(received) if received else '(ninguna)'}"
        )
        return

    resolved_script = script_path.resolve()
    repo_root = find_project_root(resolved_script)
    env_path = repo_root / "scripts" / ".env"
    load_env_file(env_path)

    if not require_bool_env("RUN_REMOTE"):
        return

    vps_ip, vps_user, identity_file = load_vps_config(repo_root)
    vps_deploy_dir = require_env("VPS_DEPLOY_DIR")
    git_repo_url = require_env("GIT_REPO_URL")
    vps_python = require_env("VPS_PYTHON")

    repo_name = repo_name_from_git_url(git_repo_url)
    script_rel = resolved_script.relative_to(repo_root).as_posix()
    remote_repo_path = f"{vps_deploy_dir.rstrip('/')}/{repo_name}"

    forwarded_env = {k: v for k, v in _iter_env_pairs(env_path) if k in env_keys}
    env_assignments = " ".join(f"{k}={shlex.quote(v)}" for k, v in forwarded_env.items())

    args_str = ""
    if argv:
        args_str = " " + " ".join(shlex.quote(a) for a in argv)

    remote_cmd = (
        f'cd {shlex.quote(remote_repo_path)}'
        f" && {env_assignments} {_REMOTE_DISPATCH_SENTINEL}=1"
        f" {shlex.quote(vps_python)} {shlex.quote(script_rel)}{args_str}"
    )

    print(f"[INFO] RUN_REMOTE=true: ejecutando en el VPS ({vps_user}@{vps_ip}): {script_rel}{args_str}")

    argv_ssh = ssh_argv(remote_cmd, identity_file=identity_file, user=vps_user, host=vps_ip)
    result = subprocess.run(argv_ssh)
    raise SystemExit(result.returncode)
