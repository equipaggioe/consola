# Los tres servicios del VPS

Plan para homologar `configure_service`, `configure_coturn` y `configure_caddy`. Se escribe
porque el tercero se diseñó dos veces seguidas mal, y las dos veces por perder de vista qué es
Consola.

## 1. Qué es Consola, y qué no

Consola es un **instrumento**. Sirve para dejar un VPS listo apretando un botón, y se puede tirar
a la basura sin que nada deje de funcionar.

De ahí salen tres reglas que no se negocian:

1. **El repo no depende de Consola.** Un repo se clona, se compila y se despliega a mano sin ella.
   Consola no deja archivos dentro del árbol versionado, no exige que el repo traiga archivos que
   solo ella entiende, y no le inyecta valores sin los cuales el repo no se compila bien.
2. **El VPS no depende de Consola.** Lo que Consola escribe en el servidor son archivos estándar
   de ese servicio —una unidad systemd, un `turnserver.conf`, un `Caddyfile`—, legibles y
   editables a mano. Si Consola desaparece, el servidor sigue andando y cualquiera puede seguir
   operándolo con `systemctl` y un editor.
3. **Consola es genérica.** Nada de lo que hace puede estar atado a un repo en particular. Si una
   capacidad solo sirve para concordia, está mal planteada.

La regla 1 es la que se violó al pedirle a concordia que trajera su propio `Caddyfile` y que su
`svelte.config.js` leyera una variable de Consola. La regla 3 es la que se violó al deducir la
topología del proxy de los nombres de las carpetas del repo.

## 2. Los tres son el mismo botón

`configure_service` (el backend del repo), `configure_coturn` y `configure_caddy` hacen lo mismo
sobre tres servicios distintos:

```
leer los datos -> generar el archivo de configuración -> escribirlo en el VPS (mostrando el diff)
  -> validar -> abrir puertos -> habilitar -> arrancar -> comprobar que quedó vivo
```

El cierre ya está compartido (`vps_server.bring_up_service`) y los tres se dibujan igual (dos
casillas: *Habilitar* y *Arrancar*, porque escribir es lo que el botón **es**). Lo que falta
homologar es el principio: de dónde salen los datos y dónde queda el archivo.

## 3. Dónde queda cada archivo generado

Todos en `/etc`, que es donde vive la configuración de un servicio en Linux. Ninguno dentro del
repo, ni en el VPS ni en local.

| Servicio | Archivo que genera Consola | Dueño |
|---|---|---|
| Backend del repo | `/etc/systemd/system/<repo>.service` | Consola |
| coturn | `/etc/turnserver.conf` (+ el `TURNSERVER_ENABLED` de `/etc/default/coturn`) | Consola |
| Caddy | `/etc/caddy/Caddyfile` | Consola |

«Dueño: Consola» significa que el botón lo sobrescribe, mostrando antes el diff en el log
(`vps.write_config`). No es un archivo a cuatro manos.

Dos correcciones que esto implica:

- **Nunca escribir a través de un symlink.** `sudo tee` sobre un symlink escribe en el destino.
  Así se perdió el `Caddyfile` versionado dentro del clon de producción de concordia, que era a
  donde apuntaba `/etc/caddy/Caddyfile`. Antes de escribir hay que romper el enlace y avisar.
- **Consola no crea symlinks hacia el repo.** Enlazar `/etc/caddy/Caddyfile` al clon hace que el
  servidor dependa del árbol de git para arrancar, y que un `git pull` cambie la configuración del
  proxy sin que nadie lo pida.

## 4. Dónde viven los datos

En `.consola/config.env`, que está gitignorado: es de la máquina y del despliegue, no del repo.

El criterio de reparto entre `config.env` y `params.json` es **contrafáctico**, no «quién lo lee»:

> Si esto lo configurara a mano por SSH, ¿el valor existiría igual?

- **Sí → `config.env`** (`core/settings.py::SETTINGS`, editable en el panel de Configuración). Es
  estructura del despliegue: el dominio, los puertos, la tabla de rutas del proxy.
- **No, solo existe porque hay una app con botones → `params.json`**: qué casillas de una
  compuesta se marcan, los seguros `@protection`, el orden de las pestañas.

Los datos de cada servicio, hoy:

