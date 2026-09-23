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

## 2. Rutas del despliegue

| Función | Qué da |
|---|---|
| `vps.repo_name(config)` | El nombre que va a crear `git clone`, derivado de `GIT_REPO_URL`. La carpeta local puede no coincidir, y por eso no se usa como default silencioso |
| `vps.deploy_root` | `<VPS_DEPLOY_DIR>/<repo>` |
| `vps.remote_path(config, *partes)` | La misma jerarquía relativa que en el repo local |
| `vps.remote_python` | El intérprete del venv del servidor, dentro del repo desplegado |
| `vps.ensure_deploy_dir` | Crea la carpeta con sudo y se la pasa al usuario de despliegue. `VPS_DEPLOY_DIR` suele apuntar a `/srv` o `/opt`, que son de root, y el problema aparecía recién en el `git clone`, con un «Permission denied» que no decía qué faltaba |

## 3. Paquetes

`vps.PACKAGE_GROUPS` agrupa por lo que significan para quien elige, no por cómo se llaman en apt (`python` son tres paquetes): `python`, `git`, `postgresql`, `postgis`, `caddy`, `ufw`, `redis`, `coturn`. Arrancan marcados los cinco de `DEFAULT_GROUPS`: lo que necesita un backend Python detrás de Caddy.

Instalar saltea lo que ya está (`dpkg -s`). Configurar **no** instala: `vps.require_package` corta con «Corre "Software base" con el grupo X marcado». Instalar el paquete y configurar el servicio son dos acciones distintas, y la segunda se repite mientras la primera pasa una sola vez ([ADR-0022](../adr/0022-instalar-y-configurar-son-dos-botones.md)).

`vps.open_ports` abre en ufw si ufw manda; si no está activo, **lo dice**: el firewall puede estar en el panel del proveedor, y ahí los puertos siguen cerrados.

## 4. Los servicios del VPS

Consola administra en el mismo VPS las unidades systemd **del repo** más `coturn` y `caddy`. Todas se reinician, se paran y se leen igual, así que `service` es **un eje** de `systemd_action` y de `view_logs`, no un botón por servicio ([ADR-0023](../adr/0023-los-servicios-son-un-eje.md)).

Cuántas son las del repo lo dice el repo: `SERVICES` es una tabla de filas `<sufijo> <tipo> <destino>` y cada fila es una unidad ([ADR-0041](../adr/0041-un-repo-declara-sus-servicios.md)). Sin tabla hay una sola, llamada como el repo, que es el valor `proyecto` del eje de siempre.

| Tipo | Destino | `ExecStart` |
|---|---|---|
| `uvicorn` | El entrypoint | Consola arma la línea: dónde escucha, TLS y `--proxy-headers` |
| `python` | Argumentos | El intérprete del venv del repo con eso |
| `command` | La línea entera | Tal cual |

`vps.managed_services` arma los valores del eje —los del repo y después los dos paquetes— y `vps.resolve_service` los traduce al nombre real de la unidad: `<repo>` sin tabla, `<repo>-<sufijo>` con ella. Los valores que se ofrecen no se enumeran: `vps.installed_services` pregunta cuáles existen en **este** VPS, en una sola consulta, y el resultado se cachea por host. Si no se puede preguntar los devuelve todos, para no dejar el botón sin nada que ofrecer.

Dos preguntas distintas sobre una unidad, y las dos hacen falta: `service_exists` mira `/etc/systemd/system` (donde Consola escribe la del proyecto) y `unit_installed` pregunta con `systemctl cat` (las de un paquete apt viven en `/lib/systemd/system`).

### Escribir configuración

`vps.write_config` es el único escritor: compara contra lo que hay, imprime un `diff` unificado, escribe por `sudo tee` con heredoc y **devuelve si cambió**. Los tres botones de configurar eran los únicos que sobrescribían a ciegas y reiniciaban siempre.

Ese booleano es lo que separa `restart` de `start` en `vps_server.bring_up_service`, el cierre común de los tres: con configuración nueva hay que reiniciar para que entre; sin cambios alcanza con asegurarse de que esté corriendo. Recargar Caddy corta el 80 y el 443 de **todo** el VPS, así que ese reinicio de más se paga en cada corrida.

`bring_up_service` además **comprueba que el servicio quedó vivo**: la unidad es `Type=simple` con `Restart=always`, así que `systemctl restart` devuelve 0 en cuanto el proceso arranca, aunque muera un segundo después. Sin esa comprobación, «servicio instalado» se imprimía con el backend caído.

Desmarcar «Arrancar» es la ventana de mantenimiento: la configuración nueva queda escrita y el servicio sigue con la vieja, y el botón lo dice al terminar.

## 5. Los servicios del repo

