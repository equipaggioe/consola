# ADR-0016 · A la base del VPS se llega siempre por un túnel SSH, nunca por su IP pública

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/database.py, core/ssh.py

## Contexto

Conectarse a la base remota por su dirección pública exige abrir el puerto de Postgres en el firewall y confiar en TLS y en la contraseña del rol. El acceso al VPS ya está resuelto y autenticado por llave.

## Decisión

1. Con ámbito remoto, `database.connect` pregunta el puerto real de Postgres al propio VPS, elige un puerto local libre y abre `ssh -N -L`. La URL apunta siempre a `127.0.0.1`.
2. El túnel vive lo que vive la tarea: lo anota `ctx.hold_tunnel`, lo cierra `Connection.close`, y «Limpiar» detiene la tarea si tiene uno vivo.
3. Cuando el proceso corre **del otro lado**, el túnel sobra: `database.vps_url` arma la URL como la ve el VPS.
4. El puerto local no se asume igual al remoto: `ports.resolve_port` busca el siguiente libre. En Windows se comprueba en `0.0.0.0` y en `127.0.0.1`, porque el sistema deja escuchar en una un puerto que otro ya tiene en la otra.
5. `ExitOnForwardFailure=yes`: sin él, un puerto ocupado deja a `ssh` vivo sin reenviar nada y la conexión cae en lo que ya escuchaba ahí.

## Consecuencias

- El puerto de Postgres del VPS no necesita estar abierto.
- Cada conexión remota cuesta abrir y cerrar un proceso `ssh`, y `bind_to_app` lo ata a la aplicación para que no sobreviva.
- El puerto local de Postgres se lee de `postgresql.conf`, porque una instalación con varias versiones no siempre deja la buena en 5432.

## Descartado

- **Conectar a la IP pública.** Obliga a abrir el puerto y a confiar en la contraseña del rol como única defensa.
