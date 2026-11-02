# 30 · Riesgos, deuda y pendientes

El único lugar donde vive lo que falta. Un pendiente se **borra** de acá en el commit que lo resuelve; no se tacha.

## 1. Marcado como provisional en el código

Solo lo que el propio código declara incompleto.

| Punto | Qué dice el código |
|---|---|
| **La bitácora no existe** | `ui/tab_panel.py`: «La bitacora todavia no existe (`core/store.py`)». `ctx.note()` está implementado y hay 18 llamadas repartidas en siete módulos de `core/tasks/`; hasta que exista el almacén, cada nota se imprime en la consola con un `✱` y se pierde al cerrar |
| **No hay botón de Detener** | `ui/task_runner.py`: «el boton de Detener todavia no existe en la UI, pero cuando exista no debe encontrarse con una tarea dormida». Se detiene cerrando la pestaña, o con «Limpiar» si hay un túnel ([11](11_ejecucion_de_tareas.md) §7) |
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
| H8 | **El ámbito remoto de la base no encuentra nada en un VPS de canone.** Corre el Python de `<VPS_DEPLOY_DIR>/<repo>`, que en ese VPS no existe, y usa `sudo -n` | `core/runner.py::resolve`, `core/vps.py::postgres_port`, `core/database.py` |

| H10 | **«Control del servicio» no marca error si `sudo` falla en una consulta.** Con `status`, `is-active` e `is-enabled` el código de salida no corta, porque `systemctl` responde distinto de cero cuando la unidad está parada. Con la contraseña equivocada, el log dice `sudo: 2 incorrect password attempts` y la tarea termina bien. Probado el 2026-11-02 | `core/tasks/vps_server.py::systemd_action` |
| H12 | **Los secretos se ven en el formulario.** «Contraseña de sudo» y los demás campos con `secret=True` se muestran en claro en la configuración del repo. Visto el 2026-11-02 | `ui/env_panel.py` |
| H11 | **Una versión que no arrancó no se puede volver a desplegar.** Si la salud falla y `current` vuelve a la anterior, su carpeta queda en `releases/`, y pedirla otra vez responde `already exists`: hay que publicar otra. Comprobado el 2026-11-02 con `v0.1.3` de prueba | `deploy.py` de canone |
| H9 | **«Generar migración» escribe una revisión vacía si el modelo no cambió.** Su docstring promete `None` y el aviso «El modelo no cambio», pero Alembic genera el archivo igual: corrido el 2026-11-02 contra `equipaggio`, dejó un `upgrade` sin operaciones | `core/tasks/database.py::generate_migration` |

## 3. Pendientes abiertos

### Decididos y sin construir

| Qué | ADR | Plan |
|---|---|---|
| Bitácora, historial y presets en un SQLite de la máquina (`core/store.py`) | — | — |
| Que la confirmación escrita de un destructivo sea **el nombre del repo** y no una palabra fija, para que el automatismo no erosione la comprobación | [0018](../adr/0018-seguro-por-repo-y-objetivo.md) | — |
| Botón de Detener en la pestaña | — | — |
| Capturas: marcos de dispositivo, y la landing leyendo el manifiesto (del repo) | [0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md) | [capturas.md](../planes/capturas.md) |
| `build_binary` con eje `many` descubierto y `install_python_deps` | — | [apps-python.md](../planes/apps-python.md) |
| «Instalar receptora» y «Pedir respaldo». Pendiente por decisión del 2026-11-02. **Hasta entonces, un VPS de canone no tiene respaldo:** el volcado corre solo cuando la receptora lo pide, y «Ver eventos» dice «último respaldo: ninguno» | [0059](../adr/0059-desplegar-con-los-programas-de-canone.md) | [despliegue_canone.md](../planes/despliegue_canone.md) |

### Sin decidir

