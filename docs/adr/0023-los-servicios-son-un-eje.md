# ADR-0023 · Los tres servicios systemd del VPS son un eje, no tres botones

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/catalog.py, core/tasks/vps_server.py
- **Modificada por:** [ADR-0041](0041-un-repo-declara-sus-servicios.md), que hace del eje una lista derivada de los servicios que el repo declara. Cambia el punto 1; el resto sigue en pie.

## Contexto

Consola pasó a configurar tres servicios en el mismo VPS: el del repo, coturn y Caddy. Los tres se reinician, se paran y se leen igual, y lo único que cambia entre ellos es el nombre de la unidad. Un botón «Reiniciar coturn» al lado de «Acción systemd» sería la misma función con una constante distinta.

## Decisión

1. `service` es un eje de `systemd_action` y de `view_logs`, con tres valores: `proyecto` (el único cuyo nombre sale del repo abierto), `coturn` y `caddy`.
2. Los valores **no se enumeran**: salen de preguntarle al VPS de ese repo cuáles de los tres existen, en una sola consulta, cacheada por host.
3. Si no se puede preguntar se ofrecen los tres: un VPS todavía sin llave no debería dejar el botón sin valores.
4. Los tres botones de configurar terminan por el mismo cierre (`bring_up_service`), que habilita, reinicia y **comprueba que el servicio quedó vivo**.
5. `daemon-reload` es una acción del eje que no toma nombre de unidad.

## Consecuencias

- Cuando coturn o Caddy no arrancan, lo que hay que leer es su journal, y el botón ya sabe apuntar ahí.
- Hay dos preguntas distintas sobre una unidad y hacen falta las dos: dónde escribe Consola (`/etc/systemd/system`) y qué conoce systemd (las de apt viven en `/lib/systemd/system`).

## Descartado

- **Un botón por servicio.** Nueve acciones por tres servicios son veintisiete botones para una función.
- **Ofrecer los tres siempre.** Elegir coturn en un VPS sin coturn terminaba en un error que se podía haber evitado antes de apretar.