`configure_service` escribe una unidad por fila de `SERVICES` y las deja corriendo; `remove_systemd_service` las borra todas, porque dejar viva la mitad de un repo «eliminado» es peor que no borrar nada. Antes exige que haya código y venv en el VPS (`_require_deployment`): sin eso la unidad se escribía igual, uvicorn moría por falta de intérprete y `Restart=always` lo reintentaba cada 3 segundos, todo después de un mensaje de éxito.

Antes de la unidad escribe las carpetas del servicio: `SERVICE_DIRS` se vuelca a `/etc/tmpfiles.d/<servicio>.conf`, que systemd vuelve a aplicar en cada arranque. Van fuera del repo porque el despliegue corre `git clean`.

Dónde escucha el backend sale de `BACKEND_HOST` y `BACKEND_PORT`, no de un parámetro del botón: es el mismo dato que necesita Caddy para saber a dónde mandar el tráfico. De ahí se derivan tres cosas más, todas para los servicios de tipo `uvicorn`: **TLS** solo cuando el backend da la cara a internet (detrás de Caddy, el tramo hasta el upstream es HTTP), **abrir el puerto en ufw** solo en ese mismo caso, y **`--proxy-headers`** justo en el contrario — escuchando en loopback hay un proxy delante, y sin eso el backend ve todas las peticiones como `http` y con la dirección del proxy.

## 6. La tabla de rutas públicas

`PUBLIC_ROUTES` es una lista ordenada de reglas `<patrón> <tipo> <destino>`. Gana la primera que matchea, que es la semántica de Caddy — y por eso el orden es información, no presentación ([ADR-0019](../adr/0019-tabla-de-rutas-publicas.md)).

Un patrón es **un host más una ruta**, y las dos partes van escritas ([ADR-0040](../adr/0040-una-regla-es-host-mas-ruta.md)). `split_pattern` lo parte:

| Patrón | Host | Ruta |
|---|---|---|
| `api.ejemplo.net` | `api.ejemplo.net` | `*` |
| `api.ejemplo.net/*` | `api.ejemplo.net` | `*` |
| `api.ejemplo.net/v1/*` | `api.ejemplo.net` | `/v1/*` |

Un patrón sin host **corta**. El host va aunque el repo no tenga proxy: la tabla dice dónde se publica cada cosa, no quién la sirve ([ADR-0020](../adr/0020-ruta-publica-no-implica-proxy.md)), y esa dirección tiene host igual.

Las dos formas valen y el generador no prefiere ninguna. Lo que las separa es el **origen del navegador**: `localStorage`, `IndexedDB`, el scope del service worker y la CSP son por origen, así que dos aplicaciones bajo un mismo host comparten todo eso. A cambio, separarlas en dos hosts trae CORS, un registro DNS por pieza y un certificado por pieza. Cuál conviene depende de si las piezas de ese repo comparten sesión ([ADR-0040](../adr/0040-una-regla-es-host-mas-ruta.md)).

| Tipo | Destino | Qué hace Caddy |
|---|---|---|
| `proxy` | `host:puerto` | `reverse_proxy`. No recorta el prefijo: las rutas del server ya incluyen su `/api` |
| `spa` | Nombre de una carpeta SPA del repo | Sirve su build, recorta el prefijo y cae en `index.html` |
| `static` | Ruta del VPS | Sirve la carpeta y recorta el prefijo |

`$CLAVE` en el destino se resuelve contra la configuración (`$BACKEND_HOST:$BACKEND_PORT`). El catch-all se queda con todo lo que llegue **a su host**, así que tiene que ir último *de ese host*, no de la tabla. Una fila que no se entiende **corta**: una regla ignorada en silencio no falla al escribir, falla en producción, cuando el tráfico que iba al backend cae en la SPA.

La clave se llama `PUBLIC_ROUTES` y no `CADDY_ROUTES` porque Caddy es **un** consumidor de la tabla, no su dueño: la misma tabla la lee el build para saber con qué `base` compilar cada SPA ([17](17_builds_y_artefactos.md)). De ahí salen dos preguntas que parecen una:

- `declares_routes` — ¿el repo declaró su tabla? Decide si hay una ruta pública que escribirle al build.
- `uses_proxy` — ¿hay alguna regla `proxy`? Decide dónde escucha el backend. Un repo puede publicar diez SPA y servirlas él mismo ([ADR-0020](../adr/0020-ruta-publica-no-implica-proxy.md)).

## 7. Caddy

`configure_caddy` arma el Caddyfile entero en una función sin efectos (`_caddyfile`), que es lo único que se puede probar sin un VPS — y `tests/test_caddyfile.py` lo prueba. Emite **un bloque de sitio por host** (`_site`), en el orden en que cada host aparece en la tabla; un solo host es el caso de un bloque, no otra rama del generador.

Escribe siempre tres cabeceras de seguridad —HSTS, `nosniff` y `Referrer-Policy`—, porque cada una tiene un solo valor sensato y son de las que uno se olvida. La CSP no: cambia entre proyectos **y entre sitios del mismo proyecto**, así que `CSP` es una tabla `<host> <política>` con `*` para los sitios que no tengan la suya ([ADR-0040](../adr/0040-una-regla-es-host-mas-ruta.md)). Una fila sin host corta, igual que un patrón sin host.

