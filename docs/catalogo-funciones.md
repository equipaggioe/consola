# Catálogo de funciones — dónde viven, cuáles son atómicas y cuáles compuestas

Mapa de referencia rápida sobre [nivel-0.md](nivel-0.md) y [atomicas.md](atomicas.md): no repite el
porqué de cada decisión, solo responde "¿dónde está esto?" y "¿qué es esto?" con una tabla por
módulo.

---

## 1. Dónde se guarda cada cosa

| Capa | Carpeta / archivo | Qué contiene |
|---|---|---|
| Nivel 0 — plomería | `core/*.py` (`process.py`, `ssh.py`, `database.py`, `files.py`, `context.py`...) | Nada que sea una capacidad por sí solo: `capture()`, `Connection`, `reversible()`. Ningún módulo de este nivel importa `core/tasks/`. |
| Nivel 1 — atómicas | `core/tasks/<grupo>.py`, funciones sueltas | Un paso con una responsabilidad, idempotente. Puede o no tener botón propio (ver §3). |
| Nivel 2 — compuestas | `core/tasks/<grupo>.py`, mismo archivo que sus atómicas | Encadenan atómicas del mismo módulo (a veces de otro, ej. `bootstrap_vps` llama compuestas de `database.py`). |
| Forma de los botones | `core/catalog.py` | Declara cada `Capability`: grupo, sección, ejes (`AxisDef`), pasos (`Step`), si es `hidden`. No tiene lógica, solo forma. |
| El puente | `core/registry.py` — método `Registry.bind()` | `bind_all()` de cada módulo le pone la función real a la capacidad declarada. Mientras nadie haga `bind`, la `Capability` queda `stub=True` y la UI la dibuja como pendiente. |
| El disparador | `main.py` | `load_catalog()` (declara la forma) seguido de `bind_all()` (le da cuerpo). En ese orden. |

Regla para ubicar una función nueva: si no le importa nada de `ctx` (no loguea, no confirma, no
pregunta), es nivel 0 y va en `core/`. Si recibe `ctx` y hace un paso reconocible del dominio, es
nivel 1 o 2 y va en `core/tasks/<grupo>.py`.

---

## 2. Qué hace que algo tenga botón propio

No todas las atómicas de `core/tasks/` tienen una fila en el rail. Una atómica llega a botón propio
solo si además tiene una `Capability` registrada para ella en `core/catalog.py` (visible, o
`hidden=True` cuando el botón vive escondido como paso de otra). El resto son funciones tan
reutilizables y tan idempotentes como las demás, pero hoy solo se llaman desde dentro de una
compuesta — están escritas para ese día en que alguien pida "esto suelto" (PLAN.md §11, punto 5).

Tres columnas en las tablas de abajo:

- **Nivel** — atómica (A) o compuesta (C).
- **Botón** — el `id` de la `Capability` en `core/catalog.py` si tiene uno (visible o hidden); `—` si
  hoy solo es una función interna sin capacidad registrada.
- **Usada por** — qué compuesta la llama, cuando no es botón propio.

---

## 3. Catálogo completo por módulo

### `core/tasks/database.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `create_role` | A | — | `bootstrap_db` |
| `create_database` | A | — | `bootstrap_db` |
| `grant_privileges` | A | — | `bootstrap_db` |
| `enable_extensions` | A | — | `bootstrap_db` |
| `drop_tables` | A | — | `rebuild_db` |
| `drop_database` | A | — | `teardown_db` |
| `drop_role` | A | — | `teardown_db` |
| `reset_migrations` | A | — | `rebuild_db` |
| `generate_migration` | A | — | `rebuild_db`, `migrate_db` |
| `apply_migrations` | A | — | `rebuild_db`, `migrate_db` |
| `ensure_partitions` | A | — | `rebuild_db` |
| `run_seeders` | A | `run_seeders` | `rebuild_db` (y solo) |
| `run_mock_seeders` | A | `run_mock_seeders` | `rebuild_db` (y solo) |
| `backup_database` | A | `backup_db` | — |
| `rotate_backups` | A | — | `backup_database` |
| `open_db_tunnel` | A | `ssh_tunnel` | — |
| `inspect_database` | A | `inspect_db` | — |
| `bootstrap_db` | C | `bootstrap_db` | `bootstrap_vps` |
| `rebuild_db` | C | `rebuild_db` | `bootstrap_vps` |
| `teardown_db` | C | `teardown_db` | `clean_vps` |
| `migrate_db` | C | `migrate_db` | — |

