# Niveles 1 y 2 — atómicas y compuestas en `core/tasks/`

Implementación de los niveles 1 y 2 de [PLAN.md §2](PLAN.md), sobre la plomería documentada en
[nivel-0.md](nivel-0.md). Nueve módulos, ~2.300 líneas, **45 capacidades del catálogo con cuerpo
real** (0 stubs).

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
`fetch_dependencies` · `compile_apk` · `install_node_modules` · `compile_spa` · `compile_binary` ·
`promote_app`.

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
`install_android_sdk` · `install_flutter_sdk`.

---

## 4. Piezas nuevas que aparecieron al implementar

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
implementadas 45 / 45   ·   siguen stub: []
```

Verificado sobre un repo de prueba: bump en `pubspec.yaml` (`1.4.22+318` → `1.4.23+319`, con el
build number) y en `package.json`, detección de targets (`flutter-app: app`, `spa-vite: panel`),
listado de artefactos, y generación de la unidad systemd.

**Lo que falta para que los botones corran de verdad** (etapa 2 de PLAN.md §10, no cubierto acá):

- `core/runner.py` — el pool de workers que ejecuta una capacidad en un hilo aparte. Hoy
  `ui/tab_panel.py` sigue haciendo ejecución simulada e ignora `cap.func`.
- El puente entre los ejes/pasos del panel de parámetros y los argumentos de cada función
  (hoy las atómicas reciben kwargs con default; nadie los llena desde la UI todavía).
- Los `ask_sink` / `note_sink` del `TaskContext` conectados a diálogos Qt reales.
- `core/store.py` — SQLite para historial, bitácora y presets.

**Pendientes de confirmar con uso real** (PLAN.md §11, puntos 3 y 5): cuáles de estas atómicas se
piden sueltas de verdad. Si alguna nunca se usa sola, sobra como botón y puede volver a ser un paso
interno — la decisión es barata ahora y cara después.

Los dos instaladores de SDK (`install_android_sdk`, `install_flutter_sdk`) piden la URL del paquete
en vez de traerla hardcodeada: las de Google y Flutter cambian con cada versión y una constante
vieja hacía fallar el script sin decir por qué.
