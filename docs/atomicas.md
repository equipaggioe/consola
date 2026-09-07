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
| `android_emulator.py` — un `run()` que bajaba la system image, creaba el AVD, parcheaba `config.ini` y arrancaba, con tres wrappers que solo cambiaban una constante | Para arrancar un emulador ya creado había que volver a entrar a la lógica de descarga y creación; y las tres constantes escondían los 88 dispositivos y 317 imágenes que publica el SDK | `install_system_image` · `create_avd` · `launch_emulator` · `await_emulator` · `stop_emulator` ([emuladores.md](emuladores.md)) |
| `rebuild_db.py` — un archivo que borraba tablas, reseteaba Alembic, regeneraba la migración inicial, aseguraba particiones y corría dos tandas de seeders | Volver a correr solo los seeders mock obligaba a destruir el esquema | `drop_tables` · `reset_migrations` · `generate_migration` · `apply_migrations` · `ensure_partitions` · `run_seeders` · `run_mock_seeders` |
| `update_remote.py` — 607 líneas en un `main()` | "Solo recopiar los certificados" implicaba rehacer `git pull` + venv + `pip install` | `sync_repository` · `ensure_remote_venv` · `install_remote_deps` · `upload_secret_files` · `restart_service` |
| `setup_ssh_key.py` — un comando shell de 40 líneas encadenadas con `&&` | Si fallaba el login había que rehacer la creación del usuario que ya existía | `ensure_deploy_access` · `configure_sudo` (+ la verificación, que es plomería: §4.6) |
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
| `create_avd` | Crea el dispositivo virtual eligiéndolo del catálogo; falla claro si falta la imagen |
| `launch_emulator` | Arranca un AVD ya creado, en puerto propio y con `-read-only` si ya corría |
| `await_emulator` | Espera el boot y devuelve el serial (lo usa `run_mobile`) |
| `stop_emulator` | `adb emu kill` — matar el proceso no alcanza |
| `purge_emulators` | Borra los AVD e imágenes marcados, con simulacro primero |
| `inventory` | Lo que hay en la máquina; no corre nada |

**Sin compuestas.** `start_emulator` (imagen → AVD → arrancar) existió y se borró: al conectar los
catálogos reales del SDK —88 dispositivos, 317 system images— los tres pasos dejaron de ser
variantes de lo mismo y pasaron a ser tres actividades con opciones propias. Un paso deja de caber
en una casilla cuando gana su propio catálogo. Ver [emuladores.md](emuladores.md).

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
`compile_apk` · `install_node_modules` · `compile_spa` · `compile_binary` · `resolve_entrypoint` ·
`checksum_artifact` · `promote_app`.

**Compuestas:** `build_apk`, `build_vite`, `build_binary` — las tres envuelven el manifiesto en
`files.reversible()`, así que si el build falla la versión vuelve atrás y el repo no queda marcado
con un número que nunca se publicó.

### `core/tasks/vps_server.py`

`push_repository` · `sync_repository` (clona o actualiza segun el estado del VPS; pregunta si
tiene cambios sin commitear) · `install_remote_deps` (crea el venv adentro) · `upload_secret_files` ·
`restart_service` (avisa y sigue si el servicio no existe) · `write_systemd_unit` · `systemd_action` ·
`view_logs`.

`clone_repository` y `ensure_remote_venv` ya no están sueltas: nadie pide «solo clonar» ni «solo
crear el venv», así que son el primer tramo de `sync_repository` y de `install_remote_deps` (§1).

**Compuestas:** `install_systemd` (reusa `systemd_action` para `enable`/`restart`, no lo
reimplementa), `publish_code` y `update_remote` (§4.7).

### `core/tasks/vps_setup.py`

`refresh_known_host` · `ensure_deploy_access` · `configure_sudo` · `install_base_software` ·
`install_coturn` · `generate_remote_keypair` · `register_github_key` · `test_github_ssh`.

Eran cuatro donde ahora hay dos: la revisión del §4.6 fusionó `ensure_remote_user` con
`install_public_key` y bajó `test_ssh_login` a `core/ssh.py::reachable`.

