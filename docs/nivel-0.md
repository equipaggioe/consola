# Nivel 0 — funciones comunes en `core/`

Implementación del nivel 0 descrito en [PLAN.md §2.1](PLAN.md). Traslada `scripts/common.py`
(917 líneas, un solo archivo) a doce módulos en `core/`, cada uno responsable de una sola clase
de problema. No es una copia: cada función se leyó por su comportamiento y se reescribió con
nombres homologados — se descartó lo que solo existía por cómo funcionaba el sistema de scripts
sueltos (ver §3).

Ninguno de estos módulos produce un botón. Son la plomería que usan por dentro las capacidades
atómicas y compuestas de nivel 1/2 (`core/tasks/*.py`, todavía no implementadas).

---

## 1. Convención de nombres

Antes, `common.py` no tenía un criterio único: `resolve_flutter_cmd` junto a `sdk_root_from_env`
junto a `_local_database_url`. En `core/` todo módulo sigue el mismo vocabulario:

| Prefijo | Significa | Ejemplos |
|---|---|---|
| `resolve_*` | deriva un valor; falla con `TaskError` si no puede | `resolve_remote`, `resolve_identity`, `resolve_port`, `resolve_executable` |
| `list_*` | inventario, devuelve una lista | `list_avds`, `list_images`, `list_devices`, `list_keys` |
| `find_*` / `only` | búsqueda puntual; `None` o error si es ambigua | `find_key`, `find_manifest`, `only` |
| `ensure_*` | idempotente: detecta el estado actual antes de actuar | `ensure_avd`, `ensure_dir`, `ensure_local_keypair` |
| `read_*` / `write_*` | I/O de un archivo puntual | `read_version`, `write_unit`, `read_value`, `upsert_value` |
| `run` / `capture` / `detach` | ejecutar con log en vivo / sin log / que sobreviva a la pestaña | métodos de `TaskContext` y de `core/ssh.py` |
| `is_*` / `*_exists` / `succeeds` | predicados | `is_free`, `service_exists`, `path_exists` |

---

## 2. Módulos

### `core/errors.py`
`TaskError` (falla esperable, marca la pestaña en rojo), `Cancelled` (el usuario detuvo la
tarea), `MissingConfig` (subclase de `TaskError` que además lleva `keys: list[str]`, para que la
UI pueda abrir el engranaje de Configuración filtrado a esas claves en vez de mostrar un mensaje
suelto).

### `core/context.py` — `TaskContext`
La pieza central de PLAN.md §4, ahora con cuerpo real (antes era un placeholder de 19 líneas).
Es lo que hace corto el código de un botón: casi todo termina siendo `ctx.algo(...)`.

- `ctx.log/info/ok/warn/error(msg)` — a la consola de su pestaña, coloreado.
- `ctx.step(titulo)` — encabezado de un paso dentro de una compuesta; el log de una receta
  queda plano, sin sub-pestañas (PLAN.md §7, caso 8).
- `ctx.run(argv, cwd=, env=, check=)` — binario externo con streaming línea a línea y
  cancelación; colorea automáticamente líneas que empiezan con `ERROR`/`WARN`/`OK`.
- `ctx.capture(argv, ...)` — comando corto, devuelve la salida, no la vuelca al log.
- `ctx.detach(argv, cwd=)` — proceso que sobrevive a su pestaña (servicio de fondo, §7.2).
- `ctx.confirm(pregunta, danger=, expect=)` — diálogo modal; `expect` exige escribir un texto
  exacto (destructivos, §7.5).
- `ctx.ask(prompt, secret=)` — pide un dato al usuario; si es secreto, lo enmascara después.
- `ctx.guard(*valores)` / `ctx.mask(texto)` — marca valores para que no vuelvan a aparecer en
  claro en la consola ni en el log guardado.
- `ctx.require_config(*keys)` — levanta `MissingConfig` **antes** de arrancar si falta algo, en
  vez de morir a mitad de flujo con un `[ERROR] Falta variable de entorno` como hacían los scripts.
