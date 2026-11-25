# 30 · Riesgos, deuda y pendientes

El único lugar donde vive lo que falta. Un pendiente se **borra** de aquí en el commit que lo resuelve; no se tacha.

## 1. Marcado como provisional en el código

Solo lo que el propio código declara incompleto.

| Punto | Qué dice el código |
|---|---|
| **La bitácora no existe** | `widgets/tab_panel.py`: «La bitacora todavia no existe (`services/store.py`)». `ctx.note()` está implementado y hay 18 llamadas repartidas en siete módulos de `services/tasks/`; hasta que exista el almacén, cada nota se imprime en la consola con un `✱` y se pierde al cerrar |
| **No hay botón de Detener** | `services/task_runner.py`: «el boton de Detener todavia no existe en la UI, pero cuando exista no debe encontrarse con una tarea dormida». Se detiene cerrando la pestaña, o con «Limpiar» si hay un túnel ([11](11_ejecucion_de_tareas.md) §7) |
| **La barra de estado no muestra servicios de fondo** | `WorkspaceStatusBar.add_service` existe y nadie la llama. Un túnel Postgres vivo no aparece ahí |

## 2. Hallazgos de la verificación

Encontrados al leer el código para esta serie, **sin confirmar**. No se tratan como defectos hasta que alguien los confirme.

| # | Hallazgo | Evidencia |
|---|---|---|
| H1 | **`ctx.progress()` no llega a ninguna parte.** `TaskRunner` crea el `TaskContext` sin `progress_sink`, así que el avance de la descarga del SDK —la única que lo emite, cientos de megas— se descarta en silencio. El docstring de `TaskRunner` lo nombra entre los canales que puentea | `services/task_runner.py::run`, `services/tasks/utils.py::_download` |
| H3 | **«Ver logs» no ofrece sus filtros.** `view_logs` acepta `lines`, `since`, `priority` y `grep`, y `vps.journal_command` los arma; el catálogo solo declara `service` y `follow`, así que siempre son 200 líneas sin filtrar | `services/catalog.py`, `services/tasks/vps_server.py::view_logs` |
| H4 | **«Migrar» no deja escribir el mensaje de la revisión.** `migrate_db(message=...)` existe y no tiene eje: toda revisión autogenerada se llama `auto` | `services/catalog.py`, `services/tasks/database.py::migrate_db` |
| H8 | **«Levantar backend» con ámbito remoto no llega a la base de un VPS de canone.** Pregunta el puerto con `sudo -n`, que pide contraseña, y entra por TCP con `DB_USER` y `DB_PASSWORD`, cuando los roles de canone entran por `peer` y sin contraseña. Solo lo usa un repo sin el `Settings` de canone | `services/database.py::connect`, `services/vps.py::postgres_port`, `services/tasks/launchers.py::serve_backend` |
| H10 | **«Control del servicio» no marca error si `sudo` falla en una consulta.** Con `status`, `is-active` e `is-enabled` el código de salida no corta, porque `systemctl` responde distinto de cero cuando la unidad está parada. Con la contraseña equivocada, el log dice `sudo: 2 incorrect password attempts` y la tarea termina bien. Probado el 2026-11-02 | `services/tasks/vps_server.py::systemd_action` |
| H11 | **Una versión que no arrancó no se puede volver a desplegar.** Si la salud falla y `current` vuelve a la anterior, su carpeta queda en `releases/`, y pedirla otra vez responde `already exists`: hay que publicar otra. Comprobado el 2026-11-02 con `v0.1.3` de prueba. Canone lo cambió en `main` (ADR-0123 de canone), sin probarlo en un VPS. | `deploy.py` de canone |
| H9 | **«Generar migración» escribe una revisión vacía si el modelo no cambió.** Su docstring promete `None` y el aviso «El modelo no cambio», pero Alembic genera el archivo igual: corrido el 2026-11-02 contra `equipaggio`, dejó un `upgrade` sin operaciones | `services/tasks/database.py::generate_migration` |
| H13 | **El avance de cmdline-tools solo llega al terminar.** `dl.google.com` deja el total en `-1` hasta el último aviso, y `_download` descarta los avisos sin total: 1 de 72, medido el 2026-11-04. La descarga de Flutter sí trae el total: 47 avisos en 5 s. No se investigó por qué difieren. Hoy no se ve, por H1 | `services/tasks/utils.py::_download` |
| H16 | **Ejecutar podría no mostrar el foco del teclado.** Su parte (`RUN_BUTTON`) rellena con `primary` y no declara `focus`, así que el anillo de 2 px va en `Highlight`, que también es `primary`. Los filtros de la consola tenían lo mismo: lo marcó `test_focus_shows` y se arregló con `CHIP_ON`. La prueba no lo ve en Ejecutar porque en su ventana está inactivo | `theme.py::RUN_BUTTON`, `widgets/params_panel.py` |
| H17 | **Una ruta de repo larga ensancha la ventana.** En la ventana de `tests/conftest.py`, con una carpeta temporal de nombre largo, la ventana no baja de 968 px en el commit 28d63a5: más que los 960 px del 200 %. Medido el 2026-11-23. No se buscó qué control muestra la ruta | `tests/test_accessibility.py::test_text_at_200` con un id de prueba largo |

