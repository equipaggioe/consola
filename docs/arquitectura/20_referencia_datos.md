# 20 · Referencia de datos

Formatos, claves y archivos. Lo que **significa** cada uno está en el documento de su dominio; acá está la forma.

## 1. Claves de `.consola/config.env`

41 claves declaradas en `core/settings.py`, 40 del repo y una de la máquina. «Exige» significa que alguna acción no puede correr sin ella (su botón queda en ámbar); «usa» que la miran pero corren igual.

| Clave | Grupo | Etiqueta | Tipo | Default | |
|---|---|---|---|---|---|
| `API_URL` | Server | URL pública de la API | | | usa |
| `CF_API_TOKEN` | Cloudflare | API token | secreto | | exige |
| `CF_DOMAIN_NAME` | Cloudflare | Dominio | | | exige |
| `CF_RECORD_NAME` | Cloudflare | Registro DNS | | | exige |
| `VPS_IP` | VPS | IP del servidor | | | exige |
| `ROOT_USER` | VPS | Usuario root | | `root` | exige |
| `VPS_USER` | VPS | Usuario de despliegue | | nombre del repo | exige |
| `VPS_KEY_NAME` | VPS | Nombre de la llave SSH | | | exige |
| `VPS_PYTHON` | VPS | Python del VPS | | `server/.venv/bin/python` | exige |
| `VPS_DEPLOY_DIR` | VPS | Directorio de despliegue | | | exige |
| `PUBLIC_HOST` | VPS | Nombre público del VPS | | `CF_RECORD_NAME` → `CF_DOMAIN_NAME` → `VPS_IP` | usa |
| `SECRET_FILES` | VPS | Archivos a copiar | lista | | usa |
| `DB_USER` | VPS | Rol de la base | | `VPS_USER` | exige |
| `DB_NAME` | VPS | Base de datos | | `<VPS_USER>_db` | exige |
| `DB_PASSWORD` | VPS | Password de la base | secreto | | exige |
| `TURN_SECRET` | VPS | Secreto TURN | secreto | lo genera `configure_coturn` | usa |
| `TURN_PORT` | VPS | Puerto TURN | | `3478` | usa |
| `TURN_RELAY_RANGE` | VPS | Rango de relay | | `49160-49360` | usa |
| `PG_SUPERUSER` | VPS | Superusuario Postgres | | `postgres` | exige |
| `PG_PASSWORD` | VPS | Password del superusuario | secreto | | exige |
| `DB_EXTENSIONS` | VPS | Extensiones de Postgres | lista | `postgis` | usa |
| `PUBLIC_ROUTES` | Web | Rutas públicas | lista | | exige |
| `CSP` | Web | Content-Security-Policy | | vacía = no emitir CSP | usa |
| `GIT_REPO_URL` | GitHub | URL del repositorio | | | exige |
| `GITHUB_TOKEN` | GitHub | Token | secreto | | exige |
| `GITHUB_KEY_TITLE` | GitHub | Título de la llave | | `<repo>-vps` | exige |
| `SERVER_DIR` | Systemd | Carpeta del server | | `server` | exige |
| `BACKEND_HOST` | Systemd | Escucha del backend | | `127.0.0.1` con proxy, si no `0.0.0.0` | usa |
| `BACKEND_PORT` | Systemd | Puerto del backend | | `8000` | usa |
| `CERT_FILE_PATH` | Systemd | Certificado | | `server/certs/cert.pem` | exige |
| `KEY_FILE_PATH` | Systemd | Llave privada | | `server/certs/key.pem` | exige |
| `UVICORN_APP` | Systemd | Entrypoint uvicorn | | `app.main:app` | exige |
| `SERVICE_DIRS` | Systemd | Carpetas del servicio | lista | | usa |
| `BUILD_OUT_APK` | Builds | Carpeta del build APK | | donde lo deja el framework | usa |
| `BUILD_OUT_AAB` | Builds | Carpeta del build AAB | | ídem | usa |
| `BUILD_OUT_WEB` | Builds | Carpeta del build web | | ídem | usa |
| `BUILD_OUT_WINDOWS` | Builds | Carpeta del build Windows | | ídem | usa |
| `BUILD_OUT_LINUX` | Builds | Carpeta del build Linux | | ídem | usa |
| `BUILD_OUT_MACOS` | Builds | Carpeta del build macOS | | ídem | usa |
| `BUILD_OUT_IPA` | Builds | Carpeta del build iOS | | ídem | usa |
| `PYINSTALLER_BIN` | Máquina | Ruta de PyInstaller | `scope='machine'` | venv de la app, si no el PATH | usa |