- `ctx.note(entry)` — entrada automática en la bitácora del proyecto (§8).
- `ctx.cancel()` / `ctx.cancelled` / `ctx.raise_if_cancelled()` — cancelación cooperativa; mata
  el árbol de procesos hijos registrados.
- `ctx.child(capability_id)` — contexto para un paso interno: mismo log, misma cancelación,
  mismos secretos enmascarados. Así una compuesta llama a sus atómicas sin que el usuario vea
  una segunda consola ni un segundo botón Detener.

### `core/process.py`
Ejecución de binarios externos, sin Qt:

- `stream(argv, on_line, cancel, register)` — corre y entrega cada línea a un callback;
  cancelable a mitad de camino (mata el proceso si `cancel` se activa).
- `capture(argv, timeout, check)` — para consultas cortas.
- `feed(argv, stdin_text, timeout)` — como `capture`, pero le escribe a stdin y no revisa el
  código de salida. Es la excepción deliberada a "nunca dejar un proceso esperando teclado"
  (`stream`/`capture` cierran stdin a propósito): `sdkmanager --licenses` pregunta licencia por
  licencia y no tiene bandera para aceptar todas de una.
- `spawn(argv, detached=)` / `kill_tree(proc)` — `kill_tree` termina de abajo hacia arriba
  (`taskkill /T /F` en Windows, `killpg` en POSIX) para no dejar procesos zombis ocupando
  puertos — el caso del launcher que vigila archivos y relanza a su hijo (§7, caso 6).
- `resolve_executable(names, override, label, hint)` — unifica tres funciones que en
  `common.py` eran casi idénticas (`resolve_flutter_cmd`, `resolve_flet_cmd`,
  `resolve_android_tool`): primero el override explícito, después el PATH.
- `as_argv(exe)` — envuelve los shims `.bat`/`.cmd` de Windows con `cmd.exe /c`.

### `core/envfile.py`
Ya existía (parseo de `.consola/config.env`, `render_config`, `save_config`,
`_ensure_gitignored`). Se le agregó:

- `read_value(path, key)` — lee una sola clave sin tocar `os.environ` (reemplaza
  `peek_env_value`; nunca muta el entorno del proceso, porque una tarea no puede pisarle el
  entorno a las otras pestañas que corren a la vez).
- `upsert_value(path, key, value)` — reemplaza o agrega una línea conservando el resto.
- **Clase `Config`** — reemplaza las ocho funciones sueltas sobre `os.environ`
  (`require_env`, `require_port_env`, `require_bool_env`, `optional_env`, ...):
  `Config.for_project(repo_path)`, `.get(key, default)` (con fallback al default del
  esquema de `settings.py`), `.require(key)`, `.port(key)`, `.flag(key)`, `.rel_path(key, root)`,
  `.missing(*keys)`, `.secrets()`.

### `core/ssh.py`
- **`Remote`** (dataclass) — host + user + identity juntos. Antes cada función remota recibía
  los tres por separado y los volvía a resolver. Trae `.argv(cmd)`, `.scp_argv(local, remote)`,
  `.as_user(otro)` (para operar como root durante el aprovisionamiento).
- `resolve_remote(config, user=)` — arma el `Remote` del proyecto desde `Config`.
- `capture/run/succeeds/path_exists/ensure_dir` sobre un `Remote`.
- `upload/download` — sube o baja archivos/directorios por scp.
- **`Tunnel`** (context manager) — `open_tunnel(remote, local_port, remote_port)`; `.alive`,
  `.endpoint`, `.close()`.
- `ensure_local_keypair`, `public_key`, `forget_host`/`trust_host` (limpiar y repoblar
  `known_hosts` tras reinstalar el VPS), `terminal_argv(remote)` (arma el comando para abrir
  una terminal externa — sesión SSH interactiva, §7 caso 1).
