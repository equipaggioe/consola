# Plan — desplegar con el mecanismo de canone

> **Estado (verificado 2026-11-02).** Construidas las fases 0 a 2 (§6), salvo lo que espera otra
> fase o una pregunta. Fase 0: el despliegue propio salió (tag `despliegue-propio`,
> [ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md) a
> [0061](../adr/0061-los-forzados-corren-en-esta-maquina.md)). Fase 1: la configuración del §4
> ([ADR-0063](../adr/0063-las-lineas-de-config-env-se-clasifican-por-fuente.md) a
> [0065](../adr/0065-cada-spa-va-en-la-raiz-de-su-host.md)) y «Vaciar VPS» salió
> ([ADR-0062](../adr/0062-vaciar-vps-sale.md), *propuesta*). Fase 2: «Configurar VPS», «Instalar
> paquetes base» y «Cargar credenciales»
> ([ADR-0066](../adr/0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md)), corridos
> contra un VPS el 2026-11-02, sin la UI. Fase 3, del lado de Consola: «Publicar versión», «Desplegar versión» y
> el último paso de «Configurar VPS»
> ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)). «Publicar versión»
> corrió contra GitHub el 2026-11-01: `equipaggio` tiene `v0.1.0` publicado y firmado. El
> 2026-11-02, «Configurar VPS» desplegó esa versión en el VPS de prueba de `equipaggio`: la API
> responde por HTTPS, y la landing y el panel también (30, «Sin verificar»). Lo que hay está en
> [13](../arquitectura/13_configuracion_y_persistencia.md) y
> [15](../arquitectura/15_vps_y_despliegue.md); manda la arquitectura. Fase 4: los botones que
> operan el VPS y «Ver eventos» ([ADR-0068](../adr/0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md)),
> corridos contra un VPS el 2026-11-02, sin la UI. Fase 5: `backend` con `credentials/` y Alembic
> con `credentials-migrate/` ([ADR-0069](../adr/0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md)),
> corridos contra la base local de `equipaggio`; `sync_server_env` salió.
>
> **Para retomar en otro chat:** leer `canone/principios.md` y `canone/documentacion.md`, este
> plan (sobre todo el §6 y el §8) y los ADR 0059 a 0067. `equipaggio` ya sigue la plantilla de
> canone y tiene `v0.1.0` firmado con `vps_xs1` (fases 1 a 5 de su `desplegar_con_canone.md`).
> Lo que sigue es probar desplegar una versión encima de otra y llevar los repos a la plantilla de
> canone (§6, «Lo que le falta a cada repo»).
>
> Este plan sale de leer canone en `b405874` (revisado el 2026-10-31; las lecturas anteriores
> fueron en `03bc3c8`, `24b0396`, `cc9a48d` y `2ed25d2`) y el código de Consola. De `2ed25d2` a
> `b405874`, fuera del ADR-0107, canone revisó sus fuentes (ADR-0108 y 0109): de `plantilla/infra/`
> cambian solo los sitios de Caddy, `nftables.conf`, `turn.nft` y `turnserver.conf`, y la
> restauración suma `ANALYZE` (§5). La interfaz de `install.py`, `credentials.py`, `deploy.py` y
> los scripts de la receptora no cambia. `026c878` suma `uv.py`, que instala uv
> (ADR-0110). Desde `24b0396` canone
> commiteó los ADR 0088 a 0106; los que cambian este plan son el 0096 (coturn), el 0100 y 0101
> (registros), el 0104 (firmantes), el 0105 (`credentials.py`) y el 0106 (`deploy.py` instalado).
> `2ed25d2` suma `ca-certificates` a los paquetes de la máquina. El ADR-0107 saca a Consola de las
> reglas de canone: canone fija sus programas por su interfaz, y cómo Consola junta y guarda sus
> datos lo decide Consola. Nada se ejecutó desde Consola: los conflictos y los fallos marcados son
> **sin confirmar**.
>
> **Decidido el 2026-10-25:** corte limpio. Los botones del despliegue propio salen y no conviven
> con los nuevos; el código viejo queda en el tag `despliegue-propio` (§6, fase 0).
>
> **Decidido el 2026-10-30:** las preguntas 2, 4, 5, 7, 9, 10, 11, 12, 13 y 14 del §8.
>
> **Decidido el 2026-10-31:** la pregunta 8 del §8; los nombres de los botones y sus casillas
> (§3), `--without` (§4) y las fases (§6) quedan como dice el plan; el repo piloto es `equipaggio`
> (§6). Para la fase 3: el número de la versión, cómo elige «Desplegar versión» y qué instala el
> primer despliegue (ADR-0067), y seguir con `equipaggio` como piloto, empezando por P1 y P2.
>
> **Prioridad (decidido el 2026-10-31):** el objetivo de este plan es desplegar. Lo que no
> despliega (los botones de base con ámbito remoto, «Compilar ejecutable», la plataforma web,
> `sync_server_env`, borrar `scripts/`) es secundario y espera, sin bloquear las fases 2 y 3.
>
> **Objetivo (decidido el 2026-11-02):** que Consola trabaje de acuerdo a canone. Dejar `equipaggio`
> en marcha no es el objetivo: es el repo con el que se prueba, y P3, P4 y su fase 7 esperan.
>
> **Decidido el 2026-11-02:** las fases 6 (receptora y respaldo) y 7 (`clean_vps`) quedan pendientes.
> Hasta la 6, un VPS de canone no tiene respaldo.
>
> Lo que fija canone está decidido en sus ADR. Lo demás que este plan dice sobre Consola es
> *propuesta* hasta que se responda su pregunta en el §8.

## 1. Qué fija canone