### `core/tasks/emulators.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `install_system_image` | A | — | `start_emulator` |
| `create_avd` | A | — | `start_emulator` |
| `launch_emulator` | A | — | `start_emulator` |
| `await_emulator` | A | — | `run_mobile` (launchers.py) |
| `stop_emulator` | A | — | ningún llamador hoy |
| `delete_avd` | A | — | `purge_avds` |
| `delete_system_image` | A | — | `purge_system_images` |
| `inventory` | A | `avd_manager` | — |
| `start_emulator` | C | `start_emulator` | — |
| `purge_avds` | C | `purge_avds` | — |
| `purge_system_images` | C | `purge_images` | — |

### `core/tasks/builders.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `bump_version` | A | `bump_version` (hidden) | `build_apk`, `build_vite`, `build_binary` |
| `upload_artifact` | A | `upload_to_vps` (hidden) | `build_apk`, `build_vite`, `build_binary` |
| `fetch_dependencies` | A | — | `build_apk` |
| `compile_apk` | A | — | `build_apk` |
| `install_node_modules` | A | — | `build_vite` |
| `compile_spa` | A | — | `build_vite` |
| `compile_binary` | A | — | `build_binary` |
| `promote_app` | A | `promote_app` | — |
| `build_apk` | C | `build_apk` | — |
| `build_vite` | C | `build_vite` | — |
| `build_binary` | C | `build_binary` | — |

### `core/tasks/launchers.py`

Puros atómicos: ninguno encadena a otro (el módulo no declara compuestas).

| Función | Nivel | Botón |
|---|---|---|
| `resolve_server_port` | A | — (lo llama `serve_backend`) |
| `backend_url` | A | — (lo llama `serve_backend`) |
| `resolve_tls` | A | — (lo llama `serve_backend`) |
| `serve_backend` | A | `backend` |
| `serve_spa` | A | `serve_vite` |
| `run_mobile` | A | `run_mobile` |
| `open_terminal` | A | `terminal` |
| `open_ssh_session` | A | `ssh_login` |

### `core/tasks/vps_setup.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `refresh_known_host` | A | `refresh_known_host` | `bootstrap_vps` (y solo) |
| `ensure_remote_user` | A | — | `setup_ssh_key` |
| `configure_sudo` | A | — | `setup_ssh_key` |
| `install_public_key` | A | — | `setup_ssh_key` |
| `test_ssh_login` | A | — | `setup_ssh_key` |
| `install_base_software` | A | `install_software` | `bootstrap_vps` (y solo) |
| `install_coturn` | A | `install_coturn` | — |
| `generate_remote_keypair` | A | — | `setup_github_ssh` |
| `register_github_key` | A | — | `setup_github_ssh` |
| `test_github_ssh` | A | — | `setup_github_ssh` |
| `setup_ssh_key` | C | `setup_ssh_key` | `bootstrap_vps` |
| `setup_github_ssh` | C | `setup_github_ssh` | `bootstrap_vps` |
| `bootstrap_vps` | C | `bootstrap_vps` | — (tope: nadie la encadena) |

### `core/tasks/vps_server.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `clone_repository` | A | — | `update_remote` (primera corrida) |
| `sync_repository` | A | — | `update_remote` (corridas siguientes) |
| `ensure_remote_venv` | A | — | `update_remote` |
| `install_remote_deps` | A | — | `update_remote` |
| `upload_secret_files` | A | — | `update_remote` |
| `restart_service` | A | — | `update_remote`, `install_systemd` |
| `write_systemd_unit` | A | — | `install_systemd` |
| `systemd_action` | A | `systemd_action` | `install_systemd` (y solo) |
| `view_logs` | A | `view_logs` | — |
| `install_systemd` | C | `install_systemd` | `bootstrap_vps` |
| `update_remote` | C | `update_remote` | `bootstrap_vps` |

### `core/tasks/vps_ops.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `health_check` | A | `health_check` | — |
| `run_command` | A | `run_command` | — |
| `revoke_ssh_key` | A | `revoke_ssh` | — |
| `remove_remote_key_files` | A | — | `revoke_github_ssh` |
| `revoke_github_key` | A | — | `revoke_github_ssh`, `clean_vps` |
| `remove_systemd_service` | A | — | `clean_vps` |
| `remove_deployed_repo` | A | — | `clean_vps` |
| `uninstall_packages` | A | — | `clean_vps` |
| `remove_vps_user` | A | — | `clean_vps` |
| `run_setup_scripts` | C | `run_setup_scripts` | — |
| `revoke_github_ssh` | C | `revoke_github_ssh` | `clean_vps` |
| `clean_vps` | C | `clean_vps` | — (compuesta de compuestas: reusa `teardown_db` y `revoke_github_ssh`) |