Una clave `kind='list'` se edita multilínea y se guarda separada por comas; al leerla, `envfile.split_list` acepta comas y saltos de línea.

Un valor envuelto en comillas las pierde al leerse, pero solo si el **par** envuelve todo el valor: `strip("'")` se comía la última de `… frame-ancestors 'none'` y dejaba una CSP inválida.

## 2. Gramáticas de las claves compuestas

### `PUBLIC_ROUTES` — una regla por renglón

```
<patrón> <tipo> <destino>
```

- `patrón`: empieza con `/`, o es `*` (catch-all, siempre última). `/admin/*` recorta el prefijo `/admin`.
- `tipo`: `proxy` \| `spa` \| `static`.
- `destino`: `host:puerto` para `proxy`, el nombre de la carpeta de la SPA para `spa`, una ruta absoluta del VPS para `static`. Admite `$CLAVE`, que se resuelve contra la configuración.
- Sin comas en ningún valor: es el separador con el que se guarda la lista.

```
/api/*  proxy   $BACKEND_HOST:$BACKEND_PORT
/admin/* spa    backoffice
/files/* static /srv/archivos
*       spa     landing
```

`CADDY_ROUTES` es el nombre viejo y `vps.route_lines` todavía lo lee como respaldo ([30](30_riesgos_y_pendientes.md)).

### `SERVICE_DIRS` — una carpeta por renglón

```
<ruta absoluta> <modo octal>
```

Ejemplo: `/srv/datos/subidas 750`. Admite `$CLAVE`. Se vuelca a `/etc/tmpfiles.d/<servicio>.conf` como `d <ruta> <modo> <usuario> <usuario> -`.

### `SECRET_FILES` y `DB_EXTENSIONS`

Listas planas. Las rutas de `SECRET_FILES` son relativas a la raíz del repo y se suben a la misma ruta del lado del VPS, con `chmod 600`. No hay lista por defecto: el script original se equivocaba en las dos puntas, con tres nombres fijos más un barrido que mandaba a producción el `.env.example` y el de los tests.

## 3. `.consola/params.json`

```json
{
  "@tabs":       { "open": ["<capability_id>", "..."] },
  "@protection": { "vps": true, "db": true, "otros_repos": true,
                   "publicacion": true, "local": false, "origin": false },
  "<capability_id>": {
    "variants": { "<eje many>": ["valor", "..."] },
    "options":  { "<eje one>": "valor" },
    "fields":   { "<eje field>": "texto" },
    "picks":    { "<eje pick>": "valor" },
    "steps":    ["<step id>", "..."]
  }
}
```

Las claves con `@` no chocan con ningún `capability_id`. Escritura atómica (archivo temporal y `os.replace`), agrupada cada 500 ms.

## 4. `QSettings` (organización y aplicación: `Consola`)

| Clave | Qué |
|---|---|
| `projects/list` | JSON con los repos abiertos: ruta, nombre, color, icono, en orden |
| `projects/order` | Clave vieja; solo se borra en `clear()` |
| `favorites/ids` | Ids de las acciones favoritas |
| `favorites/only` | El interruptor «solo favoritos» |
| `ui/hidden_sections` | Secciones ocultas de la columna derecha |
| `params/machine/<capability_id>` | Parámetros de las acciones `scope='machine'` |
| `machine/<CLAVE>` | Valores de las claves `scope='machine'` de `core/settings.py` |

## 5. Archivos que Consola escribe

### En el repo abierto

