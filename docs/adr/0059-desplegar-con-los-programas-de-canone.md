# ADR-0059 · Consola despliega con los programas de canone y no reimplementa el despliegue

- **Estado:** Aceptada. El punto 6 lo reemplaza el [ADR-0065](0065-cada-spa-va-en-la-raiz-de-su-host.md), y lo que conservaba `scripts/` en el punto 1, el [ADR-0075](0075-consola-sigue-las-convenciones-de-canone-como-cualquier-repositorio.md)
- **Fecha:** 2026-10-31
- **Alcance:** todo el repositorio

## Contexto

El [ADR-0001](0001-reimplementar-no-ejecutar-scripts.md) decidió reimplementar los scripts de los repos administrados como funciones y permitir `subprocess` solo a un binario externo. Sobre esa regla Consola armó su propio despliegue: clonaba el repo en el VPS, instalaba sus dependencias, copiaba los archivos secretos, escribía en `/etc` la unidad systemd, el `tmpfiles.d`, `turnserver.conf` y el Caddyfile ([ADR-0021](0021-configuracion-en-etc-no-en-el-repo.md)), con un botón para instalar cada paquete y otro para configurarlo ([ADR-0022](0022-instalar-y-configurar-son-dos-botones.md)), y migraba la base por túnel.

canone fija ahora cómo queda un VPS y lo entrega como programas: `install.py`, `uv.py`, `credentials.py`, `deploy.py` y los scripts de la receptora. Quien despliega los corre y no escribe encima de lo que instalan (ADR-0075 y ADR-0107 de canone). Sobre un VPS instalado así, el despliegue propio rompe lo que encuentra: «Configurar Caddy» pisaba el Caddyfile de `install.py`, «Crear servicio systemd» escribía `<app>.service` encima de la unidad de canone, que se llama igual, y «Vaciar VPS» la borraba.

Este ADR reemplaza a los tres: conserva de cada uno lo que sigue vigente.

## Decisión

1. **Los scripts de los repos administrados se siguen reimplementando como funciones** sobre `core/`, y `scripts/` se conserva como especificación de comportamiento. Nada del código lo importa (del ADR-0001).
2. **Una capacidad que necesita lo que hace otra la llama como función**, con un contexto hijo, no como proceso (del ADR-0001).
3. **El único `subprocess` permitido es a un binario externo real** (`git`, `ssh`, `scp`, `flutter`, `npm`, `psql`, `pg_dump`…) **o a un programa de canone.**
4. **En el VPS, Consola corre los programas de canone** —`install.py`, `uv.py`, `credentials.py` y `deploy.py`— y no los reimplementa. No escribe encima de lo que instalan: ni unidades systemd, ni configuración en `/etc`, ni un clon del repo.
5. **Corte limpio.** Los botones del despliegue propio salen sin convivir con los nuevos, y su código queda en el tag anotado `despliegue-propio`. Salen «Desplegar» (`publish_code`), «Actualizar despliegue» (`update_remote`), «Publicar en producción» (`promote_app`), «Copiar archivos secretos» (`upload_secret_files`), «Crear servicio systemd» (`configure_service`), «Configurar Caddy» (`configure_caddy`), «Configurar Coturn» (`configure_coturn`), «Dar acceso a GitHub» (`setup_github_ssh`), «Revocar acceso a GitHub» (`revoke_github_ssh`) y «Configurar VPS» (`bootstrap_vps`). De «Vaciar VPS» sale el paso que borra las unidades systemd. De «Compilar app Flutter» y «Compilar SPA» salen el número de versión y la subida al VPS.
6. **Consola no escribe configuración de servicios dentro del repo administrado.** Lo único generado que queda dentro del repo es lo que el repo necesita para compilarse sin Consola: `base.generated.js` de cada SPA (del ADR-0021).
7. **Instalar paquetes no configura servicios.** «Instalar paquetes base» instala con apt y nada más (del ADR-0022).

## Consecuencias

- Hasta que existan los botones nuevos —«Configurar VPS» con `install.py`, «Cargar credenciales», «Publicar versión» y «Desplegar versión»— Consola no despliega ningún repo. `pze`, que está en producción con el despliegue propio, queda sin botones de despliegue hasta que siga a canone.
- El código del despliegue propio se recupera del tag: `git show despliegue-propio:core/tasks/vps_server.py`.
- «Compilar ejecutable» conserva el número de versión, la subida al VPS (`upload_to_vps`) y el manifiesto de release ([ADR-0024](0024-publicar-escribe-un-manifiesto-de-release.md)) hasta que se decida qué pasa con él.
- Quedan en pie los botones que leen el despliegue propio sin escribirlo: «Control del servicio», «Ver logs del servicio» y «Health check» buscan las unidades por los nombres viejos, y el ámbito remoto de la base corre el Python del repo desplegado ([`core/runner.py`](../../core/runner.py)).
- Las claves de configuración que solo leían los botones que salen se borran con ellos: `PUBLIC_HOST`, `SECRET_FILES`, `TURN_SECRET`, `TURN_PORT`, `TURN_RELAY_RANGE`, `CSP`, `BACKEND_HOST`, `BACKEND_PORT`, `CERT_FILE_PATH`, `KEY_FILE_PATH` y `SERVICE_DIRS`. Un `config.env` que las tenga las conserva con su valor, al final, bajo «Otras claves» (`envfile.render_config`).

## Descartado

- **Que convivan los dos mecanismos.** El despliegue propio rompe un VPS instalado con canone, y dos caminos para la misma operación dejan a quien aprieta adivinando cuál corresponde a cada VPS.
- **Reimplementar en Consola lo que hacen los programas de canone.** Sería una segunda copia de lo que canone fija, y cada cambio de canone habría que perseguirlo aquí.
- **Lanzar los scripts viejos como subprocesos** (del ADR-0001). Conserva el `print` como único canal, el `SystemExit` como único error y el `input()` que dentro de una ventana no tiene dónde escribirse.
- **Versionar el Caddyfile en el repo** (del ADR-0021). Ataba el proxy al árbol de git.
