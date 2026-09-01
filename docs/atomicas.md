# Niveles 1 y 2 — atómicas y compuestas en `core/tasks/`

Implementación de los niveles 1 y 2 de [PLAN.md §2](PLAN.md), sobre la plomería documentada en
[nivel-0.md](nivel-0.md). Nueve módulos, ~2.300 líneas, **48 capacidades del catálogo con cuerpo
real** (0 stubs).

---

## 0. Corrección: qué NO es una atómica

Al partir `install_android_sdk`, el criterio del §1 se aplicó mal por un momento: se propuso una
casilla por cada función interna del script (`_resolve_cmdline_tools_release`, `_download`,
`_extract`, `_accept_licenses`...). Eso es la confusión inversa a la que ya resuelve el
contraejemplo de `clean_vps` — aquí ni siquiera son pasos de una compuesta, son **utilidades**
dentro de una sola atómica: nadie va a querer nunca "solo aceptar las licencias" o "solo extraer
el zip" sin lo demás.

La pregunta del §1 (*¿tiene sentido re-ejecutar esto solo?*) sigue siendo la correcta; lo que
faltó fue aplicarla a la granularidad justa. Aplicada bien a Android dio **tres** atómicas, no
siete:

- `install_android_tools` — resolver la versión publicada, descargar, verificar SHA-1,
  descomprimir, dejar el entorno configurado. Todo eso es *un* paso reconocible del dominio
  ("tener las cmdline-tools instaladas"), aunque por dentro llame a media docena de funciones.
- `install_android_packages` — aparte porque *sí* se repite sola: cuando sale una API nueva o un
  repo pide otro `build-tools`, se agrega ese paquete sin volver a bajar el SDK ni tocar el PATH.
- `install_android_hypervisor` — aparte porque es lo único que pide permisos elevados (driver de
  kernel en Windows); separarlo deja a las otras dos sin necesidad de admin.