- Multiplexado SSH (`ControlMaster`) preservado tal cual estaba en `common.py`, con el mismo
  apagado condicional en Windows (el `ControlMaster` de Win32-OpenSSH no es confiable ahí).

### `core/vps.py`
Todo lo que opera sobre el VPS ya conectado, construido sobre `core/ssh.py`:

- `repo_name(config)` / `deploy_root(config)` / `remote_path(config, *parts)` /
  `remote_python(config)` — rutas del despliegue derivadas de `GIT_REPO_URL` y
  `VPS_DEPLOY_DIR`.
- `user_exists`, `install_packages` (idempotente: solo instala lo que falta).
- `service_state(remote, service)` → `'missing' | 'active' | 'inactive' | 'failed'` — distingue
  "no existe todavía" de "existe pero está parado", algo que los scripts no separaban.
- `systemctl(ctx, remote, action, service)` — una sola función para todas las acciones; separa
  `BUTTON_ACTIONS` (`start/stop/restart/status`) de `MENU_ACTIONS`
  (`enable/disable/reload/is-active/is-enabled/daemon-reload`), listas para los dos `expand` del
  eje `action` en PLAN.md §2.4.
- `render_unit(...)` / `write_unit(...)` — arma y sube el archivo `.service`.
- `journal_command(service, lines, follow, since, priority, grep)` — reemplaza a
  `view_logs.py`, capacidad hermana de `systemctl` (§1: dejó de ser un valor de `action`).
- `postgres_port(remote)` — consulta `SHOW port` al Postgres del VPS.
- `health(remote, service)` — resumen para el chequeo de salud (servicio, uptime, disco, memoria).

### `core/database.py`
El reemplazo real de `RUN_REMOTE` / `maybe_dispatch_remote`:

- `connect(ctx, scope)` → `Connection` — la función corre siempre dentro de la app; lo único
  que cambia según `scope` (`'local' | 'remoto'`) es contra qué base apunta. Si es remota, abre
  el túnel SSH y nunca se conecta a la IP pública del VPS (PLAN.md §6).
- `Connection` es un context manager: cierra el túnel solo al salir del `with`.
- `local_port()` — lee el puerto real de Postgres desde `postgresql.conf` en Windows (evita
  asumir 5432 si hay varias versiones instaladas).
- `server_url(root)` — la única lectura permitida de `server/.env` (nunca escritura), para
  precargar el formulario del explorador con la `DATABASE_URL` que ya declaró el servidor.
- `mask_url(url)` — oculta la contraseña al mostrar la URL en consola.

### `core/versioning.py`
- `bump(version, mode)` — incrementa SemVer; respeta el build number de Flutter
  (`1.4.22+318` → `1.4.23+319` en modo patch) porque Play Store rechaza un APK que repita el
  código anterior.
- `find_manifest(project_dir)` — ubica `pubspec.yaml` / `package.json` / `pyproject.toml`.
- `read_version` / `write_version` — tocan solo la línea de la versión, sin reformatear el
  resto del archivo.

### `core/github.py`
- `request(method, path, token, body)` — llamada cruda, devuelve `(status, payload)` sin
  levantar excepción (la mayoría de los llamantes distingue 404 de 401).
- `find_key(token, title)` / `register_key(...)` / `revoke_key(...)` — idempotentes: registrar
  una llave que ya existe con el mismo contenido no hace nada; revocar una que no existe no falla.

### `core/toolchain.py`
- `flutter_cmd()` / `flet_cmd()` / `npm_cmd()` — sobre `resolve_executable`.
- `detect_app_kind(project_dir)` → `'flutter' | 'flet'` — el eje `framework` descubierto de
  §2.4, por marcador de archivo.
- `devices(ctx, project_dir)` / `pick_emulator(found)` — Flet no tiene detección propia (su
  `flet devices` parsea la tabla de texto del Flutter subyacente), así que ambos framework
  preguntan por el mismo lado (`flutter devices --machine`).