### `core/tasks/utils.py`

Puros atómicos, sin compuestas propias:

| Función | Nivel | Botón |
|---|---|---|
| `find_artifacts` | A | — (lo llama `clean_artifacts`, es su simulacro) |
| `clean_artifacts` | A | `clean_artifacts` |
| `compare_common_files` | A | — (lo llama `sync_common_files`) |
| `sync_common_files` | A | `sync_common_files` |
| `detect_public_ip` | A | — (lo llama `update_cloudflare` en modo `detect`) |
| `update_cloudflare` | A | `update_cloudflare` |
| `install_android_sdk` | A | `install_android_sdk` |
| `install_flutter_sdk` | A | `install_flutter_sdk` |

### `core/tasks/payloads.py`

No es un grupo del rail: `discover()` y `run()` son plomería de nivel 0.5 que usan `database.py`
(seeders, particiones) y `vps_server.py` (autogenerate de Alembic) para correr código del proyecto
gestionado con el intérprete del venv del servidor. Ver [atomicas.md §4](atomicas.md).

---

## 4. Futuros compuestos

Dos tipos de pendiente, distintos entre sí.

### 4.1 — Atómicas sin botón: decisión abierta, no deuda por copiar el script viejo

No son huérfanas por descuido en el sentido de "había que igualar el script anterior y no se hizo".
Bajo el concepto de scripts sueltos, cada paso *tenía* que poder correr solo porque no había otra
forma de invocarlo; como aplicación con panel, eso ya no es una obligación heredada — algunas cosas
que antes exigían su propio botón hoy son mejor una casilla o directamente quedan escondidas
(`clean_vps` es el caso ya resuelto así, ver §4.1 abajo). El criterio sigue siendo el mismo de
siempre — *¿tiene sentido re-ejecutar este paso solo?* — pero la respuesta se valida con uso real,
no replicando la estructura de `scripts/`.

Lo que sigue es la lista de candidatas: ya existen, son idempotentes, y hoy solo se llaman desde
dentro de su compuesta. Volverlas botón es agregar una `Capability(hidden=True, ...)` en
`catalog.py` y un `registry.bind(...)` extra — no hace falta escribir lógica nueva, así que la
decisión de cuáles vale la pena es barata de posponer. Ninguna se cablea todavía; quedan a la espera
de que se confirme con uso que alguien las pide sueltas (PLAN.md §11.3):

| Candidata | Por qué serviría sola |
|---|---|
| `rotate_backups` | "Limpiar respaldos viejos sin volver a volcar la base" — el docstring ya lo dice explícito. |
| `sync_repository` | Traer los últimos commits al VPS sin tocar venv, deps ni certificados. |
| `write_systemd_unit` | Regenerar la unidad después de cambiar host/puerto, sin reinstalar el servicio. |
| `stop_emulator` | Hoy no la llama nadie: ni `start_emulator` ni ninguna compuesta la usa todavía. |
| `test_ssh_login` / `test_github_ssh` | Verificar una conexión ya configurada, sin rehacer el setup. |

### 4.2 — Compuestas que no existen todavía

Combinaciones de botones ya independientes que nadie encadenó, porque hoy se piden por separado uno
tras otro:

| Compuesta candidata | Encadenaría |
|---|---|
| `diagnose_vps` | `health_check` + `view_logs` + `inspect_db` — "decime si algo anda mal", en un solo click en vez de tres pestañas. |
| `setup_dev_machine` | `install_android_sdk` + `install_flutter_sdk` — preparar una máquina nueva de un tiro. |

Ninguna de las dos está en `catalog.py` todavía: son propuestas, no capacidades a medio implementar.

### 4.3 — Referencias cosméticas en `composed_of` que no son capacidades reales

Varios `composed_of=[...]` de `catalog.py` nombran ids que **no** están registrados como
`Capability` (`git_sync_remote`, `upload_files`, `ensure_keypair`, `install_pubkey`,
`remove_remote_ssh_key_files`, `run_remote_script`, entre otros). `Registry.resolve_steps()` cae al
`_prettify(sub_id)` cuando no encuentra la capacidad, así que el panel igual muestra un nombre
legible — pero no es un botón real ni un atajo a la atómica homónima (que sí existe, con otro
nombre: `sync_repository`, `upload_secret_files`, `generate_remote_keypair`, `install_public_key`,
`remove_remote_key_files`). No rompe nada hoy; vale la pena alinear esos ids con los nombres reales
de §3 la próxima vez que se toque `catalog.py`, para que un futuro `bind()` de esos sub-pasos no
tenga que renombrar la mitad de las funciones.