Ver el detalle completo en [catalogo-funciones.md §3](catalogo-funciones.md#3-catálogo-completo-por-módulo)
y el §4.1 de más abajo.

**Segunda corrección, misma familia: `fetch_dependencies` (`flutter pub get`).** Estaba como paso
de `build_apk` porque el script original lo llamaba antes del build. Pero `flutter build apk`
resuelve dependencias solo cuando `pubspec.yaml` es más nuevo que `.dart_tool/package_config.json`
— y en este flujo el bump acaba de tocar `pubspec.yaml`, así que la resolución ocurre **siempre**,
llamemos o no a `pub get`. El paso no era una atómica de más: era trabajo duplicado con un
encabezado en la consola que hacía parecer que decidía algo.

Se borró (§4.2). El contraste que lo confirma es `install_node_modules`, que **sí** se queda:
`npm run build` no instala nada, así que ahí el paso de dependencias es el único que las trae. La
regla no es "los builders no llevan paso de dependencias" — es que el paso existe cuando la
herramienta no lo hace por ti.

---

## 1. El criterio de corte

La pregunta que decide si un paso interno de un script viejo se convierte en atómica con botón
propio o queda escondido dentro de la compuesta es una sola:

> **¿Tiene sentido re-ejecutar este paso solo, sin repetir el resto?**

Si la respuesta es sí, es una atómica. Los ejemplos reales que motivaron esto:

| Antes | Problema | Ahora |
|---|---|---|
| `android_emulator.py` — un `run()` que bajaba la system image, creaba el AVD, parcheaba `config.ini` y arrancaba | Para arrancar un emulador ya creado había que volver a entrar a la lógica de descarga y creación | `install_system_image` · `create_avd` · `launch_emulator` · `await_emulator` · `stop_emulator` |
| `rebuild_db.py` — un archivo que borraba tablas, reseteaba Alembic, regeneraba la migración inicial, aseguraba particiones y corría dos tandas de seeders | Volver a correr solo los seeders mock obligaba a destruir el esquema | `drop_tables` · `reset_migrations` · `generate_migration` · `apply_migrations` · `ensure_partitions` · `run_seeders` · `run_mock_seeders` |
| `update_remote.py` — 607 líneas en un `main()` | "Solo recopiar los certificados" implicaba rehacer `git pull` + venv + `pip install` | `sync_repository` · `ensure_remote_venv` · `install_remote_deps` · `upload_secret_files` · `restart_service` |
| `setup_ssh_key.py` — un comando shell de 40 líneas encadenadas con `&&` | Si fallaba el login había que rehacer la creación del usuario que ya existía | `ensure_remote_user` · `configure_sudo` · `install_public_key` · `test_ssh_login` |
| `build_apk.py` / `build_vite.py` / `build_binary.py` | Cada uno traía su propia copia del bump y del scp | `bump_version` (uno solo, tres manifiestos) · `upload_artifact` (uno solo) + el paso de compilación propio de cada builder |

Y el contraejemplo, donde la regla dice **no separar**: los seis pasos de `clean_vps.py`. Cada uno
se autodetecta antes de actuar, pero "dejar el VPS como recién formateado" casi siempre se pide
entero. Siguen siendo casillas del formulario, no botones del rail.

---

## 2. Cómo se ve una atómica

Casi todas quedan entre 3 y 12 líneas, porque el trabajo real lo hace el nivel 0:

```python
def create_role(ctx, scope: str = db.LOCAL) -> str:
    """Crea el rol de la aplicacion, o le actualiza la contrasena si ya existe."""
    admin = db.resolve_admin(ctx, scope)
    user, password, _ = db.credentials(ctx.config)
    ctx.guard(password)
    ...
```

Tres reglas comunes a todas:

1. **Idempotencia.** Detectan su estado antes de actuar: `create_avd` no recrea, `clone_repository`
   no vuelve a clonar, `install_packages` salta lo ya instalado, `register_key` no duplica.
   Correr la compuesta dos veces no rompe nada.
2. **Los secretos se marcan** con `ctx.guard()` apenas se leen, para que no aparezcan en la consola
   ni en el log guardado.
3. **Los destructivos hacen simulacro primero**: muestran la lista exacta y piden confirmación
   escrita (`ctx.confirm(expect=...)`) antes de tocar nada.

Y las compuestas son igual de cortas — cada paso es un `ctx.step()` más una llamada, con una
casilla booleana por paso:

```python
def rebuild_db(ctx, scope=db.LOCAL, *, drop=True, reset=True, generate=True,
               partitions=True, seeders=True, mock_seeders=True):
    if not ctx.confirm(f'Escribe {name} para reconstruir la base ({scope}).',
                       danger=True, expect=name):
        return
    if drop:      ctx.step('Vaciar esquema');  drop_tables(ctx, scope)
    if reset:     ctx.step('Resetear historial'); reset_migrations(ctx)
    ...
```

---

## 3. Catálogo por módulo

### `core/tasks/emulators.py`

| Atómica | Qué hace sola |
|---|---|
| `install_system_image` | Descarga la imagen del perfil (puede tardar 10 min: se hace una vez) |
| `create_avd` | Crea la máquina virtual; falla claro si falta la imagen |
| `launch_emulator` | Arranca un AVD ya creado |
| `await_emulator` | Espera el boot y devuelve el serial (lo usa `run_mobile`) |
| `stop_emulator` | `adb emu kill` — matar el proceso no alcanza |
| `delete_avd` / `delete_system_image` | Borrado puntual |
| `inventory` | Vista del Gestor de AVD: no corre nada |

**Compuestas:** `start_emulator` (imagen → AVD → arrancar), `purge_avds`, `purge_system_images`.

### `core/tasks/database.py`

| Atómica | Qué hace sola |
|---|---|
| `create_role` / `create_database` / `grant_privileges` / `enable_extensions` | Los cuatro pasos del bootstrap, sueltos |
| `drop_tables` | Vacía el esquema sin tocar rol, base ni migraciones escritas |
| `drop_database` / `drop_role` | Los dos pasos del teardown |
| `reset_migrations` | Borra `alembic/versions/*.py`, sin tocar la base |
| `generate_migration` | Autogenera una revisión; devuelve `None` si el modelo no cambió |
| `apply_migrations` | `alembic upgrade` |
| `ensure_partitions` | Las particiones que `autogenerate` no genera |
| `run_seeders` / `run_mock_seeders` | Los paquetes `seeders/` y `mock_data/` |
| `backup_database` / `rotate_backups` | Volcado y rotación, separados |
| `open_db_tunnel` | Servicio de fondo |
| `inspect_database` | Diagnóstico de solo lectura |

**Compuestas:** `bootstrap_db`, `rebuild_db`, `teardown_db`, `migrate_db`.

### `core/tasks/builders.py`

`bump_version` (sirve para los tres manifiestos) · `upload_artifact` (re-subir sin recompilar) ·
`compile_apk` · `install_node_modules` · `compile_spa` · `compile_binary` · `promote_app`.

**Compuestas:** `build_apk`, `build_vite`, `build_binary` — las tres envuelven el manifiesto en
`files.reversible()`, así que si el build falla la versión vuelve atrás y el repo no queda marcado
con un número que nunca se publicó.

### `core/tasks/vps_server.py`

`clone_repository` · `sync_repository` (pregunta si el VPS tiene cambios sin commitear) ·
`ensure_remote_venv` · `install_remote_deps` · `upload_secret_files` · `restart_service` (avisa y
sigue si el servicio no existe) · `write_systemd_unit` · `systemd_action` · `view_logs`.

**Compuestas:** `install_systemd` (reusa `systemd_action` para `enable`/`restart`, no lo
reimplementa), `update_remote`.

### `core/tasks/vps_setup.py`

`refresh_known_host` · `ensure_remote_user` · `configure_sudo` · `install_public_key` ·
`test_ssh_login` · `install_base_software` · `install_coturn` · `generate_remote_keypair` ·
`register_github_key` · `test_github_ssh`.

**Compuestas:** `setup_ssh_key`, `setup_github_ssh`, y `bootstrap_vps` — la compuesta de compuestas
(PLAN.md §7, caso 8): encadena `setup_ssh_key`, `update_remote`, `bootstrap_db` y `rebuild_db`,
que ya son compuestas con botón propio.

### `core/tasks/vps_ops.py`

`health_check` · `run_command` · `revoke_ssh_key` · `remove_remote_key_files` · `revoke_github_key` ·
y los seis pasos de la limpieza: `remove_systemd_service` · `remove_deployed_repo` ·
`uninstall_packages` · `remove_vps_user` (+ `teardown_db` y `revoke_github_ssh`, reusados).

**Compuestas:** `revoke_github_ssh`, `clean_vps`, `run_setup_scripts`.

### `core/tasks/launchers.py`

`resolve_server_port` · `backend_url` · `resolve_tls` · `serve_backend` · `serve_spa` ·
`run_mobile` · `open_terminal` · `open_ssh_session`.

### `core/tasks/utils.py`

`find_artifacts` (solo lectura, alimenta el simulacro) · `clean_artifacts` ·
`compare_common_files` · `sync_common_files` · `detect_public_ip` · `update_cloudflare` ·
`install_android_tools` · `install_android_packages` · `install_android_hypervisor` ·
`install_flutter_sdk`.

**Compuesta:** `install_android_sdk` (encadena las tres atómicas de Android; cada una sigue
teniendo su propio botón). Detalle en el §4.1.

---

## 4. Piezas nuevas que aparecieron al implementar

### 4.1 — Los SDK dejaron de pedir URL a mano: instalación completa, Linux primero

La primera versión de `install_android_sdk`/`install_flutter_sdk` (línea final del §5 vieja de
este documento) exigía la URL del paquete como parámetro porque "las de Google cambian con cada
versión". Eso era falso — la URL se resuelve sola desde la misma fuente que consulta un humano a
mano: la página de Android Studio (regex sobre el HTML, con su SHA-1 al lado) y el índice
`releases_<os>.json` de Flutter (con su SHA-256). Ninguna de las dos atómicas pide hoy una URL.

Consola está pensada para Linux y tiene que andar igual en Windows, así que se corrigieron tres
cosas que los scripts originales solo probaban en Windows:

- **Flutter en Linux se publica en `.tar.xz`, no en `.zip`.** El script original abría todo con
  `zipfile` y en Linux no llegaba a descomprimir nada. `files.extract()` (nuevo en
  [nivel-0.md](nivel-0.md)) elige el formato por la extensión.
- **`zipfile.extractall` descarta los permisos Unix.** El zip de Android sí se descomprimía en
  Linux, pero `sdkmanager` quedaba sin bit de ejecución. `files.extract_zip()` recupera el modo
  de `external_attr` y lo aplica con `chmod`.
- **Los directorios por defecto no miraban el sistema operativo** (`D:\Android` a secas). Ahora
  son `~/Android/Sdk` / `~/flutter` en Linux, `D:\Android` / `D:\flutter` en Windows
  (`core/catalog.py::ANDROID_DIR_DEFAULT`/`FLUTTER_DIR_DEFAULT`).

**`core/userenv.py`** (nuevo, nivel 0) reemplaza el `setx /M` + HKLM de los scripts: escribe en
`HKCU\Environment` en Windows y en un bloque delimitado (`# >>> consola >>>` / `# <<< consola
<<<`) del perfil del shell en Linux/Mac — nunca a nivel sistema, nunca pide admin. El bloque se
reescribe entero cada corrida (no se borra línea por línea como hacían los scripts), así que
reinstalar en otro directorio es idempotente y no deja rutas viejas colgando. Ver el porqué de
HKCU-vs-HKLM en la discusión que originó esto: nada de lo que Android o Flutter necesitan requiere
una consola elevada salvo el hypervisor.

Lo único que sí pide admin es `install_android_hypervisor` en Windows (el driver `gvm` es un
driver de kernel); usa `ShellExecuteW(..., 'runas', ...)` para un único prompt de UAC en vez de
exigir que toda Consola corra elevada. En Linux no se instala nada: se verifica `/dev/kvm` y, si
el usuario no tiene permiso, se le da el `usermod -aG kvm` exacto en vez de tocarlo con `sudo`
desde la interfaz.

`core/files.py` ganó `digest()` (SHA-1/SHA-256 genérico, un algoritmo por parámetro porque Android
publica SHA-1 y Flutter SHA-256) y `core/process.py` ganó `feed()` — el único punto de todo
Consola que le escribe a stdin de un subproceso (`sdkmanager --licenses` pregunta una por una y no
tiene bandera para aceptar todo).

### 4.2 — Build APK: el primer builder conectado, y el paso que se puede apagar

`build_apk` es la primera compuesta del grupo Builders con adaptador real. Quedó con **tres**
pasos, uno por átomo del dominio, y ninguno más:

| Paso | Función | Botón propio |
|---|---|---|
| Bump versión | `bump_version` | sí, oculto — compartido con los otros dos builders |
| Compilar APK | `compile_apk` | no: fuera de un build no significa nada |
| Subir al VPS | `upload_artifact` | sí, oculto — compartido |

Que dos de los tres tengan botón propio no ensucia el rail: con *solo favoritos*
([favoritos.md](favoritos.md)) las atómicas que ya viven dentro de una compuesta no se marcan, y
la vista en reposo muestra el botón grande nada más. Por eso separar sale barato aquí.

**El paso de compilar es desmarcable a propósito.** El script original tenía `BUILD_APK=false`
para subir un APK ya compilado sin rehacer el build — el caso del `scp` que se corta a mitad. Eso
sobrevive como el paso "Compilar APK" apagado: `build_apk` busca el binario que hay en disco
(`_last_apk`, que no pregunta el framework: usa la salida de Flutter si está y si no la de Flet) y
lo sube. Marcar el bump en ese modo se ignora con un aviso, porque el APK del disco se compiló con
la versión que el manifiesto ya tiene y subirla cambiada lo anunciaría como otra cosa.

**Sube el APK y el manifiesto, siempre juntos.** El `.apk` no dice de qué versión es; del lado del
VPS el `pubspec.yaml` es lo único que lo identifica. Subir solo el binario deja al servidor
anunciando la versión anterior, así que `_publish()` manda los dos o no manda ninguno.

**`build_only` es un modo de bump nuevo** (`core/versioning.py`), y existe solo por el build number
de Flutter: republicar el mismo `X.Y.Z` con un código nuevo, que es lo que se pide cuando el cambio
no le cambia nada al usuario. En un manifiesto sin `+N` falla en vez de devolver la versión intacta
como si hubiera hecho algo. Además `bump_mode` pasó de campo escrito a opción excluyente: es una
lista cerrada de cinco valores, no un texto libre.

**Validación previa, por paso y no por capacidad.** `API_URL` la necesita compilar (va por
`--dart-define`), y las cuatro claves de VPS las necesita subir. Las dos van en `requires_env` del
`Step`, no en `required_by` de la capacidad: así el modo re-subida no queda bloqueado por una clave
que solo usa el build, y compilar sin subir no pide credenciales del VPS.

### 4.3 — Un solo botón para Flutter y Flet, y el eje que sale del repo

`build_apk` no pregunta el framework. El script original tampoco: detectaba `pubspec.yaml` vs.
`pyproject.toml` con `flet` y seguía. La razón para no partirlo en dos botones es que **el framework
no es una decisión de quien aprieta el botón, es una propiedad de la carpeta** — preguntarlo sería
pedir que confirme algo que el repo ya contesta, y en cualquier repo real uno de los dos botones
estaría siempre muerto en el rail.

Lo que sí es una decisión es *cuál* app, cuando hay más de una. Ese es el eje:

```python
AxisDef('app', [], 'scope', label='App móvil', discover=targets.MOBILE_APP)
```

`values` se declara vacío a propósito. El catálogo se arma una sola vez al arrancar
(`load_catalog()`) y el repo cambia con el selector, así que un eje descubierto se llena al construir
el panel: `catalog.for_project(cap, root)` devuelve una copia de la capacidad con los valores
resueltos contra ese repo. `core/targets.py` ya tenía la mitad hecha (`names_of` está escrita para
esto); faltaba el lado del catálogo y del panel.

Cómo se ve, según lo que haya en el repo:

| Apps encontradas | Panel | Payload |
|---|---|---|
| una (el caso de los 8 repos) | **no dibuja selector** — un control de un solo valor es ruido | `app: 'app'` igual, para que el historial diga cuál se usó |
| dos o más | opciones excluyentes, ordenadas por nombre | la elegida |
| ninguna | botón en ámbar: *«no hay app móvil en este repo»* | — |

El ámbar del último caso es un blocker propio, distinto del genérico: un eje descubierto vacío no es
"olvidaste elegir", es que el repo no tiene eso, y pedir que elija de una lista vacía sería absurdo.

El mismo mecanismo se aplicó a `build_vite`, `serve_vite` y `run_mobile`, que hasta ahora declaraban
`['panel', 'backoffice', 'landing']` **a mano en el catálogo** — exactamente lo que PLAN.md §2.4 dice
que no hay que hacer. Y `run_mobile` perdió su eje `framework` de dos casillas por la misma razón que
`build_apk` no lo tiene.

**Lo único que Flutter y Flet no comparten** es `bump_mode='build_only'`: necesita el `+N` de
`pubspec.yaml` y en un `pyproject.toml` no significa nada. Falla al primer paso, antes de compilar,
con ese mensaje. No justifica dos botones — es validez por valor de eje, no otra capacidad.

**Sin verificar:** la inyección de `API_BASE_URL` en el build de Flet. `flet build` delega en el
`flutter build` de abajo, así que el `--dart-define` debería llegar (y se manda también por entorno),
pero no hay ningún repo Flet a mano para comprobarlo. Es el único paso de este flujo que sigue a
ciegas, y está marcado como tal en el código.

### `core/session.py` — estado de sesión
`run_server.py` escribía `SERVER_PORT` en `scripts/.env` para que `run_terminal.py` y `run_vite.py`
lo leyeran después. No es configuración: es el puerto que el backend consiguió *en esta corrida*.
Ahora vive en memoria, con alcance por proyecto, y desaparece al cerrar la app (PLAN.md §7, caso 4).

### `core/database.Admin` — canal de superusuario
`Connection` conecta como la aplicación; crear un rol o borrar una base necesita permisos de
administrador. `Admin` ejecuta SQL como superusuario, y resuelve el eje `scope` igual que
`Connection`: `psql` local en Windows, o `sudo -u postgres psql` por SSH en el VPS. Trae
`quote_ident` / `quote_literal`, que el script original tenía duplicados en `bootstrap_db.py` y
`teardown_db.py`.

### `core/tasks/payloads.py` — la única excepción deliberada
Los seeders y el mantenimiento de particiones no son operaciones sobre la base: son **código del
proyecto** (`seeders/`, `mock_data/`, `app.services.maintenance`) que solo se puede importar desde
el venv del servidor. Consola no puede importarlos con su propio intérprete.

La solución: dos programas cortos que viven en `core/tasks/payloads.py` como constantes de texto,
se escriben a un archivo temporal en cada corrida y se ejecutan con el Python del venv del proyecto,
con `DATABASE_URL` por el entorno del subproceso. No son scripts del repo gestionado: hay una sola
copia, es de Consola, y sigue funcionando cuando la app esté empaquetada con PyInstaller y no exista
como archivos sueltos en disco.

Lo mismo aplica a Alembic (`_alembic()` en `core/tasks/database.py`): el autogenerate necesita
importar los modelos del proyecto, así que corre con el intérprete del venv del servidor.

### `Registry.bind()` — el puente catálogo ↔ implementación
`core/catalog.py` declara la **forma** de cada capacidad (grupo, sección, ejes, pasos).
`core/tasks/<grupo>.bind_all()` le da el **cuerpo**. Mientras nadie llame a `bind`, la capacidad
sigue con `stub=True` y la UI la dibuja como tal. `main.py` ahora hace `load_catalog()` seguido de
`bind_all()`.

---

## 5. Estado

```
implementadas 48 / 48   ·   siguen stub: []
```

Verificado sobre un repo de prueba: bump en `pubspec.yaml` (`1.4.22+318` → `1.4.23+319`, con el
build number) y en `package.json`, detección de targets (`flutter-app: app`, `spa-vite: panel`),
listado de artefactos, y generación de la unidad systemd. La resolución de URL/hash de los SDK se
verificó contra las fuentes oficiales en vivo (§4.1); la instalación completa (bajar ~600 MB y
escribir el registro/perfil de verdad) todavía no se corrió de punta a punta.

**Lo que falta para que los botones corran de verdad** (etapa 2 de PLAN.md §10):

- ✅ `ui/task_runner.py` — `TaskRunner(QThread)` corre una capacidad en un hilo aparte (reemplaza
  al pendiente `core/runner.py` de esta lista). Ver `docs/catalogo-funciones.md §6`.
- ✅ El puente ejes/pasos del panel → kwargs de la función real: `ui/task_adapters.py`, un
  adaptador por capacidad conectada. Siete conectadas hoy: `clean_artifacts`,
  `install_android_tools`, `install_android_packages`, `install_android_hypervisor`,
  `install_android_sdk`, `install_flutter_sdk` y `build_apk` (§4.2) — y las que sigan sumándose.
- Los `ask_sink` / `note_sink` del `TaskContext` conectados a diálogos Qt reales — sigue pendiente
  para las capacidades con `ctx.confirm()`/`ctx.ask()` real.
- `core/store.py` — SQLite para historial, bitácora y presets.

**Pendientes de confirmar con uso real** (PLAN.md §11, puntos 3 y 5): cuáles de estas atómicas se
piden sueltas de verdad. Si alguna nunca se usa sola, sobra como botón y puede volver a ser un paso
interno — la decisión es barata ahora y cara después.