| Tema | Regla | ADR de canone |
|---|---|---|
| Reparto | canone fija las reglas, da las plantillas y fija cada programa por su interfaz (argumentos y stdin); no nombra la herramienta que los corre. El repo declara su nombre, sus superficies y los campos de `Settings`. Quien despliega, como Consola, no escribe encima de lo que instalan los programas: ni unidades, ni configuración, ni scripts propios | [0075](../../../canone/adr/0075-canone-fija-el-repositorio-declara-y-consola-dispara.md), [0107](../../../canone/adr/0107-canone-fija-la-interfaz-de-sus-programas-y-no-la-herramienta-que-los-corre.md) |
| Plantillas | La que se copia (`release.yml`) vive en el repo; las que se instalan (`infra/`, con su `deploy.py`) se toman de canone | 0107, [0106](../../../canone/adr/0106-deploy-py-se-instala-desde-plantilla-infra-con-los-datos-de-la-app.md) |
| Configuración | Lo que cambia entre despliegues, secreto o no, no se commitea, y llega al servidor como argumento de `install.py` (como el dominio y la memoria) o por `credentials.py`; canone no fija dónde lo guarda Consola. `credentials.py <app>` lee por stdin una línea `campo=valor` y cifra cada campo de `Settings` en `<app>/`, `restic_password` en `<app>-backup/` y `github_token` en `<app>-deploy/`. Rechaza `database_url` y `turn_secret`, que escribe `install.py`. Escribe solo lo que recibe y reinicia el servidor si corre | [0076](../../../canone/adr/0076-lo-que-cambia-entre-despliegues-sale-de-un-solo-archivo-y-lo-demas-es-codigo.md), [0105](../../../canone/adr/0105-las-credenciales-las-cifra-credentials-py-de-canone-y-consola-solo-se-las-pasa.md), 0107 |
| Máquina | Un VPS aloja un solo producto. El servidor escucha siempre en 8000 | [0077](../../../canone/adr/0077-un-vps-aloja-un-solo-producto.md) |
| Versión | Tag `vX.Y.Z` → `release.yml` publica `.tar.gz` y `.sha256` (borrador hasta tener el `.sha256`) → se firma fuera de GitHub con `ssh-keygen -Y sign -n deploy` → `sudo python3 /usr/local/lib/<app>/deploy.py vX.Y.Z` por `ssh`. `deploy.py` lo instala `install.py`; ya no viaja en el release. Comprueba el certificado de GitHub con los de `ca-certificates`. En un repo privado lee el token de `<app>-deploy/github_token` y no lo sigue a otro host. Cada versión crea su entorno con `uv sync --locked --no-dev` | 0068, 0090, 0091, 0106 |
| Instalación | `python3 install.py <app> <dominio> <memoria> --owner <dueño GitHub> --admin <cuenta> --key <llave> --key <llave> --signer <llave> --signer <llave> [--private] [--desktop linux\|windows\|macos]… [--without sweep\|web\|panel\|landing] [--allow <función>] [--extension <nombre>] [--turn [--turn-ip <IPv4>]] [--logs <host:puerto> --logs-key <llave> --logs-ip <IPv4>]`. La primera vez corre como root y **pide por consola** la contraseña de la cuenta; después, con `sudo` desde ella, y `--admin`, `--key` y `--signer` solo agregan llaves. Falla con menos swap que RAM, sin `sudo`, sin `systemd-timesyncd`, sin `ca-certificates`, sin `--owner`, con una llave ilegible, con una sola llave (de cuenta o de firma) en una máquina nueva, si la cuenta es `<app>`, `<app>_owner` o `<app>-receiver`, o sin `--logs` en una máquina que ya envía. No instala paquetes ni uv | 0069, 0077, 0084, 0087, 0096, 0100, 0102, 0104, 0106 |
| uv | `sudo python3 uv.py` instala en `/usr/local/bin/uv` la versión de `python.md`, del release de GitHub, y falla sin instalar nada si el archivo no tiene el SHA-256 que fija para `x86_64` o `aarch64`. Corre antes del primer `deploy.py` y otra vez cuando cambia la versión. `install.py` no lo instala ni lo comprueba | 0090, [0110](../../../canone/adr/0110-uv-lo-instala-uv-py-con-su-version-y-su-sha-256-fijos.md) |
| SSH | `sshd` solo acepta llaves y root no entra (`00-<app>.conf`); `install.py` bloquea la contraseña de root. `sudo` pide la contraseña de la cuenta; cuándo la pide quien despliega no lo fija canone | [0084](../../../canone/adr/0084-ssh-solo-acepta-llaves-y-root-no-entra.md), 0107 |
| Base | `install.py` crea la base `<app>`, el rol `<app>` (servidor) y `<app>_owner` (dueño). Ninguno es superusuario ni tiene contraseña: entran por el socket con `peer`, desde la cuenta de su nombre. Escribe las dos `database_url` cifradas en `<app>/` y `<app>-migrate/` | [0083](../../../canone/adr/0083-la-base-y-sus-roles-los-crea-install-py-y-el-servidor-entra-por-peer.md), [0085](../../../canone/adr/0085-el-dueno-del-esquema-entra-por-peer-con-su-cuenta-y-corre-el-volcado.md) |
| Migraciones | `<app>-migrate@<v>.service`, con `<app>-migrate/database_url` del dueño del esquema (`<app>_owner`). El rol del servidor no tiene DDL | 0068, 0085 |
| Respaldo | Lo pide una receptora (`plantilla/receiver/`): `rest-server --append-only` en su 8001 y túnel `ssh -R` con la cuenta `<app>-receiver`, cuyas llaves van en `/etc/<app>/receivers`. Única credencial: `restic_password`. Equipaggio deja de respaldar las bases | [0078](../../../canone/adr/0078-el-respaldo-lo-pide-una-receptora-y-lo-guarda-su-rest-server.md) |
| Operación del respaldo | canone no fija dónde se guarda una copia de `restic_password` ni la limpieza del repositorio de la receptora | [0079](../../../canone/adr/0079-canone-no-fija-la-operacion-del-respaldo.md) |
| Alertas | `GET /api/health/events` responde `lastCriticalAt`, `lastEventAt`, `lastBackupAt`, `diskFreeBytes` y `diskTotalBytes` con `Authorization: Bearer <health_token>`. Quien consulta decide cuándo avisar | [0080](../../../canone/adr/0080-la-purga-de-event-log-es-una-funcion-y-una-ruta-de-salud-dice-que-alertar.md), [0082](../../../canone/adr/0082-la-ruta-de-salud-dice-cuanto-disco-queda.md), [0097](../../../canone/adr/0097-la-ruta-de-salud-dice-cuando-fue-el-ultimo-evento.md) |
| Purga | Tarea diaria `python -m app.tasks purge`, con la cuenta `<app>_owner` y `app_database_url` de `<app>-migrate/` | 0081 |
| Rol de la app | Se llama como la app y solo tiene `INSERT` y `SELECT` sobre `event_log` | 0080 |
| Volcado | Corre como `<app>_owner`; no lleva roles ni extensiones, que crea `install.py` | 0085 |