## 3. Pendientes abiertos

### Reportados en uso

- **Arrancar tarda unos 8 s** con ocho repos abiertos. Visto el 2026-11-09. Medido sin pantalla ese día: 5,7 s son construir los ocho `TabPanel` de entrada, y unos 2 s, la hoja de estilo que `MainWindow._apply_window_border` ponía en el `centralWidget`, que ya no existe. Sin medir después de quitarla.

### Pedidos concretos sin hacer

- **Un botón que cambie la llave de un VPS.** Pedido el 2026-11-24. Debe agregar la llave nueva de `VPS_KEY_NAME` a `/etc/ssh/authorized_keys/<admin>` y a `/etc/<app>/allowed_signers`, comprobar que entra con ella y después quitar la vieja de los dos archivos. Hoy no hay forma de hacerlo desde Consola: `install.py` solo agrega llaves (`add_signers`) y «Poner la llave» solo entra con la contraseña de root si la llave no entra. Ese día se hizo a mano en equipaggio: entró `vps_xs1` y salió `vps_xs152`. Sin decidir: si el programa que quita llaves va en `plantilla/infra/` de canone o en Consola.

### Decididos y sin construir

| Qué | ADR | Plan |
|---|---|---|
| «Compilar ejecutable»: empaquetar solo en CI con `pyside6-deploy`, sin PyInstaller, sin subir al VPS, sin número de versión ni manifiesto. Sale el ADR-0024 y cambian el 0025, el 0026 y el punto 4 del 0056 | [0074](../adr/0074-lo-que-cambia-un-vps-y-canone-no-hace-va-primero-a-canone.md) | [despliegue_canone.md](../planes/despliegue_canone.md) |
| Bitácora, historial y presets en un SQLite de la máquina (`services/store.py`) | — | — |
| Que la confirmación escrita de un destructivo sea **el nombre del repo** y no una palabra fija, para que el automatismo no erosione la comprobación | [0018](../adr/0018-seguro-por-repo-y-objetivo.md) | — |
| Botón de Detener en la pestaña | — | — |
| Capturas: marcos de dispositivo, y la landing leyendo el manifiesto (del repo) | [0049](../adr/0049-la-camara-de-capturas-es-un-script-del-repo.md) | [capturas.md](../planes/capturas.md) |
| `build_binary` con eje `many` descubierto y `install_python_deps` | — | [apps-python.md](../planes/apps-python.md) |
| «Instalar receptora» y «Pedir respaldo». Pendiente por decisión del 2026-11-02. **Hasta entonces, un VPS de canone no tiene respaldo:** el volcado corre solo cuando la receptora lo pide, y «Ver eventos» dice «último respaldo: ninguno» | — | [despliegue_canone.md](../planes/despliegue_canone.md) |

### Sin decidir

