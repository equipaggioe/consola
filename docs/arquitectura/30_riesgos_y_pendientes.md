# 30 · Riesgos, deuda y pendientes

El único lugar donde vive lo que falta. Un pendiente se **borra** de acá en el commit que lo resuelve; no se tacha.

## 1. Marcado como provisional en el código

Solo lo que el propio código declara incompleto.

| Punto | Qué dice el código |
|---|---|
| **La bitácora no existe** | `ui/tab_panel.py`: «La bitacora todavia no existe (`core/store.py`)». `ctx.note()` está implementado y hay 18 llamadas repartidas en siete módulos de `core/tasks/`; hasta que exista el almacén, cada nota se imprime en la consola con un `✱` y se pierde al cerrar |
| **No hay botón de Detener** | `ui/task_runner.py`: «el boton de Detener todavia no existe en la UI, pero cuando exista no debe encontrarse con una tarea dormida». Se detiene cerrando la pestaña, o con «Limpiar» si hay un túnel ([11](11_ejecucion_de_tareas.md) §7) |
| **`CADDY_ROUTES`** | `core/vps.py::route_lines` lee ese nombre viejo como respaldo de `PUBLIC_ROUTES`, «para que los repos que ya la tenían escrita no se queden sin tabla». Es el único puente a un formato anterior que queda en el código |
| **`projects/order`** | `ui/project_store.py` declara la clave vieja de `QSettings` y solo la borra en `clear()`. No se lee en ningún lado |
| **La barra de estado no muestra servicios de fondo** | `WorkspaceStatusBar.add_service` existe y nadie la llama. Un túnel Postgres vivo no aparece ahí |

## 2. Hallazgos de la verificación

Encontrados al leer el código para esta serie, **sin confirmar**. No se tratan como defectos hasta que alguien los confirme.

| # | Hallazgo | Evidencia |
|---|---|---|
| H1 | **`ctx.progress()` no llega a ninguna parte.** `TaskRunner` crea el `TaskContext` sin `progress_sink`, así que el avance de la descarga del SDK —la única que lo emite, cientos de megas— se descarta en silencio. El docstring de `TaskRunner` lo nombra entre los canales que puentea | `ui/task_runner.py::run`, `core/tasks/utils.py::_download` |
| H2 | **«Actualizar Cloudflare» no usa la IP detectada.** La función tiene `ip_mode`, `custom_ip`, `ttl` y `proxied`, y el catálogo no declara ningún eje: corre siempre con `ip_mode='vps'`, o sea con `VPS_IP`. La descripción del botón dice «a la IP pública actual», y `detect_public_ip` queda sin alcanzar | `core/catalog.py` (registro de `update_cloudflare`), `core/tasks/utils.py::update_cloudflare` |
| H3 | **«Ver logs» no ofrece sus filtros.** `view_logs` acepta `lines`, `since`, `priority` y `grep`, y `vps.journal_command` los arma; el catálogo solo declara `service` y `follow`, así que siempre son 200 líneas sin filtrar | `core/catalog.py`, `core/tasks/vps_server.py::view_logs` |
| H4 | **«Migrar» no deja escribir el mensaje de la revisión.** `migrate_db(message=...)` existe y no tiene eje: toda revisión autogenerada se llama `auto` | `core/catalog.py`, `core/tasks/database.py::migrate_db` |
| H5 | **«Backup DB» no deja elegir cuántos respaldos conservar.** `backup_database(keep=7)` sin eje | `core/catalog.py`, `core/tasks/database.py::backup_database` |
| H6 | **El paso `push` de `publish_code`/`update_remote` arranca marcado en el panel y en `False` en la firma.** El catálogo lo declara sin `default=False`, así que la casilla viene marcada; la firma tiene `push: bool = False`, que es lo que vale cuando la llama `bootstrap_vps`. Los dos comportamientos parecen deliberados, pero el mismo nombre significa cosas distintas en cada camino | `core/catalog.py::PUBLISH_CODE_STEPS`, `core/tasks/vps_server.py` |

## 3. Pendientes abiertos

### Decididos y sin construir

| Qué | ADR | Plan |
|---|---|---|
| Bitácora, historial y presets en un SQLite de la máquina (`core/store.py`) | — | — |
| Que la confirmación escrita de un destructivo sea **el nombre del repo** y no una palabra fija, para que el automatismo no erosione la comprobación | [0018](../adr/0018-seguro-por-repo-y-objetivo.md) | — |
| Botón de Detener en la pestaña | [0005](../adr/0005-todo-pasa-por-taskcontext.md) | — |
| Capturas de pantalla publicables de las apps de un repo | — | [capturas.md](../planes/capturas.md) |
| `build_binary` con eje `many` descubierto y `install_python_deps` | — | [apps-python.md](../planes/apps-python.md) |

### Sin decidir