## 2. Conflictos con un VPS instalado con canone *(sin confirmar)*

C1 a C3 se resolvieron en la fase 0: `configure_caddy`, `configure_service` y el paso que borraba
las unidades salieron. C7 —«Vaciar VPS» borraba la cuenta que administra y dejaba la máquina sin
entrada— se resolvió en la fase 1: el botón salió (ADR-0062). C5 —el launcher `backend` pasaba
`DATABASE_URL`, y `Settings` de canone no arrancaba sin `CREDENTIALS_DIRECTORY`— se resolvió en la
fase 5 (ADR-0069). C6 —`setup_ssh_key` creaba la
cuenta con `sudo` sin contraseña— se resolvió en la fase 2: salió, y la cuenta la crea
`install.py` (ADR-0066).

## 3. Botones

Decidido el 2026-10-31: los nombres de los botones y qué es casilla de una compuesta quedan como dice esta sección.

### Qué reemplaza a cada botón actual

| Botón actual | Pasa a | Qué cambia |
|---|---|---|
| **Desplegar** (`publish_code`) | **Publicar versión** | Compuesta: crea el tag, espera `release.yml`, firma el `.sha256` y despliega |
| **Actualizar despliegue** (`update_remote`) | **Publicar versión** | Cada actualización es un tag nuevo |
| **Publicar en producción** (`promote_app`) | **Desplegar versión** | Instala un tag ya publicado: volver a desplegar o volver a una versión anterior |
| **Copiar archivos secretos** (`upload_secret_files`) | **Cargar credenciales** | Pasa los valores de `config.env` a `credentials.py` en vez de copiar archivos |
| **Crear servicio systemd** (`configure_service`) | Casilla de **Configurar VPS** | La unidad la instala `install.py` |
| **Configurar Caddy** (`configure_caddy`) | Casilla de **Configurar VPS** | El Caddyfile y los sitios los instala `install.py` |
| **Dar acceso a GitHub** (`setup_github_ssh`) | Sin reemplazo | El VPS no clona. En un repo privado, `install.py --private` y el token como `github_token` en **Cargar credenciales** |
| **Revocar acceso a GitHub** (`revoke_github_ssh`) | Sin reemplazo | No hay llave de GitHub en el VPS |
| **Configurar VPS** (`bootstrap_vps`) | **Configurar VPS** | Paquetes → swap → `install.py` → credenciales → firmante → receptora → primer despliegue |
| **Instalar paquetes base** (`install_software`) | Se queda | `redis` pasa a `valkey-server`; se suman `restic`, `nftables`, `unattended-upgrades`, `systemd-timesyncd` y `ca-certificates`, y `coturn`, `postgresql-17-postgis-3` o `systemd-journal-remote` y `wireguard-tools` según el repo. Después de los paquetes, sube `canone/plantilla/infra/uv.py` y corre `sudo python3 uv.py`, que instala `uv` (ADR-0110). Se vuelve a correr cuando canone cambia la versión de uv |
| **Control del servicio** (`systemd_action`), **Ver logs del servicio** (`view_logs`) | Se quedan | El eje lista los nombres de canone: `<app>`, `<app>-sweep`, `-purge`, `-dump`, `-backup`, `valkey-server@<app>`, `caddy`, `coturn` |
| **Health check** (`health_check`) | Se queda | `GET /api/health` en el 8000, que responde 204 |
| **Vaciar VPS** (`clean_vps`) | Salió en la fase 1 (ADR-0062). Vuelve cuando canone traiga el programa que desinstala (§5) | Borra unidades de canone, `/srv/<app>`, `/var/lib/<app>*`, credstore, sitios de Caddy, Valkey, `sshd_config.d`, la base y sus roles, y los usuarios `<app>`, `<app>_owner` y `<app>-receiver`. Queda en pie `00-<app>.conf` y la cuenta que administra, o la máquina queda sin entrada (sin confirmar) |
| **Configurar Coturn** (`configure_coturn`) | Casilla de **Configurar VPS** | `install.py --turn [--turn-ip]`: sin TLS, y el secreto lo genera `install.py` (ADR-0096) |
| **Configurar base de datos** (`bootstrap_db`) en el VPS | Sin reemplazo | `install.py` crea la base y los dos roles. En local sigue igual |
| **Correr migraciones** (`migrate_db`) en el VPS | **Desplegar versión** | En el VPS migra `deploy.py`. En local sigue igual |
| **Compilar SPA** (`build_vite`), **Compilar app Flutter** (`build_flutter`) | Se quedan | Sin subida al VPS ni `bump_version`: la web la construye el CI, y el APK sale del VPS (pregunta 4) |
| **Compilar ejecutable** (`build_binary`) | Sin decidir | El CI empaqueta `desktop/` con `pyside6-deploy` |
| **Respaldar base de datos** (`backup_db`) en el VPS | **Pedir respaldo** | El respaldo del servidor lo pide la receptora (pregunta 5). En local sigue igual |
| **Restaurar base de datos** (`restore_db`) en el VPS | Espera el programa de canone (§5) | En local sigue igual (pregunta 5) |
| **Igualar claves de config.env y .env** (`sync_server_env`) | Sin reemplazo | No hay `.env` en el servidor, y el launcher `backend` escribe `server/credentials/` desde `config.env` (pregunta 8) |
| **Force push**, **Force reset** | Se quedan | El eje `side` pierde `vps` |
| — | **Instalar receptora** | Agrega la llave de la receptora a `/etc/<app>/receivers`: `install.py` deja el archivo vacío y el ADR-0078 dice que la agrega quien despliega |
| — | **Pedir respaldo** | Corre el script de `canone/plantilla/receiver/` según el sistema de la receptora: `backup.sh` en Linux y macOS, `backup.ps1` en Windows. La receptora es esta máquina (pregunta 9) |
| — | **Ver eventos** | `GET /api/health/events` con `health_token`: `lastCriticalAt`, `lastEventAt`, `lastBackupAt` y el disco libre y total |