- **Calcular `APP_ORIGINS` y `SMS_HASHES`.** Por evaluar, anotado el 2026-11-25. Son de una app de Android con passkey o con código por SMS (`autenticacion.md` de canone), y hoy se escriben a mano en `config.env`. Salen del certificado que firma la app instalada: CI firma con la llave de subida y Play genera el APK universal que el release lleva como `<pieza>.apk`. Propuesta: Consola baja ese APK, lee su certificado con `apksigner` y escribe las dos claves. Sin confirmar: que el certificado de ese APK sea el de la app que Play instala. Ningún repo declara todavía esos campos: se evalúa cuando una app de Android adopte la plantilla.
- **El resto de las secciones informativas.** En Deducido, el nombre de la app, el dueño, la carpeta de despliegue y la memoria de Valkey; debajo de la consola, el historial de corridas, los artefactos y los procesos vivos. Cada una espera una decisión: [secciones_informativas.md](../planes/secciones_informativas.md).
- **Subir a Play las capturas de la ficha de la tienda.** Hoy se suben a mano en Play Console: «Revelar capturas» las deja en `<SHOTS_DIST>/play/` con su `screenshots.json`, que dice qué cambió desde la vez anterior, y `scripts/play.py` de canone sube solo el AAB. La API de publicación de Play también sube las imágenes de la ficha. Propuesta: un paso de Consola después de «Revelar capturas», porque las imágenes solo existen en esta máquina, ignoradas, y subirlas es igual en todos los repos. Pide la cuenta de servicio de Play en la máquina, que hoy solo usa el CI.
- **La base local de un repo de canone está dos veces.** `DATABASE_URL` para sus credenciales, y `DB_USER`, `DB_NAME` y `DB_PASSWORD`, que el panel sigue pidiendo en «Levantar backend» y «Correr migraciones» y que leen los demás botones de base ([ADR-0069](../adr/0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md)).
- **«Configurar base de datos» crea un rol, no los dos de canone.** Comprobado el 2026-11-02: crea `DB_USER` como dueño de `DB_NAME`, y `credentials/migrate/` entra como `<rol>_owner`, que hay que crear a mano. Además, los botones de base van al PostgreSQL de `postgresql.conf` de la instalación (5434 aquí), y `DATABASE_URL` puede apuntar a otro (5440 en `equipaggio`).
- **«Quitar acceso SSH» edita `authorized_keys` en el VPS**, y canone no trae un programa para eso: incumple la regla del [15](15_vps_y_despliegue.md) §2. Falta en canone.
- **La carpeta de salida del build web de Flutter** (`BUILD_OUT_WEB`): el plan la sacaba, y la plataforma web se queda sin decidir cómo sigue.
- **Íconos que «Generar íconos» no cubre.** El splash de Flet (`src/assets/splash_android.png` de banditore), el ícono de ventana de las apps de escritorio (es código de cada app), y las imágenes del logo dentro de la app Flutter: `vettore/mobile/assets/brand/logomark.png` y `logo.png`, que usan la pantalla de bloqueo, el registro y la barra principal. No se sabe si alguien las regenera; falta decidir si entran en el botón ([ADR-0056](../adr/0056-cada-tecnologia-declara-donde-va-su-icono.md)).
- **Apps que no declaran dónde va su ícono.** posta/backoffice tiene el `favicon.svg` de la plantilla sin ningún `<link>` que lo use, y posta no tiene logo SVG: declararlo hoy pondría el logo de Svelte en la pestaña. posta/terminal usa la sección vieja `flutter_icons:`, que Consola no lee. banditore/spikes/background_gps no tiene `icon.png`, y es código desechable.
- **posta/clientes no sigue la forma de las PWA.** Escribe el manifest dentro de `vite.config`, y la corrida sobre ella corta ([ADR-0057](../adr/0057-el-manifest-de-la-pwa-es-un-archivo-estatico.md)). Además declara un `favicon.png` sin `sizes` que no existe, un `apple-touch-icon` a `/icons/icon-192x192.png` que tampoco existe, y un `static/manifest.json` que ningún `<link>` usa.
- **El repo que es su propia app.** `resolve_entrypoint` cae en la raíz del repo cuando no hay ningún `python-app` que descubrir. Falta elegir entre reconocer la raíz como app en `_detect` o conservar el campo de texto como escape ([planes/apps-python.md](../planes/apps-python.md) §3.3).
- **`API_URL` gana sobre el backend de la sesión en `run_mobile`.** Con un backend local corriendo y `API_URL` apuntando al VPS, la app del emulador va al VPS. Es lo que hacía el script original.
- **`BACKEND_WAIT = 90 s`** es un número puesto a ojo para un uvicorn con `--reload` y base remota por túnel. Falta uso real para saber si sobra o falta.
- **El explorador conecta como el rol de la aplicación, y en el VPS como `<app>_read`.** Una tabla sin `GRANT` —en el VPS, `event_log`— aparece en el árbol, porque sale de `pg_catalog`, pero sus datos dan «permission denied». Conectar como superusuario lo vería todo, pero ese canal es `psql` y no el driver ([ADR-0015](../adr/0015-explorador-de-solo-lectura.md)).
- **Un botón para juntar las migraciones en el VPS.** Hoy son seis pasos a mano con los botones que hay ([16](16_base_de_datos.md) §6). Los pasos 3 a 6 podrían ser una compuesta; el 1 y el 2 no, porque el commit es de quien desarrolla. El 2026-11-07 se dejó sin construir.
- **Dónde vive la parte Dart del kit de la cámara**: un paquete de Consola con dependencia `path:` o una copia por app Flutter ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
- **Dónde vive la parte Flet del kit de la cámara.** `banditore/demo/camera/flet_camera.py` corre una app Flet en modo web y le da al recorrido `tap`, `wait_for_text` y `shoot`. No depende de banditore, salvo por cómo siembra la sesión. Se importa desde la app, así que tampoco puede llegar como ruta en `--kit` ([ADR-0051](../adr/0051-el-kit-de-la-camara-viaja-en-un-argumento.md)).
- **Volver a una versión reciente.** «Desplegar versión» ofrece las cinco últimas, pero `deploy.py` se niega con `already exists` si la carpeta sigue en el VPS: comprobado el 2026-11-02, con `v0.1.1` activa y pidiendo `v0.1.0`. Hoy, ante una versión mala, se publica otra. Volver pide un programa en canone ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)). Canone lo cambió en `main` (ADR-0123 de canone), sin probarlo en un VPS.
- **`OFFLINE_KEY` de esta máquina es de prueba.** `~/.ssh/vps_offline.pub` es una copia de la pública de `~/.ssh/vps_offline_prueba`, cuya privada está en esta misma computadora, y la clave es una sola para todos los VPS. Antes de un VPS real hay que cambiarla por una guardada fuera; en un VPS ya instalado, `install.py` solo agrega llaves y la de prueba queda hasta quitarla a mano.
- **Una sola base por repo.** `DB_NAME` es una. Si un repo tuviera dos sería otro eje, y no hace falta decidirlo antes de que pase.