| Ruta | Quién | Qué |
|---|---|---|
| `.consola/config.env` | `envfile.save_config` | Regenerado desde el esquema |
| `.consola/params.json` | `ui/params_store.py` | Parámetros, seguros y pestañas |
| `.consola/Caddyfile.generado` | `configure_caddy` | Copia de referencia, no fuente |
| `.gitignore` | `envfile.ensure_gitignored` | Agrega `.consola/` si falta |
| `<spa>/base.generated.js` | `compile_spa`, `create_spa` | `export const base = "…"` |
| `releases/<app>/<plataforma>.json` | Los tres builders | Manifiesto de release |
| `<app>/pyproject.toml` | `build_binary` | Solo si no había manifiesto: se crea en `0.0.0` |
| `.backups/<base>-<sello>.dump` | `backup_db` | Volcado `pg_dump -Fc`, rotado |
| El manifiesto de versión | `bump_version` | Solo la línea de la versión |
| `<spa>/` entera | `create_spa` | Una SPA nueva |

### En el VPS

| Ruta | Quién |
|---|---|
| `/etc/systemd/system/<repo>.service` | `write_systemd_unit` |
| `/etc/tmpfiles.d/<repo>.conf` | `write_service_dirs` |
| `/etc/turnserver.conf` | `configure_coturn` |
| `/etc/caddy/Caddyfile` | `configure_caddy` |
| `<VPS_DEPLOY_DIR>/<repo>/…` | El repo clonado, su venv, los secretos y los artefactos |
| `~/.ssh/authorized_keys`, la deploy key | `setup_ssh_key`, `setup_github_ssh` |
| `/etc/sudoers.d/consola-<usuario>` | `configure_sudo` |

### En esta máquina

| Ruta | Quién |
|---|---|
| `~/.ssh/<VPS_KEY_NAME>` y su `.pub` | `ensure_local_keypair` |
| `~/.ssh/known_hosts` | `refresh_known_host` (solo borra la entrada vieja) |
| `HKCU\Environment` o el perfil del shell | `core/userenv.py`, en un bloque delimitado |
| `%LOCALAPPDATA%\Consola\cache` o `~/.cache/consola` | `core/cache.py` |
| `%TEMP%/consola_ssh/` | Sockets de multiplexado y el helper de contraseña |

## 6. Formato del manifiesto de release

```json
{
  "app": "app",
  "platform": "apk",
  "version": "1.4.23",
  "build": 319,
  "artifact": "app-release.apk",
  "sha256": "…",
  "published_at": "2026-09-21T12:00:00Z"
}
```

`build` solo aparece si el manifiesto del subproyecto usa `+N`. `sha256` solo si el artefacto es un archivo: un build web es un árbol.

## 7. El catálogo, de un vistazo

61 capacidades. `C` = compuesta, `A` = atómica; `⌂` = `scope='machine'`.