Las atómicas ocultas `upload_to_vps` y `bump_version` salen con los botones que las usan.

### Qué hace cada paso nuevo

| Paso | Dónde va | Qué hace |
|---|---|---|
| Crear swap | Casilla de **Configurar VPS** | Sin swap igual a la RAM, `install.py` falla |
| Instalar infraestructura | Casilla de **Configurar VPS** | Sube `canone/plantilla/infra/` y corre `install.py <app> <dominio> <memoria> --owner` con `--admin`, `--key` y `--signer` (dos de cada una, la primera vez), `--private`, `--desktop`, `--without`, `--allow`, `--extension`, `--turn`/`--turn-ip` y `--logs*` (los tres juntos, en cada corrida si la máquina ya envía). La primera vez entra como root con la llave `VPS_KEY_NAME` que se puso al crear el VPS, y pide dos veces la contraseña de la cuenta: Consola corre `ssh -tt` y escribe `SUDO_PASSWORD` solo cuando aparece «Password of» y después «Again», porque escrita antes la terminal remota la repite y queda en el log. Probado el 2026-10-31 con el `ssh.exe` de Windows, desde Python con stdin y stdout en tuberías, contra el sshd de Debian 13.7 en WSL y no en un VPS, con las dos llamadas a `getpass` de `create_admin`: escrita tras cada petición, la contraseña llega y no aparece en la salida (3 de 3 corridas); escrita antes, la salida la muestra dos veces, `getpass` la descarta y el programa queda esperando. Reemplaza a `setup_ssh_key.py` (pregunta 12). Reinstalar hace falta al agregar un instalable o pasar a privado (ADR-0106) |
| Cargar credenciales | Botón y casilla de **Configurar VPS** | Sube `canone/plantilla/infra/credentials.py` (`install.py` no lo instala) y le pasa por stdin, con `sudo python3 credentials.py <app>`, una línea `campo=valor` por cada valor de `config.env` que es credencial, con `sudo`. No se cargan `database_url` ni `turn_secret`: los escribe `install.py` |
| Instalar firmante | Parte de **Instalar infraestructura** | Los `--signer`: la pública de `VPS_KEY_NAME` y la de la llave guardada fuera, las mismas dos de `--key` (pregunta 11). `install.py` escribe `allowed_signers` solo para el espacio de nombres `deploy` |
| Crear tag | Casilla de **Publicar versión** | Crea `vX.Y.Z`, lo empuja y espera `release.yml` (`gh run watch`) |
| Firmar release | Casilla de **Publicar versión** | `gh release download -p "*.sha256"` → `ssh-keygen -Y sign -n deploy` con `VPS_KEY_NAME` → `gh release upload` del `.sig` |
| Desplegar | Casilla de **Publicar versión** y botón **Desplegar versión** | `ssh … sudo python3 /usr/local/lib/<app>/deploy.py vX.Y.Z`. Lo instaló `install.py`: no se copia nada, ni la primera vez |

### Fuera de los botones

| Pieza | Cambio |
|---|---|
| Launcher `backend` | Escribe en `server/credentials/` un archivo `app_<campo>` por cada campo de `Settings`, con los valores de `config.env` y el `DATABASE_URL` local, y arranca con `CREDENTIALS_DIRECTORY` apuntando ahí (C5, pregunta 8) |
| Contraseña de `sudo` | Cada operación con `sudo` (desplegar, cargar credenciales, `systemctl`, vaciar) la pasa por `sudo -S` desde `SUDO_PASSWORD`. Si está vacía, la pide una vez por sesión y la tiene solo en memoria |
| `.consola/` | Hecho en la fase 1: `envfile.ensure_ignored` escribe `.consola/.gitignore` con `*` y falla si no puede (ADR-0064) |

## 4. Configuración (`core/settings.py`)

| Salen | Entran |
|---|---|
| `VPS_DEPLOY_DIR`, `VPS_PYTHON`, `SECRET_FILES`, `GITHUB_KEY_TITLE` | `DOMAIN`, o derivado de `CF_DOMAIN_NAME` |
| `PUBLIC_ROUTES`, `CSP`, `SERVICES`, `SERVICE_DIRS` | `VALKEY_MEMORY`, sin valor por defecto |
| `BACKEND_HOST`, `BACKEND_PORT` (ADR-0077: siempre 8000), `UVICORN_APP` | `PERMISSIONS_ALLOW`, la lista de `--allow` |
| `CERT_FILE_PATH`, `KEY_FILE_PATH` | La llave pública de la que se guarda fuera de esta máquina: con la de `VPS_KEY_NAME`, son las dos `--key` y las dos `--signer` (pregunta 11) |
| `BUILD_OUT_WEB` | Los campos de `Settings` del repo, con sus valores de producción (ADR-0076), sin `database_url` ni `turn_secret` |
| `GIT_REPO_URL` como origen del clon | `RESTIC_PASSWORD` y, en un repo privado, `PRIVATE` y el token de solo lectura (`github_token`) |
| `VPS_USER` con valor por defecto | `VPS_USER` sin valor por defecto: la cuenta de `--admin`, que no puede llamarse `<app>` (C6) |
| | `SUDO_PASSWORD`: la contraseña de esa cuenta. Vacía, Consola la pide (pregunta 12) |
| | `HEALTH_TOKEN`, campo de `Settings`: lo genera el monitor de Equipaggio (pregunta 10) |
| | `TURN` y `TURN_IP` |
| | `LOGS_IP`, por repo. `LOGS` y `LOGS_KEY`, del VPS de Equipaggio, van en la configuración global de Consola (pregunta 13) |