### Sin verificar

Construido y nunca probado en condiciones reales:

- **«Verificar con canone», «Actualizar copias de canone» y «Secretos a generar», en la ventana, y una carga con secretos generados en un VPS.** El 2026-11-25 corrieron sin la ventana: los dos primeros contra canone y un clon de `equipaggio`, y el panel y el formulario en las pruebas. La consulta de lo que el VPS ya tiene (`canone.stored_command`) corrió en Debian 13 de WSL, sobre lo que escribe `credentials.py`.
- **La passkey con el backend local.** Las credenciales de desarrollo llevan el `domain` de producción, que es el RP ID: leído en el código, no debería funcionar en `localhost`.
- **Consola en inglés, leída por una persona** ([04](04_conceptos_transversales.md) §10). `en.ts` traduce los 1473 textos, y las pruebas comprueban que ninguno falta ni pierde un `{…}`. El 2026-11-22 la ventana real se abrió en Windows en inglés y en español, y un cliente de UI Automation leyó la cultura `en-US` y `es-ES` en sus 53 elementos. Nadie recorrió todavía la app en inglés mirando si cada texto se entiende, ni los mensajes de las tareas.
- **El icono del binario** ([03](03_ejecucion_y_despliegue.md) §1). `release.yml` corrió en GitHub el 2026-11-22 con dos tags de prueba, que después se borraron con sus releases: pasaron todos los jobs y los dos binarios subieron con su `.sha256`. El primer `.exe` abría también una consola; con `--windows-console-mode=disable` el segundo abre solo la ventana. El icono no se miró en ningún sistema: Nuitka avisa que en Linux no lo usa fuera del modo `app`.
- **Vaciar, migrar y sembrar la base de un VPS de canone** ([16](16_base_de_datos.md) §6): «Reconstruir base» y los seeders con ámbito remoto. Las pruebas cubren qué comandos de `database.py` se mandan y cuándo se corta antes; nada de eso corrió contra un VPS, porque `v0.1.1` de equipaggio, lo único desplegado, no tiene `app.tasks migrate`. Sí se comprobó el 2026-11-07 en `74.208.72.71`, desde Windows y sin la UI: «Configurar VPS» pasa `--development` y deja la marca; «Abrir túnel a Postgres» y «Explorar datos» entran como `equipaggio_read` por el socket, leen las 24 tablas y no pueden leer `event_log`, borrar ni crear tablas; `equipaggio` y `equipaggio_owner` no entran por ese túnel.
- **Los pasos de «Reconstruir base» que cambian con el ámbito, en la ventana.** `ParamsPanel` oculta los del otro ámbito y no los manda: se comprobó el 2026-11-07 con el panel fuera de pantalla (`QT_QPA_PLATFORM=offscreen`), cambiando el ámbito por código, no con clics en la ventana.

