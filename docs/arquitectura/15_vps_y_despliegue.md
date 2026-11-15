# 15 · VPS y despliegue

## 1. Cómo se llega

`core/ssh.py::resolve_remote(config)` arma un `Remote` (host, usuario, llave) desde `VPS_IP`, `VPS_USER` y `VPS_KEY_NAME`.

| Detalle | Por qué |
|---|---|
| `-n` salvo que se pida TTY | Estos comandos no leen teclado; sin cerrar el stdin, `ssh` lo reenvía y el comando remoto puede esperar un EOF que nunca llega |
| `ConnectTimeout=15` y `BatchMode` en las consultas | Una consulta corta no debe colgar la interfaz |
| `StrictHostKeyChecking=accept-new` | La primera conexión a un VPS anota su huella: con `BatchMode`, sin esto, un VPS nuevo o recién olvidado da «No se entra». Una huella que cambió sigue cortando |
| Multiplexado (`ControlMaster`) en POSIX | Cinco `scp` seguidos abren una sola conexión TCP. **Desactivado en Windows**: el ControlMaster de Win32-OpenSSH emula sockets Unix con pipes y falla al reusarlos |
| `ExitOnForwardFailure` en los túneles | Sin él, un puerto local ocupado deja a `ssh` vivo sin reenviar nada y la conexión cae en lo que ya escuchaba ahí |
| `scp -r` al **padre** del destino | `scp -r origen destino` copia dentro del destino cuando este ya existe: apuntar a la ruta final deja `.../dist/dist` a partir de la segunda vez |

### Root, la cuenta y `sudo`

`vps_setup.access` entra por la cuenta de `VPS_USER` si la llave ya la deja entrar, y si no, por root con la misma llave: root entra solo hasta que `install.py` lo deja afuera ([ADR-0066](../adr/0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md)). Con la cuenta, lo que pide root va por `sudo -S`, con la contraseña por stdin (`ssh.run(..., stdin_text=...)`): sale de `SUDO_PASSWORD` o se pide una vez por sesión y queda en memoria (`core/session.py`).

Lo que va por stdin no pasa por el log. Un comando que lee stdin se lanza sin `-n`; los demás lo llevan, porque `ssh` reenviaría el stdin y el comando remoto podría esperar un EOF que no llega.

## 2. El despliegue

El despliegue lo hacen los programas de canone ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)). Consola prepara la máquina y corre `install.py` y `credentials.py` (§4), y publica, firma y despliega versiones (§4b). No clona el repo en el VPS ni escribe configuración de servicios: eso lo instala `install.py`.

**Regla:** lo que deja un cambio permanente en un VPS lo hace un programa de canone. Si canone no lo trae, se agrega primero a canone. No alcanza a lo que corre en esta máquina (compilar, crear el tag, firmar), a correr lo que canone ya instaló (`deploy.py`, `credentials.py`, `systemctl`, los registros, la salud). Hoy la incumplen «Quitar acceso SSH» y el ámbito remoto de los botones de base (30).

Este documento describe los botones que siguen alcanzando el VPS.

## 3. Rutas del repo desplegado

| Función | Qué da |
|---|---|
| `vps.repo_name(config)` | El nombre del repo, derivado de `GIT_REPO_URL`. La carpeta local puede no coincidir, y por eso no se usa como default silencioso |
| `vps.deploy_root` | `<VPS_DEPLOY_DIR>/<repo>` |
| `vps.remote_path(config, *partes)` | La misma jerarquía relativa que en el repo local |

Las lee la subida de «Compilar ejecutable» ([17](17_builds_y_artefactos.md)).

## 4. Configurar VPS

«Configurar VPS» (`bootstrap_vps`) encadena seis pasos, que se pueden volver a correr porque cada uno detecta lo que ya está ([ADR-0066](../adr/0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md)):