Sin clave, porque salen del repo:

| Flag | De dónde |
|---|---|
| `--owner` | `git remote get-url origin`: el dueño (usuario u organización) en `github.com/<dueño>/<repo>` |
| `--desktop` | Cada `desktop-<os>` del `release.yml` del repo |
| `--without` | Lo que el repo tiene (`web/`, `panel/`, `landing/`) |
Para `sweep` no hay una señal en el repo: la plantilla trae la tarea siempre.

Construido en la fase 1 *(propuesta, sin confirmar en lo que no responde una pregunta)*:

| Clave | Estado |
|---|---|
| `SECRET_FILES`, `CSP`, `SERVICE_DIRS`, `BACKEND_HOST`, `BACKEND_PORT`, `CERT_FILE_PATH`, `KEY_FILE_PATH` | Salieron en la fase 0 |
| `PUBLIC_ROUTES` | Salió, con `base.generated.js` y la comprobación del HTML (ADR-0065, *propuesta*) |
| `GITHUB_KEY_TITLE` | Salió con «Vaciar VPS» |
| `VPS_USER` | Sin default. `DB_USER` y `DB_NAME` pasan a salir del nombre del repo, que es lo que daban cuando `VPS_USER` estaba vacío |
| `VPS_DEPLOY_DIR`, `VPS_PYTHON` | Quedan: las lee la subida de «Compilar ejecutable» (sin decidir) y el ámbito remoto de la base (pregunta 15) |
| `SERVICES`, `UVICORN_APP`, `GIT_REPO_URL` | Quedan: dan los nombres del eje `service`, que la fase 4 cambia por los de canone |
| `BUILD_OUT_WEB` | Queda (pregunta 17) |
| `DOMAIN`, `VALKEY_MEMORY`, `PERMISSIONS_ALLOW`, `TURN`, `TURN_IP`, `LOGS_IP`, `PRIVATE`, `SUDO_PASSWORD` | Entraron, en el grupo VPS o GitHub. Las lee la fase 2 |
| `RESTIC_PASSWORD`, `GITHUB_TOKEN` | En el grupo «Credenciales» |
| Los campos de `Settings` | `core/fields.py` los lee con `ast` y el formulario los suma a «Credenciales» (ADR-0063) |
| `OFFLINE_KEY`, `LOGS`, `LOGS_KEY` | Entraron como claves de la máquina (`scope='machine'`), porque son las mismas para todos los VPS (*propuesta*) |
| `--owner`, `--desktop`, `--without` | Hechos en la fase 2 (`core/canone.py`) |

## 5. Bloqueos en canone

El `README.md` de canone dice que lo que una convención exige en una máquina, canone lo da como el
programa que la deja así. Consola adopta además la regla (pregunta 14): lo que deja un cambio
permanente en el VPS y ningún programa de canone hace se agrega primero a canone. No alcanza a lo
que corre en esta máquina (compilar, tag, firma), ni a correr lo que canone ya instaló (`deploy.py`,
`credentials.py`, `systemctl`, logs, salud), ni a lo que canone deja expresamente a quien despliega,
como la llave de una receptora.

| Falta | Qué bloquea |
|---|---|
| Restaurar desde la receptora. `despliegue.md` describe el `restic restore`, el `pg_restore` y después `ANALYZE`, pero canone no trae un programa | Un reemplazo de `restore_db` |
| Desinstalar lo que instala `install.py` | **Vaciar VPS** |
| Volver a una versión que sigue en `/srv/<app>/releases/`: `deploy.py` falla si la carpeta de la versión existe, y ahí quedan las cinco más nuevas *(hallazgo de lectura, sin confirmar)* | Que «Desplegar versión» vuelva a la activa o a una de esas cinco |
| Operar la base del VPS desde esta máquina: los roles entran por `peer` y no tienen contraseña, así que el túnel al 5432 no se autentica *(sin confirmar)* | El ámbito remoto de «Reconstruir base», «Borrar base y rol», «Reiniciar historial de migraciones», los seeders, «Habilitar extensiones», «Explorar datos» y «Abrir túnel a Postgres» (pregunta 15) |

Hallazgo de lectura en canone *(sin confirmar)*: `backup.sh` y `backup.ps1` llaman a `ssh` sin
`-i`, así que usan la llave por defecto de la receptora y no una con nombre como `VPS_KEY_NAME`.
Con esta máquina como receptora (pregunta 9), **Instalar receptora** tiene que agregar la pública
de esa llave por defecto, o canone tiene que sumar un `-i` a los dos scripts.

El ADR-0107 corrigió en «Quién hace qué» del `README.md` el puerto, el dominio y la memoria, que
figuraban entre los datos del repo.

## 6. Fases

| Fase | Qué | Depende de |
|---|---|---|
| 0 | Crear el tag anotado `despliegue-propio` en el último commit con el despliegue propio. Quitar los botones que salen en el §3, empezando por `configure_caddy` y `configure_service`, y sacar `remove_systemd_service` de `clean_vps`: son los que rompen un VPS con canone (C1–C3). `setup_ssh_key.py` (C6) se resuelve en la fase 2. El ADR que reemplace al 0001 nombra el tag | — |
| 1 | Configuración del §4 | — |
| 2 | Instalar paquetes (con `uv.py`), infraestructura (con firmantes y coturn) y cargar credenciales | Fase 1 |
| 3 | Publicar, firmar y desplegar versión | Fase 2 y el repo piloto |
| 4 | `systemd_action`, `view_logs`, `health_check`, ver eventos | Fase 2 |
| 5 | `backend` con `credentials/` (C5) y salida de `sync_server_env` | Fase 1 |
| 6 | Instalar receptora y pedir respaldo | Fase 2 |
| 7 | `clean_vps` nuevo | Fase 2 y el desinstalador del §5 |

