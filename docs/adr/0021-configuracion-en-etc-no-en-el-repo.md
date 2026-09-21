# ADR-0021 · La configuración de los servicios se escribe en `/etc` del VPS; en el repo solo queda una copia de referencia

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/tasks/vps_setup.py, core/tasks/vps_server.py

## Contexto

Un Caddyfile versionado en la raíz del repo termina en que alguien lo enlaza desde `/etc/caddy/`, y a partir de ahí el proxy depende del árbol de git: un `git reset --hard` del despliegue puede cambiar la configuración de todo el VPS. Ya pasó: `tee` escribió **a través** del symlink y se perdió aquel archivo.

Al mismo tiempo, mirar la configuración del proxy sin entrar por SSH es razonable.

## Decisión

1. El archivo vivo de cada servicio está en el VPS, en `/etc`, y **no hay otro**: la unidad systemd, el `tmpfiles.d`, `turnserver.conf` y el Caddyfile.
2. Consola no escribe configuración de servicios dentro del repo administrado.
3. Se deja una **copia de referencia** en `.consola/Caddyfile.generado`, que está gitignorada y lleva un encabezado que dice que editarla no cambia nada.
4. Si el archivo de `/etc` es un symlink, Consola **rompe el enlace** y escribe uno propio, dejando en el log a dónde apuntaba.
5. Lo único generado que sí queda dentro del repo es lo que el repo necesita para compilarse sin Consola: `base.generated.js` de cada SPA.

## Consecuencias

- El proxy deja de depender del árbol de git.
- Hay que mirar en dos lugares distintos según qué se busque, y la copia puede quedar vieja si alguien edita a mano en el VPS.

## Descartado

- **Versionar el Caddyfile en el repo.** Es lo que ató el proxy al despliegue.
- **No dejar ninguna copia.** Obliga a entrar por SSH para leer lo que Consola acaba de escribir.
