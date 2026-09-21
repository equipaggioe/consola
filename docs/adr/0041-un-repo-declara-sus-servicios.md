# ADR-0041 · Un repo declara sus servicios en una tabla; uno solo es el caso de una fila

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/settings.py, core/tasks/vps_server.py, core/tasks/vps_ops.py, core/catalog.py

## Contexto

Consola daba por hecho que un repo tiene **un** proceso largo: `service_name` devolvía un
nombre, `write_systemd_unit` escribía una unidad y el eje `service` del
[ADR-0023](0023-los-servicios-son-un-eje.md) tenía tres valores fijos, uno de ellos el repo.

Eso no es una propiedad de los repos, es una suposición. Un repo con una API y un enviador de
avisos tiene dos procesos largos; uno con un consumidor de cola, también. Para systemd son dos
unidades y no hay nada que las distinga salvo su comando. Sin forma de declararlo, la única
salida era meter el segundo proceso dentro del primero —una tarea de fondo en el proceso web—,
que acopla su ciclo de vida al del servidor e impide levantar más de un worker.

Es el mismo error que el [ADR-0040](0040-una-regla-es-host-mas-ruta.md) corrigió en las rutas:
el caso simple estaba clavado en el modelo en vez de ser una fila de una tabla.

## Decisión

1. **`SERVICES` es una lista ordenada de filas `<sufijo> <tipo> <destino>`**, con la misma
   forma que `PUBLIC_ROUTES`. Tres tipos:

   | Tipo | Destino | `ExecStart` |
   |---|---|---|
   | `uvicorn` | El entrypoint | Consola arma la línea: dónde escucha, TLS y `--proxy-headers` |
   | `python` | Argumentos | El intérprete del venv del repo con eso |
   | `command` | La línea entera | Tal cual |

2. **Tabla vacía = un servicio**, llamado como el repo y corriendo `UVICORN_APP`. Es
   exactamente lo que había antes de que la tabla existiera, y por eso un repo que nunca la
   declaró no ve su unidad renombrada.
3. **Con tabla, cada unidad se llama `<repo>-<sufijo>`.** El nombre pelado queda para el repo
   sin tabla, que es el que ya está corriendo en los VPS desplegados.
4. **El eje `service` sale de la tabla**, no de una constante: los del repo primero y después
   los dos paquetes que Consola configura (`coturn`, `caddy`). Modifica el punto 1 del
   ADR-0023.
5. **`proyecto` sigue resolviendo**, al primero de la tabla. Es el valor por omisión de
   `systemd_action`, `view_logs` y `bring_up_service`, y un repo sin tabla no tiene otro nombre.
6. **`configure_service` escribe y levanta todas las unidades**; `remove_systemd_service` las
   borra todas. Dejar viva la mitad de un repo «eliminado» es peor que no borrar nada, porque
   nada lo dice.
7. **Un servicio `uvicorn` detrás de un proxy arranca con `--proxy-headers` y
   `--forwarded-allow-ips 127.0.0.1`.** Consola ya decide que escuche en loopback cuando hay
   tabla de rutas, o sea que ya sabe que hay un proxy delante; no decírselo a uvicorn dejaba al
   backend viendo todas las peticiones como `http` y con la dirección del proxy.

## Consecuencias

- Un repo que **empieza** a declarar la tabla renombra su unidad de `<repo>` a
  `<repo>-<sufijo>`. La vieja sigue instalada y corriendo: hay que borrarla antes, con
  «Eliminar servicio» sobre la configuración anterior.
- El eje `service` de un repo con tres procesos ofrece cinco valores. `installed_services`
  sigue preguntándole al VPS cuáles existen, así que la lista no crece con los que nunca se
  instalaron.
- `SERVICE_DIRS` sigue siendo del repo y no de cada servicio: se vuelca a un solo
  `/etc/tmpfiles.d/<repo>.conf`. Las carpetas son del proyecto, no de un proceso.
- Los tipos `python` y `command` no pasan por `bash`: `ExecStart` de systemd no expande
  variables de entorno ni tuberías. Un comando que las necesite va en un script del repo.

## Descartado

- **Una clave aparte para «workers adicionales».** Sería el mismo error otra vez: el caso de
  un servicio clavado en el modelo y todo lo demás como excepción. Un backend y un worker son
  dos unidades de systemd, y systemd no los distingue.
- **Hacer que cada fila escriba su `ExecStart` entero.** Obligaba a repetir a mano la línea de
  uvicorn con su host, su puerto y su TLS condicional, que es justo lo que Consola sabe
  resolver desde la configuración.
- **Numerar las unidades (`<repo>-1`, `<repo>-2`).** El nombre de una unidad es lo que se lee
  en `systemctl status` y en el journal: tiene que decir qué corre.