**Compuestas:** `setup_ssh_key`, `setup_github_ssh`, y `bootstrap_vps` — la compuesta de compuestas
(PLAN.md §7, caso 8): encadena `setup_ssh_key`, `publish_code`, `bootstrap_db` y `rebuild_db`, que
ya son compuestas con botón propio. Encadenaba `update_remote` y por qué dejó de hacerlo está en el
§4.7.

### `core/tasks/vps_ops.py`

`health_check` · `run_command` · `revoke_ssh_key` · `remove_remote_key_files` · `revoke_github_key` ·
y los seis pasos de la limpieza: `remove_systemd_service` · `remove_deployed_repo` ·
`uninstall_packages` · `remove_vps_user` (+ `teardown_db` y `revoke_github_ssh`, reusados).

**Compuestas:** `revoke_github_ssh`, `clean_vps`, `run_setup_scripts`.

### `core/tasks/launchers.py`

**Atómicas:** `serve_backend` · `serve_spa` · `run_mobile` · `open_terminal` · `open_ssh_session`.

**Plomería, no atómicas** (corrección del §0 aplicada a este módulo):
`resolve_server_port` · `backend_url` · `resolve_tls`. Estaban listadas como atómicas y no lo son
—nadie pide «elige un puerto y nada más»—; son el `_download`/`_extract` de este grupo.
`serve_backend` es **una** atómica hecha de cinco funciones. Ver
[launchers.md §1](launchers.md).

**Compuesta:** `dev_env` («Entorno de desarrollo»), y es de un tipo que este documento no tenía:
**concurrente**. Sus pasos no van uno tras otro, van todos a la vez, una pestaña cada uno, y ninguno
termina. No tiene cuerpo en `core/tasks/`: lo despacha la interfaz, porque «N pestañas» no significa
nada acá adentro ([launchers.md §2.5](launchers.md)).

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

**`bump_mode` pasó de campo escrito a opción excluyente**, y luego a algo más preciso que eso: el
componente SemVer (`major`/`minor`/`patch`/`none`) es una elección excluyente, pero **subir el build
number es independiente y se combina con cualquiera de las cuatro** (§4.4) — `patch` sola deja el
build number igual, `patch`+`build` sube los dos. Es el mismo desglose que el script original tenía
como `patch_only` vs. `patch+build`, solo que ahora son dos controles en vez de cuatro strings mágicos.

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
| una (el caso de los 8 repos) | se dibuja igual, **marcada y sin poder desmarcarse** — se ve cuál es, sin dejar elegir algo que no existe | `app: 'app'` |
| dos o más | opciones excluyentes, ordenadas por nombre | la elegida |
| ninguna | botón en ámbar: *«no hay app móvil en este repo»* | — |

(El caso "una sola opción se dibuja bloqueada en vez de ocultarse" cambió de rumbo una vez — ver
§4.4 — y quedó documentado ahí junto con el resto de la revisión de ejes.)

El ámbar del último caso es un blocker propio, distinto del genérico: un eje descubierto vacío no es
"olvidaste elegir", es que el repo no tiene eso, y pedir que elija de una lista vacía sería absurdo.

El mismo mecanismo se aplicó a `build_vite`, `serve_vite` y `run_mobile`, que hasta ahora declaraban
`['panel', 'backoffice', 'landing']` **a mano en el catálogo** — exactamente lo que PLAN.md §2.4 dice
que no hay que hacer. Y `run_mobile` perdió su eje `framework` de dos casillas por la misma razón que
`build_apk` no lo tiene.

**Lo único que Flutter y Flet no comparten** es el `+build` de `bump_mode` (§4.4): necesita el `+N`
de `pubspec.yaml` y en un `pyproject.toml` no significa nada. Falla al primer paso, antes de compilar,
con ese mensaje. No justifica dos botones — es validez por valor de eje, no otra capacidad.