- **La primera instalación en una máquina recién creada, desde la ventana.** El 2026-11-02 se apretaron en la ventana de Consola, con clics simulados, «Configurar VPS» (sobre un VPS ya instalado), «Instalar paquetes base», «Cargar credenciales», «Control del servicio», «Ver logs del servicio», «Health check», «Ver eventos», «Ejecutar comando», «Desplegar versión», «Levantar backend» y «Correr migraciones». La primera corrida de `install.py` como root corrió sin la ventana, y la huella nueva se simuló olvidando la anterior. «Publicar versión» corrió por el panel, sin mostrar la ventana.
- **«Instalar paquetes base» con `packages.py` de canone, contra un VPS.** Se comprobó el 2026-11-09 que `packages.py` instala los catorce paquetes con `--extension postgis --turn --logs` en un Debian 13 de WSL, y que el panel muestra la lista de `--list` desde Windows. Que Consola lo suba y lo corra con `sudo` en un VPS no se probó.
- **Desplegar un repo que no sea `equipaggio`.** Solo `equipaggio` se publicó y se desplegó con Consola (`v0.1.0` y `v0.1.1`, en un VPS de prueba). Ningún otro repo de canone se probó.
- **«Vaciar VPS» desde la ventana, y `scripts/infra/uninstall.sh` de canone** ([ADR-0083](../adr/0083-vaciar-vps-corre-uninstall-py-de-canone.md)). El 2026-11-09, sin la ventana, cada nivel corrió contra el VPS de prueba y después «Configurar VPS» lo dejó sirviendo: `/api/health` respondió 204 las tres veces (con «La base», además «Reconstruir base» → migrar). «La máquina» corrió en su forma actual, sin purgar paquetes. `uninstall.sh` corre en el `infra.yml` de canone al empujar.
- **«Poner la llave» contra un VPS nuevo.** El 2026-11-09 corrió contra el sshd de la distribución `CanoneTest` de WSL, entrando como root con contraseña: con `ROOT_PASSWORD`, pedida y equivocada, con una contraseña con `%`, `^`, `&`, `!` y `"`, y otra vez con la llave ya puesta. Falta un VPS recién creado del proveedor y la ventana.
- **«Abrir sesión SSH».** Abre una terminal externa, y no se probó.
- **La comprobación de la raíz del panel en `caddy.sh` de canone.** Aquí no hay Caddy, así que corre por primera vez en `infra.yml` cuando se empuje canone. El arreglo del `Caddyfile` sí se comprobó en el VPS de prueba.