- **La base local de un repo de canone está dos veces.** `DATABASE_URL` para sus credenciales, y `DB_USER`, `DB_NAME` y `DB_PASSWORD`, que el panel sigue pidiendo en «Levantar backend» y «Correr migraciones» y que leen los demás botones de base ([ADR-0069](../adr/0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md)).
- **«Configurar base de datos» crea un rol, no los dos de canone.** Comprobado el 2026-11-02: crea `DB_USER` como dueño de `DB_NAME`, y `credentials-migrate/` entra como `<rol>_owner`, que hay que crear a mano. Además, los botones de base van al PostgreSQL de `postgresql.conf` de la instalación (5434 aquí), y `DATABASE_URL` puede apuntar a otro (5440 en `equipaggio`).
- **`credentials-migrate/` no está en `plantilla/.gitignore` de canone.** Un repo nuevo corta hasta agregarla.
- **Un campo `turn_secret` en desarrollo.** `install.py` lo escribe en el VPS, y `config.env` no tiene de dónde darlo: «Levantar backend» cortaría pidiendo `TURN_SECRET`. Hoy ningún repo de canone lo declara.
- **«Compilar ejecutable» y su publicación.** Sigue subiendo el ejecutable a `VPS_DEPLOY_DIR` por `scp`, con el número de versión y el manifiesto de release, como hacía el despliegue propio ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)). Falta decidir si lo empaqueta el CI ([planes/despliegue_canone.md](../planes/despliegue_canone.md) §3).
- **El ámbito remoto de los botones de base que lo conservan.** «Reconstruir base», «Borrar base y rol», «Reiniciar historial de migraciones», los seeders, «Habilitar extensiones», «Explorar datos» y «Abrir túnel a Postgres» alcanzan la base del VPS por túnel o por SSH, y contra un VPS de canone no funcionan. Comprobado el 2026-11-02 con «Habilitar extensiones», «Explorar datos» y el túnel, que cortan con `sudo: a password is required`, y con los seeders y las migraciones, que piden `VPS_DEPLOY_DIR`. Hacen falta; la solución se busca primero en canone ([ADR-0060](../adr/0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md), [planes/despliegue_canone.md](../planes/despliegue_canone.md) §5).
- **La carpeta de salida del build web de Flutter** (`BUILD_OUT_WEB`): el plan la sacaba, y la plataforma web se queda sin decidir cómo sigue.
- **Íconos que «Generar íconos» no cubre.** El splash de Flet (`src/assets/splash_android.png` de banditore), el ícono de ventana de las apps de escritorio (es código de cada app), y las imágenes del logo dentro de la app Flutter: `vettore/mobile/assets/brand/logomark.png` y `logo.png`, que usan la pantalla de bloqueo, el registro y la barra principal. No se sabe si alguien las regenera; falta decidir si entran en el botón ([ADR-0056](../adr/0056-cada-tecnologia-declara-donde-va-su-icono.md)).
- **Apps que no declaran dónde va su ícono.** posta/backoffice tiene el `favicon.svg` de la plantilla sin ningún `<link>` que lo use, y posta no tiene logo SVG: declararlo hoy pondría el logo de Svelte en la pestaña. posta/terminal usa la sección vieja `flutter_icons:`, que Consola no lee. banditore/spikes/background_gps no tiene `icon.png`, y es código desechable.
- **posta/clientes no sigue la forma de las PWA.** Escribe el manifest dentro de `vite.config`, y la corrida sobre ella corta ([ADR-0057](../adr/0057-el-manifest-de-la-pwa-es-un-archivo-estatico.md)). Además declara un `favicon.png` sin `sizes` que no existe, un `apple-touch-icon` a `/icons/icon-192x192.png` que tampoco existe, y un `static/manifest.json` que ningún `<link>` usa.
- **El repo que es su propia app.** `resolve_entrypoint` cae en la raíz del repo cuando no hay ningún `python-app` que descubrir. Falta elegir entre reconocer la raíz como app en `_detect` o conservar el campo de texto como escape ([planes/apps-python.md](../planes/apps-python.md) §3.3).
- **`API_URL` gana sobre el backend de la sesión en `run_mobile`.** Con un backend local corriendo y `API_URL` apuntando al VPS, la app del emulador va al VPS. Es lo que hacía el script original.
- **`BACKEND_WAIT = 90 s`** es un número puesto a ojo para un uvicorn con `--reload` y base remota por túnel. Falta uso real para saber si sobra o falta.
- **El explorador conecta como el rol de la aplicación.** Una tabla sin `GRANT` aparece en el árbol —sale de `pg_catalog`— pero sus datos dan «permission denied». Conectar como superusuario lo vería todo, pero en remoto ese canal es `psql` por SSH y no el driver ([ADR-0015](../adr/0015-explorador-de-solo-lectura.md)).
- **Dónde vive la parte Dart del kit de la cámara**: un paquete de Consola con dependencia `path:` o una copia por app Flutter ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
- **Dónde vive la parte Flet del kit de la cámara.** `banditore/demo/camera/flet_camera.py` corre una app Flet en modo web y le da al recorrido `tap`, `wait_for_text` y `shoot`. No depende de banditore, salvo por cómo siembra la sesión. Se importa desde la app, así que tampoco puede llegar como ruta en `--kit` ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
- **«Vaciar VPS» con el programa que desinstala.** Pendiente por decisión del 2026-11-02, y espera a que canone lo traiga ([ADR-0062](../adr/0062-vaciar-vps-sale.md)). Hasta entonces, desarmar un VPS es reinstalarlo desde el proveedor.
- **Volver a una versión reciente.** «Desplegar versión» ofrece las cinco últimas, pero `deploy.py` se niega con `already exists` si la carpeta sigue en el VPS: comprobado el 2026-11-02, con `v0.1.1` activa y pidiendo `v0.1.0`. Hoy, ante una versión mala, se publica otra. Volver pide un programa en canone ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)).
- **`OFFLINE_KEY` de esta máquina es de prueba.** Es `~/.ssh/vps_offline_prueba`, guardada en esta misma computadora, y la clave es una sola para todos los VPS. Antes de un VPS real hay que cambiarla por una guardada fuera; en un VPS ya instalado, `install.py` solo agrega llaves y la de prueba queda hasta quitarla a mano.
- **Una sola base por repo.** `DB_NAME` es una. Si un repo tuviera dos sería otro eje, y no hace falta decidirlo antes de que pase.