| Servicio | Claves de `config.env` |
|---|---|
| Backend | `SERVER_DIR`, `UVICORN_APP`, `BACKEND_HOST`, `BACKEND_PORT`, `CERT_FILE_PATH`, `KEY_FILE_PATH` |
| coturn | `PUBLIC_HOST`, `TURN_PORT`, `TURN_RELAY_RANGE`, `TURN_SECRET`, `CERT_FILE_PATH`, `KEY_FILE_PATH` |
| Caddy | `PUBLIC_HOST`, `CADDY_ROUTES`, `CSP`, `STORAGE_ROOT`, `BACKEND_HOST`, `BACKEND_PORT` |

`BACKEND_HOST`/`BACKEND_PORT` aparecen dos veces a propósito: es una sola clave leída por los dos
lados del mismo hecho —dónde escucha el backend y a dónde manda el proxy—, que es la forma de que
no queden apuntando a lugares distintos.

## 5. La tabla de rutas del proxy

El único dato de los tres que no es un escalar. Es una lista ordenada de reglas, primera que
matchea gana — la misma forma que tienen por dentro los `handle` de Caddy, los `rewrites` de
Vercel, los `_redirects` de Netlify y los `paths` de un Ingress de Kubernetes.

Va en `CADDY_ROUTES`, un `Setting(kind='list')`: el panel lo edita con un renglón por regla y
conserva el orden. Se guarda separado por comas, así que **ningún valor puede contener una coma**.

```
<patrón> <destino>

  /api/*      backend              -> reverse_proxy a BACKEND_HOST:BACKEND_PORT
  /admin/*    spa backoffice       -> el build de esa SPA del repo
  /media/*    static $STORAGE_ROOT/public   -> una carpeta del VPS
  *           spa pwa              -> el catch-all, siempre último
```

`spa` y `static` recortan el prefijo; `backend` no (las rutas del server incluyen su `/api`). El
`$CLAVE` inicial de un `static` se resuelve contra `config.env`.

Esto reemplaza a los dos ejes que tenía el botón (*qué SPA* y *subruta o subdominio*), con los que
la topología se deducía de los nombres de las carpetas y no había forma de decir «ésta va en la
raíz y esta otra en `/admin`».

## 6. El punto delicado: la ruta pública de cada SPA

Aparece en dos lados y tiene que decir lo mismo:

- en la tabla de rutas, para que el proxy sirva la app bajo `/admin`;
- en el repo (`svelte.config.js`, `vite.config.*`), para que el build pida sus assets bajo
  `/admin/` y no en la raíz del dominio.

**El repo es el dueño de su base**, por la regla 1: tiene que poder compilarse solo. Consola no la
inyecta. Lo que hace es **verificar**: después de `npm run build` mira el `index.html` generado y,
si los assets no cuelgan de la ruta que dice la tabla, corta. Ese desacuerdo no da error por sí
solo —el proxy sirve la app y el navegador pide los assets donde vive la otra— y lo que se ve es
una página en blanco.

Se mira el resultado y no la config del repo: cómo resuelve cada uno su base es asunto suyo, y
parsear JS para averiguarlo sería adivinar.

## 7. Qué falta hacer

1. `configure_caddy`: generar el `Caddyfile` desde `CADDY_ROUTES` a `/etc/caddy/Caddyfile`,
   rompiendo el symlink si lo hubiera. **Hecho en el árbol de trabajo, sin commitear.**
2. `compile_spa`: verificar la base contra la tabla en vez de inyectarla. **Hecho, sin commitear.**
3. Revisar que `configure_coturn` y `configure_service` cumplan las mismas reglas de §3 (hoy sí:
   los dos generan a `/etc` y no tocan el repo).
4. Restaurar el `Caddyfile` de producción de concordia, que este botón pisó:
   `cd <deploy>/concordia && git checkout -- Caddyfile`.
5. **Decisión pendiente, de concordia y no de Consola**: hoy concordia mantiene su `Caddyfile`
   versionado en la raíz más un `scripts/vps_setup/setup_caddy.py` que lo enlaza. Con Consola
   generando `/etc/caddy/Caddyfile` desde `CADDY_ROUTES`, hay dos fuentes para lo mismo. O se
   deja el del repo y Consola no toca Caddy en ese repo, o se borra el del repo y manda la tabla.
   No se puede tener las dos.