### `core/android.py`
- **`Sdk`** (dataclass) — ubica las cuatro herramientas del SDK (`adb`, `emulator`,
  `avdmanager`, `sdkmanager`) una sola vez; si falta una, dice cuál y dónde se buscó.
- **`Preset`** + diccionario `PRESETS` (`pixel_4`, `pixel_8`, `resizable`) — reemplaza a los
  tres `run_emulator_N.py`, que eran el mismo flujo con una constante distinta.
- `list_avds/list_images/list_devices` — el estado del emulador no se infiere de un PID (se
  desprende del proceso que lo lanzó, §7 caso 3): se sondea con `adb`.
- `ensure_image` / `ensure_avd` (deja `hw.keyboard=yes` en `config.ini`) / `start` /
  `wait_for_boot` / `stop` (`adb emu kill`, no matar el proceso) / `remove_avd` / `remove_image`.

### `core/targets.py`
- **`Target`** (dataclass: `name`, `kind`, `path`) + `discover(root)` — recorre el repo hasta
  dos niveles de profundidad (ignora `node_modules`, `.git`, `build`, etc.) y devuelve los
  subproyectos tipados que encuentra: `spa-vite`, `flutter-app`, `flet-app`, `fastapi-server`.
  Es el eje descubierto de §2.4: no hace falta enumerar a mano qué subproyecto tiene cada uno
  de los 8 repos gestionados.
- `by_kind` / `names` / `find` / `only` (falla si hay cero o más de uno del tipo pedido).

### `core/files.py`
- `reversible(path)` — context manager que revierte un archivo si el bloque falla (rollback
  del bump de versión si el build revienta después).
- `compare(source, target)` → `'NEW' | 'DIFF' | 'SAME'` — el simulacro que exige PLAN.md §7.5
  antes de habilitar Aplicar en cualquier destructivo.
- `copy`, `collect(root, patterns)` (arma la lista exacta de lo que un destructivo va a tocar),
  `remove`, `size_of`, `human_size`.
- `digest(path, algorithm)` — SHA-1/SHA-256 genérico por bloques, agregado para verificar los
  paquetes descargados de los SDK (Android publica SHA-1, Flutter SHA-256; ver `atomicas.md §4.1`).
- `extract(archive, target)` / `extract_zip(archive, target)` — descomprime `.zip` o
  `.tar.{xz,gz,bz2}` según la extensión. `extract_zip` recupera el modo Unix de cada entrada desde
  `external_attr`, que `ZipFile.extractall` a secas descarta — sin esto, un binario descomprimido
  en Linux queda sin permiso de ejecución aunque el zip se haya descomprimido bien.

### `core/userenv.py`
Variables de entorno de usuario persistentes, sin permisos de administrador — Linux primero,
Windows igual de completo. Reemplaza el `setx /M` + HKLM de los scripts originales, que exigían
una consola elevada para instalar nada.

- `configure(ctx, variables=, path_add=, path_drop=)` — escribe variables y agrega/quita entradas
  del PATH, y además las aplica al `os.environ` del proceso vivo (para que la propia Consola
  encuentre lo recién instalado sin reiniciarse).
- En Linux/Mac: un bloque delimitado (`# >>> consola >>>` / `# <<< consola <<<`) en `.bashrc`/
  `.zshrc`, que se reescribe entero cada vez — así dos capacidades distintas (Android, Flutter)
  pueden compartir el mismo bloque sin pisarse, y reinstalar en otro directorio no deja rutas
  viejas colgando.
- En Windows: `HKCU\Environment`, nunca `HKLM`. `path_drop` avisa (sin tocarlo) si el PATH del
  sistema tiene una entrada vieja de una instalación anterior con `setx /M`, que le ganaría por
  orden de precedencia — limpiarla si hace falta admin, así que solo se informa.
- `_broadcast_change()` — `WM_SETTINGCHANGE` por `SendMessageTimeout`, para que las terminales
  nuevas vean el cambio sin cerrar sesión.

