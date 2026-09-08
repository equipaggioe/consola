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
| `drop_tables` | A | — | `rebuild_db`, `reinit_migrations` |
| `drop_database` | A | — | `teardown_db` |
| `drop_role` | A | — | `teardown_db` |
| `reset_migrations` | A | — | `reinit_migrations` |
| `generate_migration` | A | — | `reinit_migrations`, `migrate_db` |
| `apply_migrations` | A | — | `populate_db`, `migrate_db`, `update_remote` |
| `ensure_partitions` | A | — | `populate_db` |
| `run_seeders` | A | `run_seeders` | `populate_db` (y solo) |
| `run_mock_seeders` | A | `run_mock_seeders` | `populate_db` (y solo) |
| `backup_database` | A | `backup_db` | — |
| `rotate_backups` | A | — | `backup_database` |
| `open_db_tunnel` | A | `ssh_tunnel` | — |
| `inspect_database` | A | `inspect_db` | — |
| `populate_db` | C | — | `bootstrap_db`, `rebuild_db` |
| `bootstrap_db` | C | `bootstrap_db` | `bootstrap_vps` |
| `rebuild_db` | C | `rebuild_db` | — |
| `reinit_migrations` | C | `reinit_migrations` | — |
| `teardown_db` | C | `teardown_db` | `clean_vps` |
| `migrate_db` | C | `migrate_db` | — |

### `core/tasks/emulators.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `install_system_image` | A | `install_system_image` | — |
| `create_avd` | A | `create_avd` | — |
| `launch_emulator` | A | `launch_emulator` | — |
| `await_emulator` | A | — | `run_mobile` (launchers.py) |
| `stop_emulator` | A | oculto: el ✕ de *Corriendo ahora* | `ui/tab_panel.py` |
| `purge_emulators` | A | `purge_emulators` | — |
| `inventory` | A | — | — |

El grupo no tiene compuestas: instalar la máquina, crear el AVD y arrancarlo son tres actividades
con catálogos propios, no tres pasos de una secuencia. El porqué, en [emuladores.md](emuladores.md).

### `core/tasks/builders.py`

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `bump_version` | A | `bump_version` (hidden) | `build_apk`, `build_vite`, `build_binary` |
| `upload_artifact` | A | `upload_to_vps` (hidden) | `build_apk`, `build_vite`, `build_binary` |
| `compile_apk` | A | — | `build_apk` |
| `install_node_modules` | A | — | `build_vite` |
| `compile_spa` | A | — | `build_vite` |
| `compile_binary` | A | — | `build_binary` |
| `resolve_entrypoint` | A | — | `build_binary` (deduce `src/main.py` cuando el campo va vacío) |
| `checksum_artifact` | A | — | `build_binary` (paso `checksum`) |
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
| `ensure_deploy_access` | A | — | `setup_ssh_key` |
| `configure_sudo` | A | — | `setup_ssh_key` |
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
| `push_repository` | A | — | `publish_code` (primer paso, marcado) |
| `sync_repository` | A | — | `publish_code` (clona o actualiza según el estado del VPS) |
| `install_remote_deps` | A | — | `publish_code` (crea el venv adentro) |
| `upload_secret_files` | A | `upload_secret_files` | `publish_code` |
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

| Función | Nivel | Botón | Usada por |
|---|---|---|---|
| `find_artifacts` | A | — | `clean_artifacts`, es su simulacro |
| `clean_artifacts` | A | `clean_artifacts` | — |
| `compare_common_files` | A | — | `sync_common_files` |
| `sync_common_files` | A | `sync_common_files` | — |
| `detect_public_ip` | A | — | `update_cloudflare` en modo `detect` |
| `update_cloudflare` | A | `update_cloudflare` | — |
| `install_android_tools` | A | `install_android_tools` | `install_android_sdk` (y solo) |
| `install_android_packages` | A | `install_android_packages` | `install_android_sdk` (y solo) |
| `install_android_hypervisor` | A | `install_android_hypervisor` | `install_android_sdk` (y solo) |
| `install_flutter_sdk` | A | `install_flutter_sdk` | — |
| `install_android_sdk` | C | `install_android_sdk` | — |