- **Consola en Linux**, con la ventana ([ADR-0048](../adr/0048-las-diferencias-de-sistema-viven-en-host.md)). `pytest` pasó el 2026-11-04 en Debian 13 dentro de WSL, con las tres pruebas `posix_only` de `tests/test_host.py`. Falta una pasada a mano: detener una tarea y una «App Python» que relanza al guardar, respaldar y restaurar contra la base local, «SSH Login», instalar los SDK y ver la fuente de la consola.
- La **instalación completa de los SDK** de punta a punta: escribir el registro o el perfil y que el emulador acelere. El 2026-11-04 `_download` bajó entero el zip de cmdline-tools para Windows, idéntico byte a byte al de `curl`, pasó la verificación con el SHA-256 de la página, y se detuvo a los 5 s durante la descarga de Flutter para Windows.
- **«Actualizar Cloudflare» desde la ventana, con la IP del VPS.** El 2026-11-22 `update_cloudflare` corrió contra el Cloudflare real, sin la ventana, sobre `consola-prueba.equipaggio.net`: creó el registro, lo dejó como estaba al repetir, lo cambió con un PUT y el script lo borró. La IP pública de esta máquina se detectó contra el servicio real. Un token mal formado responde 400, y la tarea muestra el motivo que da Cloudflare. El TTL (automático) sigue sin eje.
- **El revelado para tiendas con capturas reales.** Las reglas de Play y las medidas de App Store se tomaron de las fichas oficiales el 2026-09-24, pero ninguna tanda se subió a una tienda. El tope de recorte de App Store (`max_crop` 3 %) es un número elegido para que un teléfono 1080×2400 pase; nadie miró todavía qué se pierde en esa franja.
- Los builds de **escritorio, macOS e iOS**: `BUILD_PLATFORMS` los declara y el eje solo ofrece los del sistema anfitrión.
- **«Respaldar» y «Restaurar» con PostGIS y con los roles de canone.** Corrieron el 2026-11-02 contra una base aparte con `pg_trgm`: el respaldo y la restauración recuperan los datos, y la extensión sigue. Falta una base con PostGIS y una cuyo dueño sea `<app>_owner` ([ADR-0060](../adr/0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md), [ADR-0047](../adr/0047-restaurar-es-un-destructivo-del-seguro-por-repo.md)).

## 4. Deuda estructural declarada

- **Cambiar `VALKEY_MEMORY` en un VPS ya instalado no se aplica hasta reiniciar Valkey.** «Configurar VPS» corre `install.py`, que escribe el `maxmemory` nuevo y enciende la instancia con `enable --now`, que no reinicia la que ya corre.
- **`config.env` escribe `TURN_IP=` en un repo sin llamadas.** El formulario no la muestra sin `turn_secret` (`Setting.needs`), pero `envfile.render_config` escribe todas las claves del esquema.

- **Las pruebas cubren la lógica pura.** Lo que Consola ejecuta de verdad (SSH, `subprocess`, el driver de Postgres) no se prueba aquí: son efectos sobre máquinas y repos ajenos. Sigue sin ejercitar parte de esa lógica pura: `AxisDef` y `kwargs_from` (`services/registry.py`), `protection.decide`, `services/targets.py` y `services/versioning.py`.
- **La interfaz asume una sola ventana.** `favorites`, `section_visibility` y `project_store` escriben en `QSettings` global, sin instancia.
- **`widgets/tab_panel.py` tiene 1.815 líneas** y concentra el espacio de trabajo entero: sub-pestañas, acordeón, barra de estado, despacho de la ejecución y los diálogos de las preguntas.
- **La app móvil solo se ejecuta contra Android.** `run_mobile` busca emuladores Android y `pick_emulator` filtra por `targetPlatform` que empiece con `android`.
- **En Linux un túnel sobrevive a una caída de Consola.** `PosixHost.bind_to_app` no hace nada; al cerrar normalmente lo apaga `TabPanel.shutdown()`. El camino es `PR_SET_PDEATHSIG` lanzando los túneles desde un hilo que viva lo que la aplicación ([ADR-0048](../adr/0048-las-diferencias-de-sistema-viven-en-host.md), «Descartado»).
- **En Linux el PATH de los SDK va a `~/.bashrc` o `~/.zshrc`**, que solo leen las terminales. Consola abierta desde el menú del escritorio no lo ve hasta que se lanza desde una terminal.
- **Windows no multiplexa SSH** (`services/host.py::WindowsHost.ssh_multiplex`), así que cada consulta remota paga un handshake nuevo contra un timeout de 30 s. Por eso hay funciones que agrupan preguntas que se contestan juntas (`vps.installed_services`), y no es microoptimización.

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
| **Ámbito** (`scope`) | `local` o `remote` para una base; `repo` o `machine` para una capacidad |
| **Objetivo de compilación** (`Target`) | Un subproyecto del repo: una SPA, una app móvil, el servidor |
| **Característica** (del repo) | Algo que el repo tiene o no tiene, y decide si un paso existe. Hoy solo `migrations` |
| **Runner** | El intérprete de Python del proyecto, con su directorio y su base |
| **Simulacro** | Modo de un destructivo que solo lista lo que haría |