---

## 5. Cómo se ve esto en la UI

Lo de §3 dejó de vivir solo en este documento: cada `Capability` lleva dos campos que la interfaz
usa para decir lo mismo sin abrir el markdown.

| Campo en `catalog.py` | Dónde se ve |
|---|---|
| `description` — una línea, en presente, qué hace el botón | Tooltip de la fila en el rail, bajo el nombre en la cabecera del panel derecho, primera línea de la consola al abrir la pestaña, tooltip de la sub-pestaña. También lo busca el filtro del rail: "caché" encuentra *Limpiar artefactos*. |
| `level` / `is_composite` — atómica o compuesta | Marca al final de cada fila del rail: `◈` compuesta, `◦` atómica; y `◈ compuesta` / `◦ atómica` en la cabecera del panel derecho. El tooltip lo dice con palabras. |

`is_composite` se deduce sola cuando la capacidad declara `steps` o `composed_of`. Las compuestas
que no publican sus pasos en el panel (`bootstrap_db`, `teardown_db`, `migrate_db`,
`start_emulator`, `purge_avds`, `purge_images`) lo declaran a mano con `level='C'` — si alguna de
ellas gana `composed_of` de verdad, el `level` se puede borrar y sigue saliendo bien.

---

## 6. Primer botón conectado de verdad: `clean_artifacts`

Hasta ahora `TabPanel._run` simulaba siempre — reportaba lo que correría, sin correr nada (PLAN.md
§10). `clean_artifacts` es el primero que corre de verdad, y deja el mecanismo para conectar el
resto uno por uno:

| Pieza | Qué hace |
|---|---|
| `ui/task_runner.py` — `TaskRunner(QThread)` | Arma un `TaskContext` real y llama a la función de la capacidad en un hilo aparte; traduce `log_sink` a señales Qt (`logged`, `finished_ok`) que la consola pinta. Sirve para cualquier capacidad simple (sin pasos, sin `ctx.confirm()`/`ctx.ask()`) — una compuesta con dialogo real todavía necesita puentear `ask_sink` con una señal bloqueante. |
| `ui/task_adapters.py` — `ADAPTERS` | Un `capability_id` → función que traduce el `payload` del panel (etiquetas que ve el usuario, ej. `'Gradle/Android'`) a los kwargs que espera la función real (`families=['gradle']`). Es la traducción entre "cómo se llama esto para quien lo lee" y "cómo se llama esto para quien programa". |
| `TabPanel._run` | Si la capacidad tiene `func` (no es stub) y tiene adaptador registrado, corre `_run_real`; si no, sigue en `_run_stub` — el camino de siempre. Conectar el próximo botón es agregar su entrada en `ADAPTERS`. |

`find_artifacts`/`clean_artifacts` ([core/tasks/utils.py](../core/tasks/utils.py)) ganaron dos
parámetros para esto: `families` (qué cachés livianas listar — Python, Gradle/Android, Flutter,
volcados de crash) y `heavy` (carpetas pesadas que se listan y borran enteras, no por dentro —
`node_modules`, `.venv`, `build`/`dist`, `.dart_tool`). `heavy` viene apagado por defecto: un
axis con `allow_empty=True` en `AxisDef`, porque "no marqué nada" es una elección válida ahí,
no un olvido — a diferencia de un axis como "Apps" en `build_vite`, donde vaciarlo es un error.

Quedó afuera de esta vuelta (documentado como pendiente, no descartado): elegir el repo destino
entre varios (`c` de la propuesta original) necesita un selector de multi-repo que hoy no existe
en ningún botón; y filtrar por antigüedad/tamaño mínimo (`d`) necesita un tipo de campo numérico
que el panel de parámetros todavía no sabe dibujar (hoy todo axis single-select es un grupo de
radio buttons, ver `ui/params_panel.py::_build_options`).

---

## 7. Estado

`registry.implemented()` devuelve 45 capacidades con `func` real (0 stubs) — ver
[atomicas.md §5](atomicas.md). Este documento no agrega capacidades nuevas: es el índice de qué
función vive dónde, para no tener que grepear `core/tasks/` cada vez que hace falta ubicar una.