| Paso | Qué hace |
|---|---|
| Poner la llave (`install_key`) | Crea la llave `VPS_KEY_NAME` en `~/.ssh` si falta. Si no entra ni como la cuenta ni como root, entra una vez como root con su contraseña, la del proveedor, de `ROOT_PASSWORD` o pedida: sube `authorize.py` de canone y lo corre con la llave, que queda en el `authorized_keys` de root ([ADR-0084](../adr/0084-configurar-vps-pone-la-llave-con-la-contrasena-de-root.md)). `scp` y `ssh` leen una contraseña solo de una terminal, así que la toman de `SSH_ASKPASS`: un script de `HOST.askpass` que la imprime desde el entorno, sin que pase por un argumento, un archivo ni el log |
| Paquetes y uv (`install_software`) | Corre `packages.py` de canone, que tiene la lista («Máquina» de [`despliegue.md` de canone](https://github.com/equipaggioe/canone/blob/main/plataformas/despliegue.md#máquina)), con las opciones de `install.py` que agregan un paquete: `--extension` por cada una de `DB_EXTENSIONS`, `--turn` si `Settings` declara `turn_secret` (`canone.calls`, [ADR-0085](../adr/0085-turn-sale-de-turn-secret.md)) `--logs` con `LOGS`, y `--java` por cada pieza en Java que el `release.yml` del repo compila con `scripts/java.py` de canone (`canone.package_args`, `canone.java_pieces`). Si la máquina no tiene `python3`, lo instala con apt antes, porque `packages.py` corre con él. Después corre `uv.py` |
| Swap (`create_swap`) | Corre `swap.py` de canone, que crea `/swapfile` con lo que le falta al swap para llegar a la memoria y lo agrega a `/etc/fstab`; con eso, no cambia nada. Sin swap, `install.py` falla |
| Infraestructura (`install_infra`) | Corre `install.py` con `canone.install_args`. La memoria de Valkey es `VALKEY_MEMORY`; vacía, lee `/proc/meminfo` del VPS y toma el `VALKEY_PERCENT` de `MemTotal` (`canone.valkey_memory`, [ADR-0086](../adr/0086-la-memoria-de-valkey-sale-de-un-valor-o-de-un-porcentaje.md)), y lo dice en el log. Cada línea del archivo `permissions` del repo va como `--allow` (ADR-0136 de canone). Cada `desktop-<sistema>` del `release.yml` del repo va como `--desktop`, cada `<pieza>.apk` que sube, como `--mobile`, y cada pieza que compila con `scripts/java.py`, como `--java` (`canone.desktops`, `canone.mobiles`, `canone.java_pieces`). Cada pieza web sin su carpeta en la raíz va como `--without`, y `--without sweep` si el `TASKS` de `<SERVER_DIR>/src/app/tasks.py`, leído con `ast`, no trae `sweep`: el servidor no guarda archivos de usuarios (`canone.without`). Cada tarea del `TIMERS` de ese `tasks.py`, `{tarea: OnCalendar}`, va como `--task <tarea>=<OnCalendar>`, y una que no está en `TASKS` corta (`canone.timers`, ADR-0151 de canone). Sin `tasks.py`, corta. Va con `--development` si el `README.md` dice `Estado: en desarrollo` ([16](16_base_de_datos.md) §6). La primera vez, como root por `ssh -tt`, y escribe la contraseña de la cuenta recién cuando aparece cada pregunta (`process.converse`); después, con `sudo` |
| Credenciales (`load_credentials`) | Pasa a `credentials.py`, por stdin, una línea `campo=valor` por credencial (`canone.credential_lines`, [13](13_configuracion_y_persistencia.md) §2). Corta antes de enviar si falta un valor o si `config.env` tiene una clave sin fuente |
| Último release (`vps_release.deploy_latest`) | Despliega el release que GitHub da como `latest`, si tiene su firma. Si `/srv/<app>/current` ya es ese release, no hace nada ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)) |

Antes de correr, «Instalar paquetes base» y «Configurar VPS» muestran arriba de sus parámetros, como casillas deshabilitadas, todos los paquetes que `packages.py` puede instalar (`--list --all`, `canone.installable`), marcados los que va a instalar con las opciones de `config.env` y del repo (`--list`, `canone.packages`). No se eligen ahí: los deciden `config.env` y el repo. Corre `packages.py` de `CANONE_DIR` con el Python de esta máquina, sobre el `config.env` guardado, y se vuelve a preguntar al guardarlo (`Capability.preview`, `catalog.preview_checks`). Si no se puede preguntar, en su lugar va el motivo.