### Sin verificar

Construido y nunca probado en condiciones reales:

- **La primera instalación en una máquina recién creada, desde la ventana.** El 2026-11-02 se apretaron en la ventana de Consola, con clics simulados, «Configurar VPS» (sobre un VPS ya instalado), «Instalar paquetes base», «Cargar credenciales», «Control del servicio», «Ver logs del servicio», «Health check», «Ver eventos», «Ejecutar comando», «Desplegar versión», «Levantar backend» y «Correr migraciones». La primera corrida de `install.py` como root corrió sin la ventana, y la huella nueva se simuló olvidando la anterior. «Publicar versión» corrió por el panel, sin mostrar la ventana.
- **«Abrir sesión SSH».** Abre una terminal externa, y no se probó.
- **«Actualizar Cloudflare» cuando tiene que cambiar el registro.** Corrió el 2026-11-02 con el registro ya correcto y con uno que no existe. La escritura nunca corrió, porque el permiso de Claude Code bloquea los cambios de DNS. Corre con `proxied=True`, que con dos niveles de subdominio dejaría sin certificado al proxy de Cloudflare *(sin confirmar)*.

- **Consola en Linux**, entera ([ADR-0048](../adr/0048-las-diferencias-de-sistema-viven-en-host.md)). Hay que correr `pytest` allá —las tres pruebas de `tests/test_host.py` marcadas `solo_posix` se saltan en Windows— y una pasada a mano: detener una tarea y una «App Python» que relanza al guardar, respaldar y restaurar contra la base local, «SSH Login», instalar los SDK y ver la fuente de la consola.
- La **instalación completa de los SDK** de punta a punta: bajar los cientos de megas, escribir el registro o el perfil y que el emulador acelere. Las URL y los hashes sí se verificaron contra las fuentes oficiales.
- **El revelado para tiendas con capturas reales.** Las reglas de Play y las medidas de App Store se tomaron de las fichas oficiales el 2026-09-24, pero ninguna tanda se subió a una tienda. El tope de recorte de App Store (`max_crop` 3 %) es un número elegido para que un teléfono 1080×2400 pase; nadie miró todavía qué se pierde en esa franja.
- Los builds de **escritorio, macOS e iOS**: `BUILD_PLATFORMS` los declara y el eje solo ofrece los del sistema anfitrión.
- **«Respaldar» y «Restaurar» con PostGIS y con los roles de canone.** Corrieron el 2026-11-02 contra una base aparte con `pg_trgm`: el respaldo y la restauración recuperan los datos, y la extensión sigue. Falta una base con PostGIS y una cuyo dueño sea `<app>_owner` ([ADR-0060](../adr/0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md), [ADR-0047](../adr/0047-restaurar-es-un-destructivo-del-seguro-por-repo.md)).

## 4. Deuda estructural declarada

- **Las pruebas cubren tres islas de la lógica pura.** `tests/` tiene dos archivos de esa clase —`parse_services`/`unit_name` y el contraste de las paletas— y el criterio que los une está escrito en sus docstrings: se prueba lo que no toca red ni disco. Lo que Consola ejecuta de verdad (SSH, `subprocess`, el driver de Postgres) no se prueba acá, y no es un olvido: son efectos sobre máquinas y repos ajenos. Lo que sí queda sin ejercitar es el resto de la superficie pura, que es grande: `AxisDef` y `kwargs_from` (`core/registry.py`), `protection.decide`, `Config` y sus defaults dinámicos (`core/envfile.py`), `core/targets.py` y `core/versioning.py`.
- **La interfaz asume una sola ventana.** `favorites`, `section_visibility` y `project_store` escriben en `QSettings` global, sin instancia.
- **`ui/tab_panel.py` tiene 1.511 líneas** y concentra el espacio de trabajo entero: sub-pestañas, acordeón, barra de estado, despacho de la ejecución y los diálogos de las preguntas.
- **La app móvil solo se ejecuta contra Android.** `run_mobile` busca emuladores Android y `pick_emulator` filtra por `targetPlatform` que empiece con `android`.
- **En Linux un túnel sobrevive a una caída de Consola.** `PosixHost.bind_to_app` no hace nada; al cerrar normalmente lo apaga `TabPanel.shutdown()`. El camino es `PR_SET_PDEATHSIG` lanzando los túneles desde un hilo que viva lo que la aplicación ({ADR}, Descartado).
- **En Linux el PATH de los SDK va a `~/.bashrc` o `~/.zshrc`**, que solo leen las terminales. Consola abierta desde el menú del escritorio no lo ve hasta que se lanza desde una terminal.
- **Windows no multiplexa SSH** (`core/host.py::WindowsHost.ssh_multiplex`), así que cada consulta remota paga un handshake nuevo contra un timeout de 30 s. Por eso hay funciones que agrupan preguntas que se contestan juntas (`vps.installed_services`), y no es microoptimización.

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