- **El repo que es su propia app.** `resolve_entrypoint` cae en la raíz del repo cuando no hay ningún `python-app` que descubrir. Falta elegir entre reconocer la raíz como app en `_detect` o conservar el campo de texto como escape ([planes/apps-python.md](../planes/apps-python.md) §3.3).
- **`API_URL` gana sobre el backend de la sesión en `run_mobile`.** Con un backend local corriendo y `API_URL` apuntando al VPS, la app del emulador va al VPS. Es lo que hacía el script original.
- **`BACKEND_WAIT = 90 s`** es un número puesto a ojo para un uvicorn con `--reload` y base remota por túnel. Falta uso real para saber si sobra o falta.
- **El explorador conecta como el rol de la aplicación.** Una tabla sin `GRANT` aparece en el árbol —sale de `pg_catalog`— pero sus datos dan «permission denied». Conectar como superusuario lo vería todo, pero en remoto ese canal es `psql` por SSH y no el driver ([ADR-0015](../adr/0015-explorador-de-solo-lectura.md)).
- **Una sola base por repo.** `DB_NAME` es una. Si un repo tuviera dos sería otro eje, y no hace falta decidirlo antes de que pase.
- **Los `scripts/` de referencia.** 51 archivos que nadie ejecuta y que ninguna capacidad necesita ya. Borrarlos es una decisión aparte de esta serie ([ADR-0001](../adr/0001-reimplementar-no-ejecutar-scripts.md)).

### Sin verificar

Construido y nunca probado en condiciones reales:

- La **instalación completa de los SDK** de punta a punta: bajar los cientos de megas, escribir el registro o el perfil y que el emulador acelere. Las URL y los hashes sí se verificaron contra las fuentes oficiales.
- `configure_caddy` y `configure_coturn` **contra un VPS real**: el Caddyfile se prueba por su función sin efectos, no contra Caddy.
- `git_force_origin_from_vps`: la deploy key que instala `setup_github_ssh` suele ser de solo lectura, así que este botón puede fallar con el error de git sin que haya forma de saberlo antes de intentarlo. Lo dice su propio docstring.
- Los builds de **escritorio, macOS e iOS**: `BUILD_PLATFORMS` los declara y el eje solo ofrece los del sistema anfitrión.

## 4. Deuda estructural declarada

- **No hay pruebas automatizadas.** Ni un `test_*.py` en el repositorio, aunque quedó un `.pytest_cache/`. Todo el diseño está pensado para poder probarse sin ventana —`core/` no importa Qt, `_caddyfile` y `parse_routes` no tienen efectos, `AxisDef` es lógica pura sobre sus valores— y nada de eso se ejercita.
- **La interfaz asume una sola ventana.** `favorites`, `section_visibility` y `project_store` escriben en `QSettings` global, sin instancia.
- **`ui/tab_panel.py` tiene 1.511 líneas** y concentra el espacio de trabajo entero: sub-pestañas, acordeón, barra de estado, despacho de la ejecución y los diálogos de las preguntas.
- **La app móvil solo se ejecuta contra Android.** `run_mobile` busca emuladores Android y `pick_emulator` filtra por `targetPlatform` que empiece con `android`.
- **Windows no multiplexa SSH** (`core/ssh.py::_control_args`), así que cada consulta remota paga un handshake nuevo contra un timeout de 30 s. Por eso hay funciones que agrupan preguntas que se contestan juntas (`_remote_state`), y no es microoptimización.

## 5. Glosario

| Término | Qué es en Consola |
|---|---|
| **Capacidad** | Una acción del catálogo: su declaración (`Capability`) más su función |
| **Atómica / compuesta** | Una responsabilidad / varias atómicas encadenadas. `◦` y `◈` en la interfaz |
| **Eje** (`AxisDef`) | Algo que se elige en cada corrida. Su `name` es el nombre del parámetro |
| **Paso** (`Step`) | Una casilla de una compuesta. Su `id` es el nombre del booleano |
| **Faceta** (`Facet`) | Una parte de un valor compuesto, con lista propia en el panel |
| **Eje descubierto** | Sus valores salen de mirar el repo abierto |
| **Eje consultado** | Sus valores salen de preguntarle al SDK o al VPS |
| **Payload** | Lo que el panel devuelve, agrupado por tipo de control; y también un programa que viaja por `-c` |
| **Ámbar** | El botón existe pero no puede correr: le faltan claves de configuración |
| **Objetivo** (del seguro) | Un tipo de cosa que un destructivo puede romper: el VPS, la base, otros repos… |
| **Endpoint** | Una URL que una tarea publicó, con su estado (`starting`/`ready`/`down`) |
| **Fanout** | Repartir los valores marcados de un eje en una pestaña cada uno |
| **Compuesta concurrente** | Sus pasos se lanzan a la vez, uno por pestaña, y ninguno termina |
| **Ámbito** (`scope`) | `local` o `remoto` para una base; `repo` o `machine` para una capacidad |
| **Objetivo de compilación** (`Target`) | Un subproyecto del repo: una SPA, una app móvil, el servidor |
| **Característica** (del repo) | Algo que el repo tiene o no tiene, y decide si un paso existe. Hoy solo `migrations` |
| **Runner** | El intérprete de Python del proyecto, con su directorio y su base |
| **Simulacro** | Modo de un destructivo que solo lista lo que haría |