Las fases 0 a 4 son las que despliegan los repos y van primero. Las 5 a 7 no hacen falta para
desplegar. Las fases 6 y 7 quedan pendientes (decidido el 2026-11-02).

La fase 0 está construida. Cómo se leyó en el código lo que el §3 dice que sale *(propuesta, sin
confirmar)*:

| Pieza | Qué se hizo |
|---|---|
| «Configurar VPS» (`bootstrap_vps`) | Salió entero: sus pasos eran el despliegue propio. La fase 2 trae el nuevo |
| `setup_ssh_key`, `install_software` | Quedan como estaban, hasta la fase 2 |
| «Compilar ejecutable» | Queda con el bump, la subida al VPS y el manifiesto de release, porque su reemplazo está sin decidir; por eso `bump_version` y `upload_to_vps` siguen |
| «Compilar app Flutter», «Compilar SPA» | Sin bump ni subida: solo compilan |
| Los cuatro botones de base del §3 | Sin eje `scope`: solo la base local (ADR-0060) |
| Los demás botones de base con ámbito remoto | Quedan como estaban hasta resolverlos en canone (pregunta 15, §5) |
| «Force push», «Force reset» | Sin eje `side` (ADR-0061) |
| «Vaciar VPS» | Sin el paso de las unidades. En la fase 1 salió entero (ADR-0062) |
| `sync_server_env` | Quedó hasta la fase 5, que lo sacó |
| Claves de configuración | Salieron las que solo leían los botones que salen (ADR-0059). Las demás del §4 salen en la fase 1 |
| `scripts/` | Se queda entera hasta que el despliegue con canone funcione; después se borra (pregunta 16) |

El repo piloto es `equipaggio`. Ningún repo con `server/` puede publicar hoy una versión
(verificado el 2026-10-31): ninguno tiene `release.yml`, solo banditore, comande y concordia tienen
`ci.yml`, siete siguen con `requirements.txt` en vez de uv, ninguno compila catálogos con `babel`,
y casi ninguno tiene `pnpm-lock.yaml` en cada pieza web. La plantilla de `release.yml` construye
una sola pieza web (`PIEZA`), y `equipaggio` tiene `panel/` y `landing/`. El piloto se lleva a la
plantilla de canone, con su `ci.yml` y su `release.yml`, antes de cerrar la fase 3; los demás
repos lo siguen después.

La fase 2 está construida y corrió contra un VPS el 2026-11-02, sin la UI *(lo que no responde
una pregunta es propuesta, sin confirmar)*:

| Pieza | Qué se hizo |
|---|---|
| «Configurar VPS» (`bootstrap_vps`) | Pasos: refrescar known_hosts (desmarcado), paquetes y uv, swap, `install.py`, credenciales. La receptora se suma en la fase 6; el primer despliegue entró en la fase 3 |
| «Instalar paquetes base» | Sin eje: los paquetes salen del repo (`canone.packages`) y después corre `uv.py` |
| Swap | `/swapfile` con lo que falta para igualar la memoria, en `/etc/fstab`. Casilla, sin botón |
| `install.py` | Casilla, sin botón. Primera vez como root por `ssh -tt` con `process.converse`; después con `sudo -S` |
| «Cargar credenciales» (`load_credentials`) | Botón y casilla. Sube `credentials.py` y le pasa las líneas por stdin, detrás de la contraseña de `sudo` |
| Acceso | `vps_setup.access`: la cuenta de `VPS_USER` si entra, si no root. La contraseña de `sudo`, de `SUDO_PASSWORD` o pedida una vez por sesión |
| `CANONE_DIR` | Clave nueva de la máquina: la copia local de canone de la que se suben los programas |
| `setup_ssh_key` | Salió (C6), con el `sudo` sin contraseña y la contraseña de root por `SSH_ASKPASS` |

Para la fase 3, el piloto `equipaggio` tiene su `.github/workflows/ci.yml` y su `release.yml`,
de la plantilla de canone con las piezas que tiene (`server/`, `panel/`, `landing/`, `mobile/`,
`packages/licenses/`): `mypy` en vez de `pyrefly`, sin `pybabel compile` porque no tiene
catálogos, y un artefacto con `panel/` y `landing/` y sin instaladores de escritorio. El CI está
en verde, y el 2026-11-01 «Publicar versión», llamada sin la UI, creó `v0.1.0`, siguió
`release.yml` y lo firmó con `vps_xs1`.

La fase 3 está construida del lado de Consola y corrió contra GitHub. `deploy.py` corrió contra
un VPS desde «Configurar VPS»; falta «Desplegar versión» y desplegar una versión sobre otra
([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md); lo que no responde una
pregunta es propuesta):

| Pieza | Qué se hizo |
|---|---|
| «Publicar versión» (`publish_release`) | Eje `part` (major, minor, patch) sobre el tag `v*` más alto de origin. Pasos: crear tag (corta con cambios sin commitear o commits sin empujar, empuja el tag y sigue `release.yml` con `gh run view` cada 15 s), firmar (`ssh-keygen -Y sign -n deploy` con `VPS_KEY_NAME`; no firma dos veces) y desplegar. Sin «Crear tag», toma el último release |
| «Desplegar versión» (`deploy_version`) | Eje `version` con los releases publicados que tienen su `.sig` (`gh api`) |
| «Configurar VPS» | Último paso: el release `latest`, si tiene firma; nada si `current` ya es ese |
| `gh` | Hace falta GitHub CLI con `gh auth login`. Esta máquina no lo tiene (2026-10-31) |

Lo que impide desplegar `equipaggio` con canone, además de los workflows:

| # | Bloqueo | Evidencia |
|---|---|---|
| P1 | ~~El job `canone` del CI falla: 12 archivos de `server/` no coinciden con los canónicos~~. Resuelto en `equipaggio`: `verificar.py --repo .` no da incumplimientos | Corrido el 2026-11-01 |
| P2 | ~~Su configuración no sigue la plantilla~~. Resuelto en `equipaggio`: una sola `Settings` lee los `app_<campo>` de `CREDENTIALS_DIRECTORY` | `server/src/app/config.py` |
| P3 | Corre seis procesos (API, `prober`, `gateway` en el 8011, `mailer`, `webhooks`, `bounces` con SMTP en el 2525) y canone instala uno, `<app>.service` con uvicorn en el 8000, más el barrido y la purga. Por la regla de la pregunta 14, las unidades, la ruta del gateway y el puerto de SMTP van primero a canone *(sin confirmar qué hace falta)* | README de `equipaggio`, `PRODUCTO.service` de canone |
| P4 | Escribe en `STATE_DIRECTORY` los `[Peer]` del túnel de registros, que aplica una unidad propia de root (ADR-0026 de `equipaggio`); canone no la instala | `server/src/app/config.py`, ADR-0026 de `equipaggio` |

Las fases 4 y 5 están construidas y corrieron el 2026-11-02 sin la UI, la 4 contra el VPS de prueba
y la 5 contra la base local de `equipaggio`
([ADR-0068](../adr/0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md) y
[ADR-0069](../adr/0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md)). Lo que no
resuelven está en el 30, «Sin decidir».

### Lo que le falta a cada repo

Verificado el 2026-10-31, salvo lo que se dice: ningún repo con `server/` fuera de `equipaggio` puede
publicar una versión. Antes de apretar «Configurar VPS», cada uno necesita:

| Qué | Cómo se comprueba |
|---|---|
| Seguir la plantilla de canone, con `Settings` en `server/src/app/config.py`, su `ci.yml` y su `release.yml` | `python ../canone/scripts/verificar.py --repo .` no da incumplimientos y el CI está en verde |
| Un solo proceso largo. Un repo con más necesita primero sus unidades en canone, como P3 de `equipaggio` | Lo que corre es `app.main:app` en el 8000 |
| `credentials/` y `credentials-migrate/` en el `.gitignore` de `server/` | `git check-ignore`; si no, Consola corta |
| Borrar `SERVICES` y `UVICORN_APP` de su `config.env`. Las tienen `banditore`, `cadenza`, `concordia`, `consola`, `navetta`, `presenze`, `pze` y `vettore` (visto el 2026-11-02) | «Cargar credenciales» corta con cualquier clave sin fuente |
| En `config.env`: `VPS_IP`, `VPS_USER`, `VPS_KEY_NAME`, `DOMAIN`, `VALKEY_MEMORY`, `SUDO_PASSWORD` si no se quiere escribir cada vez, `RESTIC_PASSWORD`, los campos de `Settings` y, si es privado, `PRIVATE` y un `GITHUB_TOKEN` de solo lectura. En desarrollo, además, `DATABASE_URL` | El panel marca lo que falta |
| Un Debian 13 sin otro producto, con la llave de `VPS_KEY_NAME` en root y el DNS apuntando a él antes de instalar. El panel va en `panel.<dominio>` | «Health check» y «Ver eventos» |

Una sola vez, en esta máquina: cambiar `OFFLINE_KEY` por una llave guardada fuera (hoy es de prueba) y
empujar canone, porque el CI de cada repo lo compara con esa copia.

`pze` declara «en producción» y usa `backend/`: queda fuera hasta que siga a canone (pregunta 1).

Cada fase actualiza en su commit los documentos del §7 que toca.

## 7. Documentación de Consola afectada

La fase 0 reemplazó los ADR 0001, 0021 y 0022 con el 0059, el 0046 con el 0060 y el 0044 con el
0061. La fase 1 escribió el 0062 («Vaciar VPS» sale) y el 0063 (pregunta 7), y reemplazó el 0017
con el 0064 y los 0019, 0020 y 0040 con el 0065. Lo que sigue falta.

| Qué | Cambio |
|---|---|
| ADR nuevo | La regla de la pregunta 14, con su alcance |
| ADR-0013, 0016 | Reemplazar en lo del VPS: ahí no se migra por túnel |
| ADR-0023 | Reemplazar: los servicios los fija canone |
| ADR-0024 | Reemplazar: el manifiesto de release sale |
| Arquitectura | Se reescriben 15 y 17; cambian 03 §5, 13 §9, 16, 20 y 30 |
| [`rol_de_respaldo.md`](rol_de_respaldo.md) | El punto 8 del ADR-0078 lo deja sin objeto: Equipaggio ya no respalda las bases |

## 8. Preguntas abiertas