El DNS tiene que apuntar al VPS antes de correrla: «Actualizar Cloudflare» deja el registro A de cada host de la app —`DOMAIN` con `landing/`, `app.DOMAIN` con `web/` y `panel.DOMAIN` con `panel/` (`canone.hosts`)— en la IP, sin el proxy de Cloudflare, y crea el que falta en la zona `CF_DOMAIN_NAME` ([ADR-0088](../adr/0088-actualizar-cloudflare-apunta-cada-host-de-la-app-sin-proxy.md)). Si no, Caddy se queda sin certificado y sus reintentos se espacian: el 2026-11-02 esperaba 20 minutos, y hubo que reiniciarlo para que lo pidiera al crear los registros. Let's Encrypt es el único emisor que responde: el Caddy 2.6.2 de Debian prueba ZeroSSL después, y ZeroSSL lo rechaza con `caddy_legacy_user_removed`.

Los programas salen de `plantilla/infra/` de la copia local de canone (`CANONE_DIR`), que se sube a `/tmp/consola-canone` y se borra al terminar. `<app>` y `--owner` salen de `git remote get-url origin`.

## 4b. Versiones

Un tag `vX.Y.Z` hace que el `release.yml` del repo publique el artefacto y su `.sha256`; Consola firma el `.sha256` y el VPS lo instala con `deploy.py`, que `install.py` dejó como `/usr/local/sbin/<app>-deploy` ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)). Lo de GitHub va por `gh`, con `--repo <dueño>/<app>` de `git remote get-url origin`.

«Publicar versión» (`publish_release`):

| Paso | Qué hace |
|---|---|
| Crear tag (`create_tag`) | Corta si hay cambios sin commitear o commits que origin no tiene. Sube el tag `v*` más alto de origin según el eje `part` (`canone.next_tag`), crea el tag anotado y lo empuja. Busca la corrida de `release.yml` del tag por la ruta de su workflow, en `GET /repos/{dueño}/{app}/actions/runs` (`vps_release.release_run`): `gh run list --workflow` solo encuentra el archivo en la rama por omisión, y el repo puede traer `release.yml` en la rama que etiqueta. Pregunta su estado con `gh run view` cada 15 s; si no termina bien, muestra `--log-failed` y corta |
| Firmar release (`sign_release`) | Baja `<app>-<tag>.sha256`, lo firma con `ssh-keygen -Y sign -n deploy` y `VPS_KEY_NAME`, y sube la `.sig`. Si ya está, no firma |
| Desplegar (`deploy_release`) | `sudo /usr/local/sbin/<app>-deploy <tag>` desde la cuenta que administra (`canone.deploy_command`) |

Sin «Crear tag», firma y despliega el último release publicado.

«Desplegar versión» (`deploy_version`) corre `deploy_release` con un tag del eje `version`, que lista los releases publicados con su firma (`catalog.RELEASES`, `canone.signed`), sin cache. `deploy.py` no instala una versión que siga en `/srv/<app>/releases/`, donde quedan las cinco más nuevas.

Lo que hace `deploy.py` en cada caso, comprobado el 2026-11-02 con versiones de prueba. En todos los que fallan, el botón termina con error:

| Caso | `current` | Servidor |
|---|---|---|
| Migra y arranca | La nueva | Arriba |
| No migra y no arranca | Vuelve a la anterior | Arriba. La carpeta nueva queda en `releases/` |
| La migración falla | Sigue la anterior, y la carpeta nueva se borra | Arriba, con la base sin cambios |
| Migra y no arranca | Se queda en la nueva | **Caído hasta publicar otra versión.** `systemctl is-active` puede decir `active` mientras reinicia: «Health check» es lo que lo detecta |
| Versión ya podada, con la base más nueva | No cambia, porque la migración falla | Arriba |
| Release sin firma | No cambia | Arriba. «Desplegar versión» no lo lista |

## 5. Los servicios del VPS

`systemd_action` y `view_logs` operan las unidades que instala `install.py`, más Caddy y coturn. Todas se reinician, se paran y se leen igual, así que `service` es **un eje**, no un botón por servicio ([ADR-0077](../adr/0077-el-eje-de-servicios-pregunta-al-vps-que-unidades-existen.md), [ADR-0068](../adr/0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md)).

| Valor del eje | Unidad |
|---|---|
| `server` | `<app>` |
| `valkey` | `valkey-server@<app>` |
| `sweep`, `purge`, `dump`, `backup` | `<app>-<valor>` |
| `caddy`, `coturn` | Con ese nombre |
| `java:<pieza>` | `<app>-java@<pieza>`, por cada instancia que el VPS tiene cargada |