**Sin verificar:** la inyección de `API_BASE_URL` en el build de Flet. `flet build` delega en el
`flutter build` de abajo, así que el `--dart-define` debería llegar (y se manda también por entorno),
pero no hay ningún repo Flet a mano para comprobarlo. Es el único paso de este flujo que sigue a
ciegas, y está marcado como tal en el código.

### 4.4 — El eje bloqueado, el bump combinable y el default que ya no bloquea

Tres ajustes sobre uso real de `build_apk`, después de mirarlo andar.

**Ocultar el selector de una sola opción se revirtió.** §4.3 lo dibujaba así — "un control de un
solo valor es ruido" — pero eso escondía justo la información que el botón necesita mostrar: *cuál*
app se va a compilar cuando el repo tiene una. Ahora `_build_options()` sigue dibujando el eje con
un único valor excluyente, pero marcado y con `setEnabled(False)`: se ve, no se puede tocar. Aplica a
cualquier eje de un solo valor, no solo a `app` — `AxisDef.exclusive_values` es lo que cuenta para
decidirlo, no `values` a secas (por el punto siguiente).

**`bump_mode` dejó de ser una lista de un solo valor.** Subir el build number ya no es una variante
más entre `major`/`minor`/`patch`/`build`/`none`: es un interruptor que se combina con cualquiera de
las otras cuatro, que sí son excluyentes entre sí. `AxisDef` ganó dos campos para esto:

```python
combine: set[str] = field(default_factory=set)  # valores que stackean, fuera del grupo excluyente
default: str = ''                                # cual arranca marcado; vacio = el primero
```

`_BUMP_AXIS()` en `core/catalog.py` declara `combine={'build'}, default='patch'` sobre
`['major', 'minor', 'patch', 'build', 'none']` — ese es el orden de lectura pedido, con `build` entre
`patch` y `none` en vez de aislado en su propia sección. El panel dibuja los cuatro excluyentes en un
`QButtonGroup` y `build` como casilla suelta al lado; el payload de un eje con `combine` viaja como
lista (`['patch', 'build']`) en vez de un string, y `ui/task_adapters.py::_bump_mode()` la arma de
vuelta a lo que entiende `versioning.bump()`: `'patch+build'`, `'build'` (= el viejo `build_only`),
`'major+build'`... `core/versioning.py::bump()` interpreta esa cadena con `_parse_mode()` — separa el
componente SemVer del `+build` y los aplica por separado.