### `core/toolstatus.py`
Qué herramientas de desarrollo tiene la máquina, para los indicadores de la barra de estado.

- `detect()` → `list[Tool]` con Java, Git, SDK de Android y Flutter. Cada `Tool` trae `found`,
  la ruta donde se encontró y un `hint` de qué hacer si falta (los tres van al tooltip del LED).
- Deliberadamente **barato**: solo mira que el archivo exista y dónde, nunca lanza `java -version`
  ni `flutter doctor`. Preguntárselo a cada herramienta cuesta segundos y bloquearía la interfaz en
  cada refresco; para lo que el indicador dice —está o no está— alcanza con el disco. Ocho
  detecciones completas tardan ~6 ms.
- Cada herramienta se busca primero bajo su variable (`JAVA_HOME`, `FLUTTER_HOME`,
  `ANDROID_SDK_ROOT` vía `core/android.resolve_sdk()`) y recién después en el PATH, porque una
  instalación recién hecha escribe la variable en el mismo momento que la ruta — así el LED se pone
  en verde sin reiniciar Consola.

### `core/ports.py`
- `is_free(port)` / `resolve_port(preferred, search)` — el puerto es estado de sesión
  (PLAN.md §7, caso 4): nadie lo escribe a un `.env`, lo devuelve la función y lo pasa quien
  arranca el servicio siguiente, en memoria.

---

## 3. Qué se descartó y por qué

Existía en `common.py` únicamente porque el sistema anterior eran scripts sueltos comunicados
por archivos y variables de entorno de proceso. Dentro de la app esos problemas no existen:

| Función descartada | Por qué ya no hace falta |
|---|---|
| `maybe_dispatch_remote` | Reenviaba el script entero al VPS por SSH según `RUN_REMOTE`. Reemplazado por el eje `scope` sobre `core/database.connect()` — la función corre siempre en la app, no se relanza a sí misma en el servidor. |
| `force_env_vars` | Forzaba variables en `os.environ` antes de lanzar un script hijo por subprocess que heredaba el entorno. Ya no hay scripts hijos: las capacidades reciben sus parámetros por argumento. |
| `load_env_file` con `input()` | Preguntaba por consola qué valor usar si una clave ya estaba en el entorno. Una tarea de Consola no puede bloquear el proceso entero ni pisarle el entorno a otra pestaña corriendo en paralelo. |
| `find_project_root` | Buscaba `.git` subiendo desde el archivo que llama. Consola ya conoce la raíz por `Project.path`. |
| `print_header` / `run_logged` | Imprimían a stdout con separadores. Reemplazados por `ctx.step()` / `ctx.run()`, que van a la consola de la pestaña, no a una terminal. |
| `SystemExit(1)` como forma de error | En todos los `require_*` y validaciones. Reemplazado uniformemente por `TaskError`, que la UI atrapa sin tumbar la app. |
| `venv_python(restart=True)` con `os.execv` | Relanzaba el proceso actual con otro Python. El venv resuelto ahora es el intérprete de un *subproceso* que la app lanza, no algo con lo que la propia app se reinicia. |
| `restart_systemd_service(run=callable)` | Recibía un callable de ejecución (local o SSH) para desacoplarse del mecanismo. Ya no hace falta: `Remote` ya es ese mecanismo, `vps.systemctl` lo usa directo. |

---

## 4. Estado y siguiente paso

12 módulos nuevos + 3 ampliados (`context.py`, `envfile.py`, `__init__.py`), ~2.300 líneas.
Todo importa limpio y pasa smoke tests manuales (bump de versión, máscara de secretos,
descubrimiento de targets, armado de `argv` SSH, rutas remotas, comando de journalctl).

Pendiente: nivel 1 (`core/tasks/*.py`) — las capacidades atómicas que reemplazan los `stub=True`
de `core/catalog.py`, construidas sobre estos módulos. Etapa 2 de PLAN.md §10.
