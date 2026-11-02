# ADR-0068 · El eje de servicios sale de las unidades de canone, y operarlas pide la contraseña de `sudo`

- **Estado:** Propuesta
- **Fecha:** 2026-11-02
- **Alcance:** core/vps.py, core/settings.py, core/catalog.py, core/tasks/vps_server.py, core/tasks/vps_ops.py, core/process.py, core/ssh.py

## Contexto

El [ADR-0041](0041-un-repo-declara-sus-servicios.md) hacía que cada repo declarara sus servicios en `SERVICES`, porque Consola escribía sus unidades. Desde el [ADR-0059](0059-desplegar-con-los-programas-de-canone.md) las unidades las instala `install.py` de canone, con nombres fijos, y `SERVICES` no describe nada de lo que hay en el VPS.

Probado el 2026-11-02 contra un VPS de canone: «Control del servicio» y «Ver logs del servicio» fallaban con `sudo: a password is required`, porque usaban `sudo -n` y el ADR-0084 de canone exige contraseña. «Health check» decía «errores: (sin datos)» por el mismo fallo. El eje solo ofrecía el servidor, coturn y Caddy.

## Decisión

1. **El eje `service` lista las unidades de canone:** `server` (`<app>`), `valkey` (`valkey-server@<app>`), `sweep`, `purge`, `dump`, `backup` (`<app>-<valor>`), `caddy` y `coturn`. Sigue preguntándole al VPS cuáles existen.
2. **`<app>` sale de `git remote get-url origin`**, como en los argumentos de `install.py`.
3. **`SERVICES` y `UVICORN_APP` salen.** Ninguna otra pieza las leía.
4. **«Control del servicio», «Ver logs del servicio» y los errores de «Health check» van por `vps_setup.Access`**, con `sudo -S` y la contraseña por stdin, igual que `install.py` y `deploy.py`.
5. **«Health check» pide `GET /api/health` en el 8000 y falla si no responde 204**, después de mostrar el resumen y los errores.
6. **«Ver eventos» pide `GET /api/health/events` con `HEALTH_TOKEN` y solo muestra la respuesta.** Avisar lo decide quien consulta (ADR-0080 de canone).
7. **Esas dos consultas van por SSH, con el Python del VPS, a `127.0.0.1:8000`.** `install.py` asegura `python3` y no `curl`, y así funcionan aunque el repo no tenga landing o el DNS no apunte al VPS. El token va por stdin.

## Consecuencias

- Un `config.env` con `SERVICES` o `UVICORN_APP` hace cortar «Cargar credenciales» hasta borrarlas, como cualquier clave sin fuente ([ADR-0063](0063-las-lineas-de-config-env-se-clasifican-por-fuente.md)).
- El ámbito remoto de los botones de base todavía usa `sudo -n`: espera a su solución en canone (pregunta 15 del plan).
- Un VPS con el despliegue propio deja de poder operarse desde estos botones, por el corte limpio ya decidido.

## Descartado

- **Conservar `SERVICES` para los repos con varios procesos.** Si canone agrega unidades (P3 del plan de `equipaggio`), se agregan a este eje: el repo no las declara.
- **Consultar la salud por HTTPS desde esta máquina.** Exige DNS y un host con `/api/*`, y mezcla la salud del servidor con la de Caddy.
- **Dejar `sudo -n` y pedir `sudo` sin contraseña.** El ADR-0084 de canone lo prohíbe.