**Un default con el que la acción igual puede correr ya no bloquea el botón.** Este era un bug
general, no solo de `build_apk`: `VPS_USER` vacío bloqueaba en ámbar *«faltan claves: VPS_USER»`
aunque `core/ssh.py`/`core/database.py` ya sabían resolverlo solos al nombre del repo — el campo
vacío nunca iba a llegar vacío a la función real. Lo mismo le pasaba de encubierto a cualquier
`Setting` con `default` fijo (`ROOT_USER='root'`, `VPS_PYTHON`, `PG_SUPERUSER`...): `Config.get()` ya
aplicaba ese default al correr, pero `ui/params_panel.py::_missing_keys()` miraba el texto crudo del
campo en vez de preguntarle a un `Config`, así que igual bloqueaba.

La causa era una sola: dos caminos para la misma pregunta ("¿qué valor va a usar esto?"), uno en
`core/envfile.py::Config.get()` y otro, más ingenuo, en el panel. Se unificaron en el primero:

- `Config.get()` gana un segundo nivel de default, dinámico y por repo, además del fijo de
  `Setting.default`: `VPS_USER` cae en `self.repo_name` (el nombre de la carpeta — lo que
  `optional_env("VPS_USER", repo_root.name)` hacía en el script original) y `DB_NAME` cae en
  `f'{vps_user}_db'` llamando de vuelta a `self.get('VPS_USER')`, así que encadena bien si las dos
  quedan vacías. Los cinco lugares que reimplementaban `config.get('VPS_USER') or config.repo_name`
  a mano (`ssh.py`, `database.py`, `vps_ops.py`, dos en `vps_setup.py`) quedaron en un `config.get()`
  solo.
- `_missing_keys()` ahora arma un `Config(self._env, repo_name=...)` con lo que hay tipeado en el
  panel de configuración y le pregunta a *ese*, no al diccionario crudo — exactamente la misma
  pregunta que se hace en tiempo de ejecución. Una clave con default fijo o dinámico deja de contar
  como faltante.
- `ui/env_panel.py::EnvRow` muestra ese mismo default como marca de agua del campo — antes cualquier
  default no literal (`VPS_USER`) mostraba el nombre de la clave a secas. `EnvPanel` arma un `Config`
  vacío (sin valores, solo `repo_name`) una vez por proyecto y se lo pasa a cada fila: la sugerencia
  que se ve es la que de verdad se va a usar si el campo queda en blanco, no una genérica.

`core/envfile.py` ganó `repo_name_of(path)` (el `os.path.basename(os.path.normpath(...))` que antes
solo vivía dentro de `Config.for_project`) para no triplicarlo entre `Config`, `EnvPanel` y
`ParamsPanel`.

### 4.5 — Build binario: el tercer builder, y el paso que nunca debió ser obligatorio

`build_binary` se conectó último y homologando a los otros dos: mismo esqueleto, mismos pasos, misma
reversibilidad del manifiesto. Lo que cambió al leer el script original
(`scripts/builders/build_binary.py`) fue más de lo esperado.

**El flag que el catálogo había dado por imposible.** El script tenía `BUILD_BINARY=false`: no
compila, no versiona, y sube al VPS el ejecutable y el `pyproject.toml` que ya están en disco. El
catálogo declaraba `Step('binary_build', optional=False)` con la explicación contraria — «PyInstaller
no deja nada re-subible» — y la función devolvía `None` sin subir nada cuando el paso venía
apagado. `dist/` sí conserva el binario, y el modo re-subida existía justamente porque un `scp`
cortado no debería costar otro empaquetado. Ahora los tres builders tienen el mismo paso desmarcable
y el mismo aviso de bump ignorado.

**Sube el binario con su manifiesto, siempre juntos.** Igual que `_publish` (APK) y `_publish_spa`.
El script original lo hacía solo en su rama `BUILD_BINARY=false`; en la normal subía el ejecutable y
dejaba el manifiesto remoto anunciando la versión anterior. Es el mismo descuido que ya se había
corregido en Vite.

**El binario se sube ejecutable.** `scp` no conserva el bit de ejecución: del otro lado quedaba un
ejecutable que no se podía ejecutar. `upload_artifact` ganó un `chmod` opcional (`755`, o `-R 755`
cuando el empaquetado es una carpeta) que solo usa este builder — un APK o una carpeta de SPA se
sirven, no se ejecutan.

**PyInstaller sale del venv de la app.** PyInstaller congela el entorno desde el que corre: con el
global, el binario sale sin las dependencias del proyecto y muere al primer import. El script
resolvía solo por PATH, así que empaquetar bien dependía de haber activado el venv correcto antes de
lanzarlo — algo que un botón no puede pedir. `toolchain.pyinstaller_cmd()` mira primero el mismo
`.venv` que usa el launcher de la terminal, y cae al PATH si ahí no está. El `PYINSTALLER_BIN` del
script sobrevive como clave de configuración (grupo Builders, `used_by` y no `required_by`: no
bloquea el botón) — hace falta más seguido de lo que parece, porque `pip install pyinstaller` deja
el ejecutable en un `Scripts/` de usuario que en Windows no suele estar en el PATH.

**No hay eje `app` descubierto, a diferencia de los otros dos builders.** Un eje descubierto vacío
deja el botón en ámbar (§4.3), y el repo que se empaqueta desde su raíz —el caso de la propia
Consola (PLAN.md §7)— no tiene ningún `python-app` que descubrir: quedaría sin poder compilar su
propio ejecutable. El eje es el campo `entrypoint`, como en PLAN.md §5, y acepta cualquier ruta del
repo igual que el script (`server/main.py`, `tools/cli.py`). Vacío no es "falta un dato":
`resolve_entrypoint` deduce `src/main.py` de la única app Python del repo — el mismo entrypoint que
lanza `open_terminal`, para que lo que se descarga sea lo que se corre en desarrollo — y si el repo
no tiene ninguna, un `main.py` en la raíz. Con dos apps Python el error pide escribir cuál, que es
la única pregunta que queda sin respuesta en la carpeta.

**La carpeta de la app se busca subiendo desde el entrypoint** hasta el primer manifiesto. El script
se quedaba con `entrypoint.parent`, que para `src/main.py` es `src/`: ahí creaba un `pyproject.toml`
paralelo al de la app, con una versión propia que no leía nadie. `_ensure_manifest` conserva la parte
buena de ese `_ensure_pyproject` — un script suelto que se empieza a distribuir no tiene por qué
traer manifiesto — pero lo crea donde corresponde y lo avisa.

**Tres cosas nuevas que el script no hacía**, y que son del dominio de "ejecutable descargable":

| Novedad | Por qué |
|---|---|
| Paso `binary_checksum` | Un ejecutable descargado no se puede mirar por dentro: el `<binario>.sha256` (formato `sha256sum -c`) es lo único que deja comprobar que lo bajado es lo publicado. Se sube junto al binario. Con empaquetado en carpeta no aplica y se saltea con aviso, sin tirar el build. |
| Ejes `packaging` y `window` | `ONEFILE` era una constante del script y ahora es un segmentado; `--windowed` es su hermano que faltaba — en Windows, una app de ventana empaquetada sin eso arrastra una consola negra detrás. |
| Campo `icon` | `--icon`, para que el ejecutable no se distribuya con el ícono por defecto de PyInstaller. Es lo que PLAN.md §7 pide para `Consola.exe`. |

**Dos detalles de higiene.** El `.spec` generado va a `build/` (`--specpath`): en la raíz de la app
aparecía como cambio sin commitear después de cada compilación, y en `build/` ya lo cubre 'Limpiar
artefactos'. Y no se pasa `--clean`, que el script sí traía: borra la caché y vuelve a analizar todas
las dependencias en cada corrida. Es la misma economía por la que `install_node_modules` usa
`npm install` y no `npm ci` — para el limpio de verdad está el botón de limpiar artefactos.

**El nombre lleva la plataforma y no la versión:** `consola-windows-amd64.exe`. PyInstaller no
compila cruzado, así que sin etiqueta el binario de Windows y el de Linux se pisan en la misma ruta
del VPS; y sin versión en el nombre, la URL de descarga queda estable y quien quiere saber qué
versión es lee el manifiesto que se publica al lado.

**Verificado de punta a punta** sobre un repo de prueba: `pyproject.toml` 0.4.1 → 0.4.2, PyInstaller
corriendo con `--specpath build`, `dist/demo-windows-amd64.exe` (7.9 MB) + su `.sha256`, y el
ejecutable arrancando y escribiendo su salida. Las dos ramas de re-subida se probaron hasta el punto
en que piden VPS. Lo único que sigue sin verificar es la subida real (`chmod 755` incluido), que
necesita un servidor.

### 4.6 — La segunda mitad del criterio: quién la llama

El §1 pregunta *«¿tiene sentido re-ejecutar este paso solo?»*, y el §0 aclara que una utilidad
interna de **una** atómica no es atómica. Faltaba el caso inverso: la utilidad que comparten
**muchas**. `setup_ssh_key` lo expuso, y la regla que salió es:

> Si algo lo necesitan la mayoría de los botones de una familia, es **plomería de nivel 0**,
> no una atómica — aunque una persona pudiera pedirlo suelto.

El olor concreto es una tarea que importa otra tarea de otro grupo para usarla como precondición.
Si `vps_server.update_remote` tuviera que hacer `from .vps_setup import test_ssh_login`, eso ya es
la prueba de que el lugar correcto era `core/`.

**El caso.** `test_ssh_login` parecía la átomica más sólida del grupo: solo lectura, sin efectos,
y su propio docstring decía que era «el paso que más se pide suelto». Los números decían otra cosa:

| | |
|---|---|
| `ssh.resolve_remote()` | llamado en **11 lugares**, 7 módulos — todos necesitan «¿llego al VPS?» y ninguno lo verifica |
| `test_ssh_login()` | llamado en **1 lugar**, dentro de su propia compuesta |

Y el cuerpo lo confirmaba: una llamada a `ssh.succeeds` —que ya *era* la plomería— más dos líneas
de consola. Bajó a `core/ssh.py::reachable()`, que es donde las once puertas pueden usarla.

**El bug que tapaba.** `health_check` es el botón de diagnóstico del VPS, y con el SSH caído
mentía. Las cuatro consultas de `vps.health()` usan `check=False`, y `service_state` cae por
`succeeds` a `'missing'`:

```
  SSH caído → antes:                      ahora:

    servicio: missing                       acceso: SIN ACCESO SSH a deploy@1.2.3.4
    uptime:   (sin datos)
    disco:    (sin datos)     ← parece
    memoria:  (sin datos)       un servidor
    carga:    (sin datos)       destruido