Cuatro cuidados que están en el código por algo que pasó:

- Si `/etc/caddy/Caddyfile` es un **symlink**, `tee` escribiría a través de él. Consola rompe el enlace y escribe un archivo propio, dejando en el log a dónde apuntaba.
- Una regla `static` cuya carpeta no existe **corta antes de escribir**: Caddy no falla por eso, devuelve 404 y hay que ir a buscar por qué.
- Un Caddyfile con un error de sintaxis deja el servicio caído, y con él todo lo que publica el VPS: se corre `caddy validate` antes de recargar.
- La copia de referencia va a `.consola/Caddyfile.generado`, que está gitignorado. Un Caddyfile en la raíz del repo termina en que alguien lo enlaza y el proxy pasa a depender del árbol de git ([ADR-0021](../adr/0021-configuracion-en-etc-no-en-el-repo.md)).

## 8. coturn

`configure_coturn` escribe `/etc/turnserver.conf` con el realm (`PUBLIC_HOST`), los puertos y el secreto. Los tres son **datos** y no parámetros: el backend tiene que anunciar en sus URLs `turn:` exactamente lo que quedó en el archivo. Lo único que se elige al apretar es si el TURN sale por TLS.

`TURN_SECRET` se genera una vez y queda en `config.env`. Antes salía de `secrets.token_hex` en cada corrida: cada reconfiguración dejaba al servidor exigiendo un secreto que el backend ya no tenía, y las llamadas se caían sin que nada lo dijera.

El certificado es el mismo que sube el despliegue, no uno propio; si no está en el VPS se sigue sin TLS y se avisa, porque un `cert=` apuntando a un archivo inexistente deja el servicio sin arrancar.

## 9. Desplegar el código

`publish_code` deja el VPS con el código y todo lo que necesita para arrancar, **sin tocar nada que ya esté corriendo**:

| Paso | Qué hace |
|---|---|
| `push` | Empuja la rama local. El VPS clona de GitHub y no de esta máquina: sin este paso se publica el commit de otro. No commitea: avisa si hay cambios sin commitear y sigue |
| `pull` | `sync_repository`: clona si no está, y si está hace `fetch --all` y `reset --hard` al upstream |
| `deps` | Crea el venv si falta e instala `requirements.txt` adentro |
| `upload` | Sube los archivos de `SECRET_FILES` con `chmod 600` |

`update_remote` es eso más migrar y reiniciar. Reenvía las cuatro banderas a `publish_code` en vez de reescribir los pasos; el panel sigue mostrando las seis casillas planas ([ADR-0038](../adr/0038-una-compuesta-reusa-otra-entera.md)).

Existen las dos porque en un servidor recién armado los dos últimos pasos no se pueden dar: migrar sería contra una base que todavía no existe, y reiniciar contra un servicio que todavía no está instalado. Por eso `bootstrap_vps` usa `publish_code` tal cual.

El paso de migraciones de `update_remote` **solo aplica** (`alembic upgrade head`). El script original además generaba contra la base del VPS, lo que autogenera revisiones en producción a partir de un modelo que quizá ni se commiteó ([ADR-0013](../adr/0013-generar-en-local-aplicar-donde-este-la-base.md)).

El `reset --hard` del VPS es la única parte destructiva, y el eje `discard_changes` ofrece las dos respuestas legítimas: preguntar con la lista de archivos a la vista, o descartar sin preguntar. El botón `git_force_reset` (grupo Repositorio) es esa misma función con el eje `side` en `vps`.

## 10. Deshacer

`clean_vps` es la reversa del bootstrap: borra el servicio, la base, el repo desplegado, la llave de GitHub, los paquetes y el usuario. Los seis son casillas del mismo formulario porque la operación casi siempre se pide entera, y el orden importa: los paquetes se purgan con el sudo del usuario de despliegue, así que borrar el usuario va último.

`revoke_ssh` muestra la huella exacta que va a sacar antes de tocar nada: revocar la llave equivocada deja el servidor inalcanzable. Sus dos lados son desmarcables por separado, igual que los de `revoke_github_ssh`: una llave puede quedar dada de baja en GitHub y seguir en el disco del VPS.

## 11. Diagnóstico

`health` pregunta primero si se llega por SSH y **corta ahí** si no. Las otras cuatro consultas usan `check=False`, así que con el SSH caído devolvían vacío y el estado del servicio caía en `missing`: el resumen anunciaba un servidor destruido cuando la verdad era que no se llegaba a la máquina.

`view_logs` arma un `journalctl` con filtros. Es capacidad hermana de `systemd_action` y no un valor suyo: los filtros no tienen sentido para start/stop. Hoy el panel no ofrece esos filtros ([30](30_riesgos_y_pendientes.md)).
