# Plan — desplegar con el mecanismo de canone

> **Estado (verificado 2026-10-24).** No hay nada construido. Consola sigue desplegando con su
> mecanismo propio: clona el repo en el VPS, escribe las unidades, el Caddyfile y el `.env`, y
> migra por túnel.
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
> (§6).
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

| # | Conflicto | Evidencia |
|---|---|---|
| C1 | `configure_caddy` sobrescribe el `/etc/caddy/Caddyfile` de `install.py`: se pierden el snippet `surface` y el `import sites/*.caddy`, y Caddy deja de servir los sitios | `vps_setup.py::CADDYFILE` y `install.py::TARGETS` |
| C2 | `configure_service` escribe `/etc/systemd/system/<repo>.service` sin sandboxing encima de la unidad de canone, que se llama igual | `vps.unit_path` y `PRODUCTO.service` |
| C3 | `clean_vps` borra con `remove_systemd_service` las unidades de canone | `vps_ops.py::remove_systemd_service` |
| C6 | `setup_ssh_key.py` crea `VPS_USER` (por defecto el nombre del repo, que es `<app>`) con `sudo NOPASSWD`. El ADR-0087 prohíbe que la cuenta que administra sea `<app>`, y el 0084 pide `sudo` con contraseña. Tras `install.py`, root ya no entra y `setup_ssh_key.py` deja de servir | `setup_ssh_key.py`, `core/vps.py` |
| C5 | El launcher `backend` pasa la base en la variable `DATABASE_URL`. `Settings` de canone lee solo `CREDENTIALS_DIRECTORY`, así que en un repo de canone el valor se ignora | `launchers.py::serve_backend`, «Configuración» de `fastapi.md` |

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
| **Vaciar VPS** (`clean_vps`) | Se queda, cuando canone traiga el programa que desinstala (§5) | Borra unidades de canone, `/srv/<app>`, `/var/lib/<app>*`, credstore, sitios de Caddy, Valkey, `sshd_config.d`, la base y sus roles, y los usuarios `<app>`, `<app>_owner` y `<app>-receiver`. Queda en pie `00-<app>.conf` y la cuenta que administra, o la máquina queda sin entrada (sin confirmar) |
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
| `.consola/` | Consola escribe `.consola/.gitignore` con `*` al crear la carpeta, en vez de agregar `.consola/` al `.gitignore` del repo (`envfile.py::ensure_gitignored`), y falla si no puede escribirlo |

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
desplegar.

El repo piloto es `equipaggio`. Ningún repo con `server/` puede publicar hoy una versión
(verificado el 2026-10-31): ninguno tiene `release.yml`, solo banditore, comande y concordia tienen
`ci.yml`, siete siguen con `requirements.txt` en vez de uv, ninguno compila catálogos con `babel`,
y casi ninguno tiene `pnpm-lock.yaml` en cada pieza web. La plantilla de `release.yml` construye
una sola pieza web (`PIEZA`), y `equipaggio` tiene `panel/` y `landing/`. El piloto se lleva a la
plantilla de canone, con su `ci.yml` y su `release.yml`, antes de cerrar la fase 3; los demás
repos lo siguen después.

Cada fase actualiza en su commit los documentos del §7 que toca.

## 7. Documentación de Consola afectada

| Qué | Cambio |
|---|---|
| ADR-0001 | Reemplazar: Consola ejecuta `install.py`, `uv.py`, `deploy.py`, `credentials.py` y el script de la receptora, que no reimplementa |
| ADR nuevo | La regla de la pregunta 14, con su alcance |
| ADR nuevo | Las líneas de `config.env` se clasifican por fuente (pregunta 7) |
| ADR-0017 | Reemplazar el punto 5: `.consola/.gitignore` en vez del `.gitignore` del repo |
| ADR-0013, 0016 | Reemplazar en lo del VPS: ahí no se migra por túnel |
| ADR-0019, 0020, 0040 | Reemplazar: la tabla de rutas sale |
| ADR-0021 | Reemplazar: Consola deja de escribir en `/etc` sus propios archivos |
| ADR-0023, 0041 | Reemplazar: los servicios los fija canone |
| ADR-0024 | Reemplazar: el manifiesto de release sale |
| ADR-0037 | Reemplazar: `sync_server_env` sale, y desarrollo usa los valores de `config.env` salvo `database_url` (pregunta 8) |
| ADR-0044 | El eje `side` pierde `vps` |
| ADR-0045, 0046, 0047 | Reemplazar en lo del VPS: `backup_db` sale y `restore_db` espera el programa de canone (pregunta 5) |
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