| # | Pregunta | Qué se sabe |
|---|---|---|
| 1 | ~~¿Corte limpio o conviven los dos mecanismos?~~ | Resuelta el 2026-10-25: corte limpio. `pze` declara «en producción» y usa `backend/`, no `server/`: queda sin botones de despliegue hasta que siga a canone |
| 2 | ~~¿Dónde guarda Consola lo que cambia entre despliegues?~~ | Resuelta el 2026-10-30: se queda en `.consola/config.env`. Es decisión de Consola desde que el ADR-0107 reemplazó el punto 2 del 0076, que la fijaba ahí. Consola la ignora con `.consola/.gitignore` con `*` (§3, «Fuera de los botones»), porque `plantilla/.gitignore` de canone ya no la ignora |
| 3 | ~~¿Quién crea la base y los dos roles?~~ | Resuelta en canone: `install.py` (ADR-0083 y 0085) |
| 4 | ~~¿Desaparece la subida del APK al VPS?~~ | Resuelta el 2026-10-30: sí. El APK va por tienda o a mano. Servirlo desde el VPS tocaría el Caddy que instala `install.py`, que el ADR-0107 no permite; si hace falta, primero una plantilla en canone. El único que lee `releases/<app>/<plataforma>.json` es `pze/terminal`, ya fuera (pregunta 1) |
| 5 | ~~¿Siguen `backup_db` y `restore_db` por túnel?~~ | Resuelta el 2026-10-30: en el VPS, `backup_db` sale (lo reemplaza **Pedir respaldo**, con esta máquina como receptora) y `restore_db` espera el programa de canone (§5); en local siguen igual. Los roles de canone no tienen contraseña y entran por `peer`, así que un túnel al 5432 no tendría con qué autenticarse *(sin confirmar)* |
| 6 | ~~¿De dónde sale el certificado TLS de coturn?~~ | Resuelta en canone: coturn va sin TLS (ADR-0096) |
| 7 | ~~¿Cómo separa Consola las líneas de `config.env`: credenciales para `credentials.py`, flags de `install.py` y los dos nombres fijos (`restic_password`, `github_token`)?~~ | Resuelta el 2026-10-30: por fuente. Los campos de `Settings` se leen con `ast` del `config.py` del repo, que es quien los declara; `RESTIC_PASSWORD` y `GITHUB_TOKEN` tienen nombre fijo; los flags y las claves propias salen del registro de `core/settings.py`. Una clave que no cae en ninguno, o un campo sin valor, falla antes de enviar nada. canone solo fija lo que recibe cada programa: los nombres y carpetas los fija `credentials.py` (ADR-0105), que no los valida contra `Settings`. Lleva un ADR de Consola (§7) |
| 8 | ~~¿De dónde salen los valores de desarrollo de `credentials/`?~~ | Resuelta el 2026-10-31: de `config.env`, los mismos de producción, salvo `database_url`, que en desarrollo es `DATABASE_URL` de `config.env` con el PostgreSQL local (en producción la escribe `install.py`). El launcher `backend` escribe `server/credentials/` y arranca con `CREDENTIALS_DIRECTORY` apuntando ahí; `sync_server_env` sale. Con las mismas llaves, un token que firma el servidor local, como uno de `jwt_key` o `probe_token_key`, también vale en producción, y se acepta así. `plantilla/.gitignore` de canone ignora `credentials/` |
| 9 | ~~¿Cuál es la receptora: esta máquina o Equipaggio?~~ | Resuelta el 2026-10-30: esta máquina, y el respaldo se pide a mano con **Pedir respaldo**, sin tarea programada. Equipaggio no puede serlo: el ADR-0078 de canone lo descarta, y el monitor solo vigila `lastBackupAt` (ADR-0024 de Equipaggio). Se respalda solo cuando se pide; el aviso de más de 48 h llega cuando Equipaggio esté desplegado, y hoy no lo está. Respaldos y `restic_password` quedan en el mismo disco que `config.env`: perder la máquina pierde las dos cosas, así que la copia de la contraseña va fuera de ella (ADR-0074 de canone). `backup.ps1` pide `rest-server` y `ssh` en el PATH |
| 10 | ~~¿Quién genera `health_token` y cómo lo recibe el monitor de Equipaggio?~~ | Resuelta el 2026-10-30: lo genera el monitor (`POST /probes/{id}/token` de Equipaggio, que lo muestra una vez). Va como `HEALTH_TOKEN` en la configuración y se carga con **Cargar credenciales** |
| 11 | ~~¿Con qué llave se firma: `VPS_KEY_NAME` u otra? ¿Cuál es la segunda, guardada fuera de esta máquina?~~ | Resuelta el 2026-10-30: se firma con `VPS_KEY_NAME`; `-n deploy` separa los usos. La segunda es una sola llave guardada fuera (por ejemplo `ed25519-sk` en una llave física), que es la segunda `--key` y la segunda `--signer`; Consola guarda solo su pública |
| 12 | ~~¿Cómo corre Consola `install.py` la primera vez? ¿Qué cuenta y qué llaves? ¿De dónde salen `--owner` y `--desktop`? ¿Reemplaza a `setup_ssh_key.py`?~~ | Resuelta el 2026-10-30. `VPS_USER` sin valor por defecto. Root entra con `VPS_KEY_NAME`, puesta al crear el VPS. La contraseña de la cuenta va en `SUDO_PASSWORD` y, vacía, Consola la pide una vez por sesión y la tiene solo en memoria; se escribe en el `ssh -tt` cuando aparece la petición. `setup_ssh_key.py` se borra. `--owner` sale de `git remote get-url origin` y `--desktop` del `release.yml` (§4). Con la contraseña guardada en claro, quien se lleve esta máquina tiene la llave y la contraseña |
| 13 | ~~¿Algún VPS envía su journal a Equipaggio? ¿De dónde salen `--logs`, `--logs-key` y `--logs-ip`?~~ | Resuelta el 2026-10-30: hoy ninguno, porque Equipaggio no está desplegado. Cuando lo esté, `LOGS` y `LOGS_KEY` en la configuración global de Consola y `LOGS_IP` por repo, desde el panel. Consola muestra la llave que imprime `install.py` para pegarla en el panel. Agregar `--logs` después no falla; quitarlo sí (ADR-0100) |
| 14 | ~~¿Adopta Consola como regla propia que lo que no tiene plantilla se agrega primero a canone?~~ | Resuelta el 2026-10-30: sí, con el alcance del §5. Lleva un ADR de Consola (§7) |
| 15 | ~~¿Qué pasa con el ámbito remoto de los botones de base que lo conservan?~~ | Resuelta el 2026-10-31: se quedan, porque siguen haciendo falta, y su solución se busca primero en canone (§5). Hasta entonces quedan como están: contra un VPS de canone no se autentican *(sin confirmar)* |
| 16 | ~~¿Se borran de `scripts/` los scripts del despliegue propio?~~ | Resuelta el 2026-10-31: `scripts/` entera es código viejo, y se borra cuando el despliegue con canone funcione. Hasta entonces no se toca |
| 17 | ¿Sale `BUILD_OUT_WEB`, como dice el §4? | Pendiente, y secundaria. «Compilar app Flutter» en web sirve: la clave se queda hasta decidir cómo se sigue |