`install_android_sdk` era una sola atómica hasta que se implementó de verdad; ver por qué se
partió en tres en [atomicas.md §0](atomicas.md#0-corrección-qué-no-es-una-atómica). Las cinco
capacidades de este módulo llevan `scope='machine'` (§5): instalar un SDK no es una decisión del
repo abierto, vale para toda la máquina.

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
| `test_github_ssh` | Verificar una conexión ya configurada, sin rehacer el setup. (`test_ssh_login` era su hermana y dejó de existir: ver [atomicas.md §4.6](atomicas.md).) |

### 4.2 — Compuestas que no existen todavía

Combinaciones de botones ya independientes que nadie encadenó, porque hoy se piden por separado uno
tras otro:

| Compuesta candidata | Encadenaría |
|---|---|
| `diagnose_vps` | `health_check` + `view_logs` + `inspect_db` — "decime si algo anda mal", en un solo click en vez de tres pestañas. |
| `setup_dev_machine` | `install_android_sdk` + `install_flutter_sdk` — preparar una máquina nueva de un tiro. |

Ninguna de las dos está en `catalog.py` todavía: son propuestas, no capacidades a medio implementar.
`install_android_sdk` ya es compuesta por su cuenta (§3), así que `setup_dev_machine` encadenaría
una compuesta con una atómica, no dos atómicas sueltas.

### 4.3 — Referencias cosméticas en `composed_of` que no son capacidades reales

Varios `composed_of=[...]` de `catalog.py` nombran ids que **no** están registrados como
`Capability` (`git_sync_remote`, `upload_files`, `ensure_keypair`, `install_pubkey`,
`remove_remote_ssh_key_files`, `run_remote_script`, entre otros). *(`ensure_keypair` e `install_pubkey`
ya no: `setup_ssh_key` pasó a declarar `steps` reales — ver [atomicas.md §4.6](atomicas.md).)*
`Registry.resolve_steps()` cae al
`_prettify(sub_id)` cuando no encuentra la capacidad, así que el panel igual muestra un nombre
legible — pero no es un botón real ni un atajo a la atómica homónima (que sí existe, con otro
nombre: `sync_repository`, `upload_secret_files`, `generate_remote_keypair`, `install_public_key`,
`remove_remote_key_files`). No rompe nada hoy; vale la pena alinear esos ids con los nombres reales
de §3 la próxima vez que se toque `catalog.py`, para que un futuro `bind()` de esos sub-pasos no
tenga que renombrar la mitad de las funciones.

---

## 5. `scope='machine'` — capacidades que no son del repo

`Capability.scope` (`core/registry.py`) distingue dos cosas que hasta ahora se trataban igual:

- `'repo'` (por defecto) — la selección del panel es una decisión sobre el repo abierto. `build_apk`
  en `navetta` y en `otra-app` casi nunca marca lo mismo.
- `'machine'` — la selección vale para toda la máquina, no para el repo desde el que se abrió el
  panel. Instalar el SDK de Android en `D:\Android` no es una decisión de un proyecto.

`ui/params_store.py` guarda las `machine` en `QSettings`, bajo una sola clave
(`params/machine/<capability_id>`): el directorio elegido en un repo aparece igual en cualquier
otro. Es **la excepción** a la regla de [parametros-persistentes.md](parametros-persistentes.md),
donde todo lo demás baja a `.consola/params.json` dentro del repo. El criterio es de quién es la
decisión: el repo no puede opinar sobre dónde va el SDK de Android.

Las cinco capacidades de `install_*` en `core/tasks/utils.py` son hoy las únicas `scope='machine'`.

**En el rail** llevan la marca `⌂` (`ui/widgets/group_card.py::ScopeMark`) antes de la marca de
nivel, y la cabecera del panel derecho lo repite con palabras. Solo se marca lo de máquina: la
ausencia de marca ya significa "es de este repo", que es el caso normal.

**En la barra de estado** hay cuatro LED —Java, Git, SDK Android, Flutter— que salen de
`core/toolstatus.py` (ver [nivel-0.md](nivel-0.md)). Se chequean solos al abrir el espacio de
trabajo y **después de cada acción de máquina**: como la instalación deja las variables en el
`os.environ` del proceso (`core/userenv.py`), el LED pasa a verde apenas termina, sin reiniciar
Consola. Por eso no hay —ni hace falta— un botón de "estado del entorno".

El verde de estos LED es fijo (`LedIndicator` estado `'on'`), no el verde que late: el pulso está
reservado para un servicio corriendo ahora mismo, y una herramienta instalada es un hecho quieto.

---

## 6. Cómo se ve esto en la UI

Lo de §3 dejó de vivir solo en este documento: cada `Capability` lleva dos campos que la interfaz
usa para decir lo mismo sin abrir el markdown.

| Campo en `catalog.py` | Dónde se ve |
|---|---|
| `description` — una línea, en presente, qué hace el botón | Tooltip de la fila en el rail, bajo el nombre en la cabecera del panel derecho, primera línea de la consola al abrir la pestaña, tooltip de la sub-pestaña. También lo busca el filtro del rail: "caché" encuentra *Limpiar artefactos*. |
| `level` / `is_composite` — atómica o compuesta | Marca al final de cada fila del rail: `◈` compuesta, `◦` atómica; y `◈ compuesta` / `◦ atómica` en la cabecera del panel derecho. El tooltip lo dice con palabras. |

`is_composite` se deduce sola cuando la capacidad declara `steps` o `composed_of`. Las compuestas
que no publican sus pasos en el panel (`teardown_db`) lo declaran a mano con `level='C'` — si
ganan `composed_of` o `steps` de verdad, el `level` se puede borrar y sigue saliendo bien.

---

## 7. Primer botón conectado de verdad: `clean_artifacts`

Hasta ahora `TabPanel._run` simulaba siempre — reportaba lo que correría, sin correr nada (PLAN.md
§10). `clean_artifacts` es el primero que corre de verdad, y deja el mecanismo para conectar el
resto uno por uno:

| Pieza | Qué hace |
|---|---|
| `ui/task_runner.py` — `TaskRunner(QThread)` | Arma un `TaskContext` real y llama a la función de la capacidad en un hilo aparte; traduce `log_sink` a señales Qt (`logged`, `finished_ok`) que la consola pinta. Sirve para cualquier capacidad simple (sin pasos, sin `ctx.confirm()`/`ctx.ask()`) — una compuesta con dialogo real todavía necesita puentear `ask_sink` con una señal bloqueante. |
| `Capability.kwargs_from()` — `core/registry.py` | Lee el `payload` del panel y devuelve los kwargs de la función, sin tabla por capacidad: el `name` de cada eje y el `id` de cada paso YA son el nombre del parámetro, y lo que ve el usuario vive en `label`/`labels`. Reemplaza a `ui/task_adapters.py`, que mantenía ese mismo nombre escrito por tercera vez (ver `docs/contrato-de-nombres.md`). |
| `TabPanel._run` | Si la capacidad tiene `func` (no es stub), corre `_run_real`; si no, `_run_stub`. Es la única condición: antes hacían falta dos —cuerpo y una entrada en `ADAPTERS`— y ese diccionario dejaba veinte capacidades escritas corriendo como simulación. Conectar un botón nuevo es escribir su función y bindearla. |

`find_artifacts`/`clean_artifacts` ([core/tasks/utils.py](../core/tasks/utils.py)) ganaron dos
parámetros para esto: `families` (qué cachés livianas listar — Python, Gradle/Android, Flutter,
volcados de crash) y `heavy` (carpetas pesadas que se listan y borran enteras, no por dentro —
`node_modules`, `.venv`, `build`/`dist`, `.dart_tool`). `heavy` viene apagado por defecto: un
axis con `allow_empty=True` en `AxisDef`, porque "no marqué nada" es una elección válida ahí,
no un olvido — a diferencia de un axis como "Apps" en `build_vite`, donde vaciarlo es un error.

Quedó afuera de esta vuelta (documentado como pendiente, no descartado): elegir el repo destino
entre varios (`c` de la propuesta original) necesita un selector de multi-repo que hoy no existe
en ningún botón; y filtrar por antigüedad/tamaño mínimo (`d`) necesitaba un tipo de campo numérico
que el panel no sabía dibujar — el §7.1 agrega uno de texto para otro caso, todavía no uno
numérico con validación.

### 7.1 — `expand='field'`: el primer axis que se escribe, no se elige

Todos los `AxisDef` hasta `install_android_sdk` eran de una lista cerrada de valores (casillas,
segmentado, menú). El directorio de instalación de un SDK, el API level, el build-tools — no son
una lista: son un valor escrito, con un default razonable. `AxisDef(expand='field')` es ese cuarto
tipo: `Capability.field_axes` filtra los ejes de este tipo, `ui/params_panel.py::_build_fields`
dibuja un `QLineEdit` por cada uno con `values[0]` como valor inicial (y placeholder si se vacía),
y `ParamsPanel.field_value(axis_name)` lee lo escrito. Se guarda y se restaura igual que el resto
del estado del panel (`state()['fields']`, ver
[parametros-persistentes.md](parametros-persistentes.md)).

Las cinco capacidades de instalación de SDK (§5) son las primeras en usarlo:
`install_android_tools`/`install_flutter_sdk` con un campo (`install_dir`),
`install_android_packages`/`install_android_sdk` con tres (`install_dir` cuando aplica,
`api_level`, `build_tools`).

---

## 8. Estado

`registry.implemented()` devuelve 48 capacidades con `func` real (0 stubs) — ver
[atomicas.md §5](atomicas.md). Este documento no agrega capacidades nuevas: es el índice de qué
función vive dónde, para no tener que grepear `core/tasks/` cada vez que hace falta ubicar una.