`<app>` sale de `git remote get-url origin`, y `vps.resolve_service` traduce el valor a la unidad. Los valores que se ofrecen no se enumeran: `vps.installed_services` pregunta cuáles existen en **este** VPS, piezas en Java incluidas, en una sola consulta, y el resultado se cachea por host. Si no se puede preguntar, el panel muestra el motivo en lugar del eje y el botón queda bloqueado ([ADR-0076](../adr/0076-un-fallo-al-consultar-o-al-guardar-en-cache-se-dice.md)).

Las piezas en Java no se preguntan una por una: `systemctl cat` responde que existe cualquier instancia de `<app>-java@` en cuanto la plantilla está instalada (comprobado el 2026-11-14 con `presenze-java@noexiste`). Se listan con `systemctl list-units --all '<app>-java@*'`, en la misma consulta, y así el eje ofrece las que `install.py` habilitó, no las que el repo declara.

`vps.unit_installed` pregunta con `systemctl cat`, que encuentra la unidad esté donde esté su archivo: las de un paquete apt viven en `/lib/systemd/system`.

`start` y `restart` sobre `backup` cortan: el respaldo lo pide la receptora ([ADR-0073](../adr/0073-el-respaldo-no-se-arranca-desde-control-del-servicio.md)).

Actuar sobre una unidad y leer su journal piden root: van por `vps_setup.Access`, con `sudo -S` y la contraseña por stdin (§1).

## 6. Deshacer

«Vaciar VPS» (`vps_setup.clean_vps`) sube `plantilla/infra/` de canone y corre `uninstall.py <app> <nivel>` desde la cuenta que administra, con `sudo` ([ADR-0083](../adr/0083-vaciar-vps-corre-uninstall-py-de-canone.md)). Cada nivel incluye al anterior:

| Nivel | Qué borra `uninstall.py` |
|---|---|
| La base (`database`) | Detiene el servidor y sus timers, y borra la base, sus tres roles, sus credenciales, su línea de `pg_hba.conf` y `pg_ident.conf`, los archivos de los usuarios y el dump. «Configurar VPS» los vuelve a crear |
| La app (`app`) | Cada unidad, sitio, credencial, cuenta y carpeta de la app |
| La máquina (`machine`) | El swap, uv, el túnel del journal y los archivos que `install.py` escribe para toda la máquina y ningún paquete trae. Los paquetes quedan, con lo que `install.py` sobrescribió en ellos, como el `Caddyfile`: dejar el VPS como lo entrega el proveedor es reinstalarlo desde su panel, y después «Configurar VPS» |

Ningún nivel toca la cuenta que administra, sus llaves ni `00-<app>.conf`, y root sigue bloqueado: después se vuelve a entrar por la misma cuenta. El simulacro corre `uninstall.py --dry-run`, que lista lo que haría; lo demás pasa por el seguro de los objetivos `vps` y `db` ([14](14_seguro_de_destructivos.md)).

`revoke_ssh` muestra la huella exacta que va a sacar antes de tocar nada: revocar la llave equivocada deja el servidor inalcanzable. Sus dos lados son desmarcables por separado. Si no se puede sacar la llave del VPS —no entra, la línea no está o es la última—, corta y deja el par local.

## 7. Diagnóstico

«Health check» (`health_check`) entra con `vps_setup.access`, que corta si no se llega por SSH. Muestra el estado de `<app>`, `GET /api/health`, el uptime, la carga, el disco y la memoria, y después los últimos errores del journal. Falla al final si la API no responde 204, para que el resumen y los errores queden a la vista.

«Ver eventos» (`view_events`) pide `GET /api/health/events` con `HEALTH_TOKEN` y muestra el último evento, el último crítico, el último respaldo y el disco. Corta si no responde 200. No decide cuándo avisar.

Las dos consultas van por SSH a `127.0.0.1:8000`, con `python3`, que `install.py` asegura (`vps.server_get`). El token va por stdin.

`view_logs` arma un `journalctl` con filtros. Es capacidad hermana de `systemd_action` y no un valor suyo: los filtros no tienen sentido para start/stop. Hoy el panel no ofrece esos filtros ([30](30_riesgos_y_pendientes.md)).