| Grupo | Id | Botón | Tipo | |
|---|---|---|---|---|
| Ejecutar | `backend` | Levantar backend | A | `live`, vista web |
|  | `serve_vite` | Levantar SPA con Vite | A | `live`, vista web, `fanout` |
|  | `run_mobile` | Levantar app móvil | A | `live` |
|  | `run_python` | Levantar app de escritorio | C | `live`, `fanout` |
|  | `dev_env` | Levantar todo el entorno | C | `live`, concurrente, sin cuerpo |
| Compilar | `create_spa` | Crear SPA SvelteKit | A |  |
|  | `build_flutter` | Compilar app Flutter | C |  |
|  | `build_vite` | Compilar SPA | C |  |
|  | `build_binary` | Compilar ejecutable | C |  |
|  | `bump_version` | Subir número de versión | A | oculta |
|  | `promote_app` | Publicar en producción | A | destructiva |
|  | `clean_artifacts` | Borrar artefactos de build | A | destructiva |
| Repositorio | `clone_repo` | Clonar repositorio de GitHub | A | `opens_repo`, ⌂ |
|  | `sync_server_env` | Igualar claves de config.env y .env | A | destructiva |
|  | `sync_common_files` | Copiar archivos comunes a otros repos | A | destructiva |
|  | `git_force_push` | Force push | A | destructiva |
|  | `git_force_reset` | Force reset | A | destructiva |
| Base de datos | `bootstrap_db` | Configurar base de datos | C |  |
|  | `enable_extensions` | Habilitar extensiones | A |  |
|  | `migrate_db` | Correr migraciones | C | `requires_repo: migrations` |
|  | `run_seeders` | Correr seeders | A |  |
|  | `run_mock_seeders` | Correr mock seeders | A |  |
|  | `explore_db` | Explorar datos | A | `live`, vista db |
|  | `ssh_tunnel` | Abrir túnel a Postgres | A | `background` |
|  | `backup_db` | Respaldar base de datos | A |  |
|  | `rebuild_db` | Reconstruir base | C | destructiva |
|  | `reinit_migrations` | Reiniciar historial de migraciones | C | destructiva, `requires_repo: migrations` |
|  | `teardown_db` | Borrar base y rol | C | destructiva |
| Despliegue | `publish_code` | Desplegar | C | `live` |
|  | `update_remote` | Actualizar despliegue | C | `live` |
|  | `upload_secret_files` | Copiar archivos secretos | A |  |
|  | `configure_service` | Crear servicio systemd | C |  |
|  | `systemd_action` | Control del servicio | A |  |
|  | `view_logs` | Ver logs del servicio | A | `live` |
|  | `upload_to_vps` | Subir artefacto al VPS | A | oculta |
| VPS | `bootstrap_vps` | Configurar VPS | C |  |
|  | `install_software` | Instalar paquetes base | A |  |
|  | `setup_ssh_key` | Crear usuario y acceso SSH | C |  |
|  | `refresh_known_host` | Refrescar known_hosts | A |  |
|  | `setup_github_ssh` | Dar acceso a GitHub | C |  |
|  | `configure_caddy` | Configurar Caddy | C |  |
|  | `configure_coturn` | Configurar Coturn | C |  |
|  | `update_cloudflare` | Actualizar Cloudflare | A |  |
|  | `health_check` | Health check | A |  |
|  | `run_command` | Ejecutar comando | A |  |
|  | `ssh_login` | Abrir sesión SSH | A | interactiva |
|  | `revoke_ssh` | Quitar acceso SSH | C | destructiva |
|  | `revoke_github_ssh` | Revocar acceso a GitHub | C | destructiva |
|  | `clean_vps` | Vaciar VPS | C | destructiva |
| Emuladores | `install_system_image` | Instalar imagen de sistema | A | ⌂ |
|  | `create_avd` | Crear AVD | A | ⌂ |
|  | `launch_emulator` | Abrir emulador | A | `live`, ⌂ |
|  | `stop_emulator` | Apagar emulador | A | oculta, ⌂ |
|  | `purge_emulators` | Borrar AVDs e imágenes | A | destructiva, ⌂ |
| SDKs | `install_android_sdk` | Instalar SDK de Android | C | ⌂ |
|  | `install_android_tools` | Instalar command-line tools | A | ⌂ |
|  | `install_android_packages` | Instalar paquetes del SDK | A | ⌂ |
|  | `install_android_hypervisor` | Instalar aceleración del emulador | A | ⌂ |
|  | `install_flutter_sdk` | Instalar SDK de Flutter | A | ⌂ |

## 8. Características y tipos de subproyecto

`core/targets.py` reconoce, hasta dos niveles de profundidad y salteando `node_modules`, `.git`, `.venv`, `build`, `dist`, `.consola`, `__pycache__`, `.dart_tool`, `android`, `ios` y `web`:

| Tipo | Marcador |
|---|---|
| `spa-vite` | `package.json` + un `vite.config.*` |
| `flutter-app` | `pubspec.yaml` |
| `flet-app` | `pyproject.toml` que menciona `flet` |
| `fastapi-server` | `FastAPI(` en `app/main.py` o `main.py`, o `alembic.ini` + `app/main.py` |
| `python-app` | Manifiesto o `.venv`, más `src/main.py` o `main.py`, y que no sea servidor |

| Característica | Marcador |
|---|---|
| `migrations` | `alembic.ini` o `alembic/versions/` |

`MOBILE_APP` = Flutter + Flet; `DESKTOP_APP` = `python-app` + Flet. Una app Flet es móvil para los builds y de escritorio para el launcher, y eso es una propiedad de la carpeta, no una elección.

## 9. Estado de sesión (memoria)

| Clave | Ámbito | Quién la deja |
|---|---|---|
| `SERVER_PORT` | Proyecto | `resolve_server_port` |
| `@endpoints` → `backend`, `spa:<nombre>`, `explore_db:<scope>` | Proyecto | `ctx.serve` |
| La URL con contraseña del explorador | Proyecto | `ctx.publish` |
| `EMULATOR_SERIAL` | `@machine` | `launch_emulator` |

Estados de un endpoint: `starting`, `ready`, `down`.
