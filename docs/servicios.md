# Los tres servicios del VPS

Plan para homologar `configure_service`, `configure_coturn` y `configure_caddy`. Se escribe
porque el tercero se diseñó dos veces seguidas mal, y las dos veces por perder de vista qué es
Consola.

## 1. Qué es Consola, y qué no

Consola es un **instrumento**. Sirve para dejar un VPS listo apretando un botón, y se puede tirar
a la basura sin que nada deje de funcionar.

De ahí salen tres reglas que no se negocian:

1. **El repo no depende de Consola.** Un repo se clona, se compila y se despliega a mano sin
   ella. Consola no exige que el repo traiga archivos que solo ella entiende, ni le inyecta por
   entorno valores sin los cuales el build sale mal.

   Esto **no** le prohíbe editar el repo. Puede escribir archivos ahí igual que los escribiría una
   persona —o yo, ayudándote a programar—: lo que deja tiene que ser un literal committeado que
   siga funcionando cuando Consola no esté. La línea no está en *quién escribe*, está en *qué
   queda*: un valor en un archivo, sí; una lectura en tiempo de build, no.
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
<patrón> <tipo> <destino>

  /api/*      proxy $BACKEND_HOST:$BACKEND_PORT  -> reverse_proxy a esa dirección
  /admin/*    spa backoffice                     -> el build de esa SPA del repo
  /media/*    static $STORAGE_ROOT/public        -> una carpeta del VPS
  *           spa pwa                            -> el catch-all, siempre último
```

Las tres reglas tienen la misma forma: un tipo y un destino. `spa` y `static` recortan el prefijo;
`proxy` no (las rutas del server incluyen su `/api`). Cada `$CLAVE` del destino se resuelve contra
`config.env`, así que el proxy apunta a la misma clave que usa la unidad systemd para escuchar.

Esto reemplaza a los dos ejes que tenía el botón (*qué SPA* y *subruta o subdominio*), con los que
la topología se deducía de los nombres de las carpetas y no había forma de decir «ésta va en la
raíz y esta otra en `/admin`».

## 6. El punto delicado: la ruta pública de cada SPA

Aparece en dos lados y tiene que decir lo mismo:

- en la tabla de rutas, para que el proxy sirva la app bajo `/backoffice`;
- en el repo, para que el build pida sus assets bajo `/backoffice/` y no en la raíz del dominio.

La fuente de verdad es `CADDY_ROUTES`. Pero el valor no puede viajar por el entorno del build,
porque entonces el repo no se compilaría bien sin Consola (regla 1). Así que Consola lo **escribe
como literal** en un archivo que se commitea, y después ese archivo es del repo:

```js
// <spa>/base.generated.js  — lo escribe compile_spa antes de compilar
export const base = "/backoffice";
```

```js
// svelte.config.js (o vite.config.*) del repo
import { base as deployedBase } from './base.generated.js';
// Solo en el build: `vite dev` sirve la SPA sola, en la raíz de su propio puerto, y ahí no hay
// proxy ni prefijo del que colgar. El archivo generado lleva la ruta DESPLEGADA, no la de dev.
const base = process.env.NODE_ENV === 'production' ? deployedBase : '';
```

Es un archivo propio y no un parche sobre la config del repo: **Consola no edita código que no
escribió ella**. Y se escribe en el repo local, que es donde se compila antes de copiar al VPS.

Que Consola *edite* un archivo del repo no viola la regla 1; lo que la violaba era que el repo
*dependiera* de Consola en tiempo de build. Con un literal committeado, quien clona el repo
compila igual, y editar el archivo a mano funciona.

Queda además la comprobación posterior: después de `npm run build`, Consola mira el `index.html`
generado y corta si los assets no cuelgan de la ruta que dice la tabla. Es lo único que no se
puede dar por hecho — una config con la ruta escrita a mano ignora el archivo generado y el build
sale apuntando a otro lado. Ese desacuerdo no da error por sí solo: da una página en blanco.

## 6.1. La copia de referencia del Caddyfile

El Caddyfile vivo es `/etc/caddy/Caddyfile` en el VPS y no hay otro. Pero poder leer la
configuración del proxy sin entrar por SSH es razonable, así que `configure_caddy` deja una copia
en `.consola/Caddyfile.generado` del repo local.

En `.consola/` y no en la raíz ni en `docs/`, por dos motivos: está gitignorado, así que la
referencia no entra al árbol versionado; y nadie la puede confundir con el archivo vivo. Un
Caddyfile en la raíz del repo termina, tarde o temprano, en que alguien lo enlaza desde `/etc` y
el proxy pasa a depender del árbol de git.

**Copia, nunca symlink.** Un symlink en cualquiera de las dos direcciones reintroduce el fallo:
`sudo tee` escribe a través del enlace, y así se perdió el Caddyfile versionado del clon de
producción de concordia.

## 7. Qué falta hacer

**Consola**

1. `configure_caddy`: generar el `Caddyfile` desde `CADDY_ROUTES` a `/etc/caddy/Caddyfile`,
   rompiendo el symlink si lo hubiera, y dejar la copia en `.consola/Caddyfile.generado`. Hecho.
2. `compile_spa`: escribir `<spa>/base.generated.js` antes de compilar y verificar el HTML
   después. Hecho.
3. Revisar que `configure_coturn` y `configure_service` cumplan las reglas de §3. Hoy sí: los dos
   generan a `/etc` y no tocan el repo.

**Concordia**

4. Renombrar `/admin` a `/backoffice`. No hay razón buena para `/admin`: todo lo demás en el repo
   —la carpeta, la cookie, los routers, los tags de OpenAPI— se llama backoffice, y `/admin` es el
   único alias, además de estar en la wordlist de cualquier escáner. Toca 6 prefijos de router,
   `backoffice_cookie_path`, los tests y `verify_backoffice.py`.
5. Borrar el `Caddyfile` de la raíz: manda el que Consola escribe en `/etc`.
6. `backoffice/svelte.config.js` importa la base de `base.generated.js` en vez de tenerla escrita.
7. Restaurar el `Caddyfile` de producción que el botón viejo pisó, si todavía hace falta:
   `cd <deploy>/concordia && git checkout -- Caddyfile`.

**Pendiente, sin decidir**

8. `scripts/vps_setup/setup_caddy.py` queda muerto (su trabajo era el symlink y el drop-in), y
   `scripts/vps_server/update_remote.py:544` recarga un Caddy que ya no depende del `git pull`.
   Se limpian aparte, cuando el botón esté probado contra el VPS real.
