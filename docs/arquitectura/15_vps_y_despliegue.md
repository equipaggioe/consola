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

**Regla:** lo que deja un cambio permanente en un VPS lo hace un programa de canone. Si canone no lo trae, se agrega primero a canone. No alcanza a lo que corre en esta máquina (compilar, crear el tag, firmar), a correr lo que canone ya instaló (`deploy.py`, `credentials.py`, `systemctl`, los registros, la salud), ni a lo que canone deja a quien prepara la máquina (sus paquetes, el swap). Hoy la incumplen «Quitar acceso SSH» y el ámbito remoto de los botones de base (30).

Este documento describe los botones que siguen alcanzando el VPS.

## 3. Rutas del repo desplegado

| Función | Qué da |
|---|---|
| `vps.repo_name(config)` | El nombre del repo, derivado de `GIT_REPO_URL`. La carpeta local puede no coincidir, y por eso no se usa como default silencioso |
| `vps.deploy_root` | `<VPS_DEPLOY_DIR>/<repo>` |
| `vps.remote_path(config, *partes)` | La misma jerarquía relativa que en el repo local |

Las lee la subida de «Compilar ejecutable» ([17](17_builds_y_artefactos.md)).

## 4. Configurar VPS

«Configurar VPS» (`bootstrap_vps`) encadena cinco pasos, que se pueden volver a correr porque cada uno detecta lo que ya está ([ADR-0066](../adr/0066-configurar-vps-prepara-la-maquina-y-corre-install-py.md)):

| Paso | Qué hace |
|---|---|
| Paquetes y uv (`install_software`) | `apt-get install` de `canone.packages`: los de la máquina de canone, más PostGIS si `DB_EXTENSIONS` la nombra, coturn con `TURN` y lo del journal con `LOGS`. Después corre `uv.py` |
| Swap (`create_swap`) | Si el swap no llega a la memoria, crea `/swapfile` con lo que falta y lo agrega a `/etc/fstab`. Sin eso, `install.py` falla |
| Infraestructura (`install_infra`) | Corre `install.py` con `canone.install_args`, con `--development` si el `README.md` dice `Estado: en desarrollo` ([16](16_base_de_datos.md) §6). La primera vez, como root por `ssh -tt`, y escribe la contraseña de la cuenta recién cuando aparece cada pregunta (`process.converse`); después, con `sudo` |
| Credenciales (`load_credentials`) | Pasa a `credentials.py`, por stdin, una línea `campo=valor` por credencial (`canone.credential_lines`, [13](13_configuracion_y_persistencia.md) §2). Corta antes de enviar si falta un valor o si `config.env` tiene una clave sin fuente |
| Último release (`vps_release.deploy_latest`) | Despliega el release que GitHub da como `latest`, si tiene su firma. Si `/srv/<app>/current` ya es ese release, no hace nada ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)) |

El DNS tiene que apuntar al VPS antes de correrla. Si no, Caddy se queda sin certificado y sus reintentos se espacian: el 2026-11-02 esperaba 20 minutos, y hubo que reiniciarlo para que lo pidiera al crear los registros. Let's Encrypt es el único emisor que responde: el Caddy 2.6.2 de Debian prueba ZeroSSL después, y ZeroSSL lo rechaza con `caddy_legacy_user_removed`.

Los programas salen de `plantilla/infra/` de la copia local de canone (`CANONE_DIR`), que se sube a `/tmp/consola-canone` y se borra al terminar. `<app>` y `--owner` salen de `git remote get-url origin`.

## 4b. Versiones

Un tag `vX.Y.Z` hace que el `release.yml` del repo publique el artefacto y su `.sha256`; Consola firma el `.sha256` y el VPS lo instala con `deploy.py`, que `install.py` dejó en `/usr/local/lib/<app>/` ([ADR-0067](../adr/0067-publicar-version-sube-el-ultimo-tag-de-origin.md)). Lo de GitHub va por `gh`, con `--repo <dueño>/<app>` de `git remote get-url origin`.

«Publicar versión» (`publish_release`):

| Paso | Qué hace |
|---|---|
| Crear tag (`create_tag`) | Corta si hay cambios sin commitear o commits que origin no tiene. Sube el tag `v*` más alto de origin según el eje `part` (`canone.next_tag`), crea el tag anotado y lo empuja. Busca la corrida de `release.yml` del tag y pregunta su estado con `gh run view` cada 15 s; si no termina bien, muestra `--log-failed` y corta |
| Firmar release (`sign_release`) | Baja `<app>-<tag>.sha256`, lo firma con `ssh-keygen -Y sign -n deploy` y `VPS_KEY_NAME`, y sube la `.sig`. Si ya está, no firma |
| Desplegar (`deploy_release`) | `sudo python3 /usr/local/lib/<app>/deploy.py <tag>` desde la cuenta que administra (`canone.deploy_command`) |

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

`<app>` sale de `git remote get-url origin`, y `vps.resolve_service` traduce el valor a la unidad. Los valores que se ofrecen no se enumeran: `vps.installed_services` pregunta cuáles existen en **este** VPS, en una sola consulta, y el resultado se cachea por host. Si no se puede preguntar, el panel muestra el motivo en lugar del eje y el botón queda bloqueado ([ADR-0076](../adr/0076-un-fallo-al-consultar-o-al-guardar-en-cache-se-dice.md)).

`vps.unit_installed` pregunta con `systemctl cat`, que encuentra la unidad esté donde esté su archivo: las de un paquete apt viven en `/lib/systemd/system`.

`start` y `restart` sobre `backup` cortan: el respaldo lo pide la receptora ([ADR-0073](../adr/0073-el-respaldo-no-se-arranca-desde-control-del-servicio.md)).

Actuar sobre una unidad y leer su journal piden root: van por `vps_setup.Access`, con `sudo -S` y la contraseña por stdin (§1).

## 6. Deshacer

No hay un botón que vacíe el VPS: desarmar uno es reinstalarlo desde el panel del proveedor ([ADR-0062](../adr/0062-vaciar-vps-sale.md)).

`revoke_ssh` muestra la huella exacta que va a sacar antes de tocar nada: revocar la llave equivocada deja el servidor inalcanzable. Sus dos lados son desmarcables por separado. Si no se puede sacar la llave del VPS —no entra, la línea no está o es la última—, corta y deja el par local.

## 7. Diagnóstico

«Health check» (`health_check`) entra con `vps_setup.access`, que corta si no se llega por SSH. Muestra el estado de `<app>`, `GET /api/health`, el uptime, la carga, el disco y la memoria, y después los últimos errores del journal. Falla al final si la API no responde 204, para que el resumen y los errores queden a la vista.

«Ver eventos» (`view_events`) pide `GET /api/health/events` con `HEALTH_TOKEN` y muestra el último evento, el último crítico, el último respaldo y el disco. Corta si no responde 200. No decide cuándo avisar.

Las dos consultas van por SSH a `127.0.0.1:8000`, con `python3`, que `install.py` asegura (`vps.server_get`). El token va por stdin.

`view_logs` arma un `journalctl` con filtros. Es capacidad hermana de `systemd_action` y no un valor suyo: los filtros no tienen sentido para start/stop. Hoy el panel no ofrece esos filtros ([30](30_riesgos_y_pendientes.md)).