```

Confundir *servidor inalcanzable* con *servidor vacío* manda a arreglar lo que no está roto. La
línea que faltaba era justo la que `test_ssh_login` tenía guardada para sí: `reachable()` es ahora
lo primero que `health()` pregunta, y corta si falla.

**La otra fusión, por el criterio viejo.** `ensure_remote_user` tampoco pasaba el §1: nadie lo
corre solo, y si lo hiciera quedaría con un usuario al que no puede entrar. Tampoco servía como
casilla desmarcable — el paso ya era idempotente (`id -u`), así que saltearlo no ahorraba nada. Es
el mismo diagnóstico que borró `fetch_dependencies` (§0): trabajo con encabezado propio que parecía
decidir algo. Se fusionó con `install_public_key` en `ensure_deploy_access` («dar de alta la cuenta
de despliegue»), que es un átomo del dominio de verdad.

Efecto medible, además del conceptual: la compuesta abre **dos** conexiones de root en vez de tres,
y pide la contraseña una vez menos.

**Las dos que sobreviven, y por qué.** `install_public_key` (dentro de `ensure_deploy_access`) y
`configure_sudo`:

- La simetría ya decidida: `revoke_ssh_key` **es** botón, con sus propias casillas. Un rail donde
  se quita el acceso de un click pero devolverlo exige la compuesta entera está torcido.
- `configure_sudo` ganó su propio catálogo — tres modos excluyentes con listas distintas. Es la
  regla del §3 («un paso deja de caber en una casilla cuando gana su propio catálogo»), la misma
  que borró `start_emulator`.

**Y el contraejemplo que había que refutar:** esto se parece a `clean_vps` —pasos que se
autodetectan y casi siempre se piden enteros—, pero `clean_vps` es *terminal*: no hay «después»,
porque cuando termina no queda nada que re-pedir. El acceso SSH es lo único del catálogo que se
**mantiene**: rota, se verifica, se afloja y se aprieta. Por eso las mismas propiedades
superficiales dan resultados opuestos.

**Lo que cambió en el código:**

| Archivo | Qué |
|---|---|
| `core/ssh.py` | `reachable()` — la precondición que comparten las 11 puertas |
| `core/vps.py` | `health()` pregunta `acceso` primero y corta |
| `core/tasks/vps_setup.py` | `ensure_deploy_access` (fusión) · se va `test_ssh_login` · `SUDO_SPECIFIC` vuelve a cubrir todos los `sudo -n` del código |
| `core/catalog.py` | eje `sudo_mode` (`all`/`specific`/`none`), y `steps` declarados en vez de un `composed_of` de cinco ids contra una función de cuatro parámetros |

El eje era lo que faltaba para que `specific` fuera elegible: venía de `SUDO_NOPASSWD_MODE`, una
constante que en el script se editaba a mano y que al portarse quedó como parámetro sin control que
lo ofreciera. Al volverlo alcanzable, su lista recortada (tres comandos, sin `tee`, `ufw` ni `rm`)
pasó de hueco latente a falla real, y se completó.

### 4.7 — Una compuesta solo reusa a otra si quiere todos sus pasos

El §4.6 cerró el agujero de «un parámetro que no se reenvía queda clavado en su default». Faltaba el
caso en que lo clavado no es un parámetro sino **la mitad de una receta**.

`bootstrap_vps` llamaba a `vps_server.update_remote(ctx, restart=False)`. De los seis pasos del
despliegue quería tres, y los otros tres entraban por sus defaults sin que nadie los viera — las
casillas de una compuesta interna no se dibujan en el panel del botón externo. Dos hacían daño:

| Paso heredado | Qué pasaba en un VPS de cero |
|---|---|
| `migrate=True` | `alembic upgrade` contra una base que **el paso siguiente todavía no creó**. Y `bootstrap_db` ya termina con `apply_migrations`, así que aun en orden sobraba |
| `upload=True` con `files=None` | `upload_secret_files` avisaba «no hay archivos que copiar» y no hacía nada. El botón Bootstrap no declaraba el eje `files`, así que ese paso **nunca** pudo hacer otra cosa |

La regla que sale, hermana de la del §4.6:

> Una compuesta puede reusar a otra **solo si quiere todos sus pasos**. Si quiere la mitad, o baja a
> las atómicas, o la mitad que comparten es una compuesta por derecho propio.

Aquí valió lo segundo, porque esa mitad tiene dos consumidores reales y un significado propio:
**`publish_code`** — push → código → dependencias → secretos. Es el despliegue sin las dos acciones
que tocan lo que ya está corriendo, que son exactamente las que un servidor recién armado no puede
hacer. `update_remote` pasó a ser `publish_code` más migrar y reiniciar, reenviándole las cuatro
banderas enteras: su panel sigue mostrando las seis casillas planas, la compuesta de adentro no se
ve desde afuera.

`bootstrap_vps` la llama tal cual y ganó el eje `files`, que es lo que le faltaba para cumplir lo
que su descripción promete («de VPS recién creado a servicio corriendo»): sin `.env` el servicio
arranca y muere, así que el último paso instalaba un systemd condenado y el botón anunciaba éxito.

Y un rótulo que mentía: el paso `git_pull` se llamaba «Pull en el VPS», pero `sync_repository`
decide sola —con `_remote_state`, sin ninguna bandera— si clona o actualiza, y en la primera
corrida clona. Ahora es «Código en el VPS».

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
  adaptador por capacidad conectada. Conectadas hoy: `clean_artifacts`, `install_android_tools`,
  `install_android_packages`, `install_android_hypervisor`, `install_android_sdk`,
  `install_flutter_sdk`, `build_apk` (§4.2), `build_vite`, `build_binary` (§4.5),
  `push_repository`, `upload_secret_files`,
  `update_remote`, los cuatro de emuladores, **el grupo Launchers completo**
  ([launchers.md](launchers.md)) y **el grupo VPS · setup completo** (§4.6) — y las que sigan
  sumándose.
- ✅ Los `ask_sink` / `note_sink` del `TaskContext` conectados a diálogos Qt reales. Esta línea
  decía "sigue pendiente" y estaba vencida: `ui/task_runner.py` ya expone `ask_requested` y
  `ui/tab_panel.py` lo conecta a un diálogo que sabe ocultar lo que se escribe. Lo que sí faltaba
  era **no repetir la pregunta**: `TaskContext.ask_once()` recuerda la respuesta durante la
  corrida, porque una compuesta abre una conexión por atómica y ninguna sabe que las otras ya
  pidieron la misma contraseña. `setup_ssh_key` pasó de tres preguntas a una.
- `core/store.py` — SQLite para historial, bitácora y presets.

**Pendientes de confirmar con uso real** (PLAN.md §11, puntos 3 y 5): cuáles de estas atómicas se
piden sueltas de verdad. Si alguna nunca se usa sola, sobra como botón y puede volver a ser un paso
interno — la decisión es barata ahora y cara después.
