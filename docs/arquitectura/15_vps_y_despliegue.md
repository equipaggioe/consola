# 15 · VPS y despliegue

## 1. Cómo se llega

`core/ssh.py::resolve_remote(config)` arma un `Remote` (host, usuario, llave) desde `VPS_IP`, `VPS_USER` y `VPS_KEY_NAME`. Los pasos de aprovisionamiento que todavía no tienen usuario de despliegue pasan `ROOT_USER` explícitamente.

| Detalle | Por qué |
|---|---|
| `-n` salvo que se pida TTY | Estos comandos no leen teclado; sin cerrar el stdin, `ssh` lo reenvía y el comando remoto puede esperar un EOF que nunca llega |
| `ConnectTimeout=15` y `BatchMode` en las consultas | Una consulta corta no debe colgar la interfaz |
| Multiplexado (`ControlMaster`) en POSIX | Cinco `scp` seguidos abren una sola conexión TCP. **Desactivado en Windows**: el ControlMaster de Win32-OpenSSH emula sockets Unix con pipes y falla al reusarlos |
| `ExitOnForwardFailure` en los túneles | Sin él, un puerto local ocupado deja a `ssh` vivo sin reenviar nada y la conexión cae en lo que ya escuchaba ahí |
| `scp -r` al **padre** del destino | `scp -r origen destino` copia dentro del destino cuando este ya existe: apuntar a la ruta final deja `.../dist/dist` a partir de la segunda vez |

### Contraseña sin consola

La interfaz lanza todo con stdin cerrado y sin ventana, y `ssh` pide la contraseña a la consola, no a stdin: dentro de la aplicación no hay dónde escribirla. `password_env` usa `SSH_ASKPASS_REQUIRE=force` (OpenSSH 8.4+) con un helper que solo reimprime lo que le llega por el entorno — un `.bat` con expansión retardada en Windows, un `.sh` en POSIX. La contraseña no toca el disco ni la línea de comandos.

Es el único momento en que Consola se conecta con contraseña: al dar de alta la cuenta de despliegue. Se pide en el momento, `ask_once` la recuerda durante la corrida y nunca se guarda. Y es el último recurso, no el primero: `ssh` prueba las llaves antes.

## 2. El despliegue

Consola no despliega ningún repo. El despliegue lo hacen los programas de canone, y Consola todavía no los corre ([ADR-0059](../adr/0059-desplegar-con-los-programas-de-canone.md)). No clona el repo en el VPS ni escribe ahí configuración de servicios: ni unidades systemd, ni `tmpfiles.d`, ni `turnserver.conf`, ni Caddyfile ([30](30_riesgos_y_pendientes.md)).

Este documento describe los botones que siguen alcanzando el VPS.

## 3. Rutas del repo desplegado

| Función | Qué da |
|---|---|
| `vps.repo_name(config)` | El nombre del repo, derivado de `GIT_REPO_URL`. La carpeta local puede no coincidir, y por eso no se usa como default silencioso |
| `vps.deploy_root` | `<VPS_DEPLOY_DIR>/<repo>` |
| `vps.remote_path(config, *partes)` | La misma jerarquía relativa que en el repo local |
| `vps.remote_python` | El intérprete del venv del servidor, dentro del repo desplegado |

Las leen el ámbito remoto de la base ([16](16_base_de_datos.md)) y la subida de «Compilar ejecutable» ([17](17_builds_y_artefactos.md)).

## 4. Paquetes

`vps.PACKAGE_GROUPS` agrupa por lo que significan para quien elige, no por cómo se llaman en apt (`python` son tres paquetes): `python`, `git`, `postgresql`, `postgis`, `caddy`, `ufw`, `redis`, `coturn`. Arrancan marcados los cinco de `DEFAULT_GROUPS`.

Instalar saltea lo que ya está (`dpkg -s`) y no configura nada: el paquete queda instalado con la configuración que trae.

## 5. Los servicios del VPS

`systemd_action` y `view_logs` operan las unidades systemd **del repo** más `coturn` y `caddy`. Todas se reinician, se paran y se leen igual, así que `service` es **un eje**, no un botón por servicio ([ADR-0023](../adr/0023-los-servicios-son-un-eje.md)).

Cuántas son las del repo lo dice el repo: `SERVICES` es una tabla de filas `<sufijo> <tipo> <destino>` y cada fila es una unidad ([ADR-0041](../adr/0041-un-repo-declara-sus-servicios.md)). Sin tabla hay una sola, llamada como el repo, que es el valor `proyecto` del eje.

`vps.managed_services` arma los valores del eje —los del repo y después los dos paquetes— y `vps.resolve_service` los traduce al nombre real de la unidad: `<repo>` sin tabla, `<repo>-<sufijo>` con ella. Los valores que se ofrecen no se enumeran: `vps.installed_services` pregunta cuáles existen en **este** VPS, en una sola consulta, y el resultado se cachea por host. Si no se puede preguntar los devuelve todos, para no dejar el botón sin nada que ofrecer.

`vps.unit_installed` pregunta con `systemctl cat`, que encuentra la unidad esté donde esté su archivo: las de un paquete apt viven en `/lib/systemd/system`.

## 6. Deshacer

No hay un botón que vacíe el VPS: desarmar uno es reinstalarlo desde el panel del proveedor ([ADR-0062](../adr/0062-vaciar-vps-sale.md)).

`revoke_ssh` muestra la huella exacta que va a sacar antes de tocar nada: revocar la llave equivocada deja el servidor inalcanzable. Sus dos lados son desmarcables por separado.

## 7. Diagnóstico

`health` pregunta primero si se llega por SSH y **corta ahí** si no. Las otras cuatro consultas usan `check=False`, así que con el SSH caído devolvían vacío y el estado del servicio caía en `missing`: el resumen anunciaba un servidor destruido cuando la verdad era que no se llegaba a la máquina.

`view_logs` arma un `journalctl` con filtros. Es capacidad hermana de `systemd_action` y no un valor suyo: los filtros no tienen sentido para start/stop. Hoy el panel no ofrece esos filtros ([30](30_riesgos_y_pendientes.md)).
