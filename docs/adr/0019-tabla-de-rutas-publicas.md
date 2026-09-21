# ADR-0019 · Bajo qué ruta se publica cada cosa es una tabla ordenada de reglas, y es un dato del despliegue

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/vps.py, core/settings.py, core/tasks/vps_setup.py, core/tasks/builders.py
- **Modificada por:** [ADR-0040](0040-una-regla-es-host-mas-ruta.md), que hace del host parte de la regla. Cambia los puntos 1 y 6; el resto sigue en pie.

## Contexto

La topología del proxy se deducía de dos preguntas del panel —qué SPA publicar y si iban por subruta o subdominio— con el nombre de cada carpeta como prefijo de URL. Así no había forma de decir «esta va en la raíz y esta otra en /admin», ni de mandar `/api` al backend.

Una topología real no sale de dos preguntas: es una lista ordenada de reglas. Y existiría igual si el Caddyfile se escribiera a mano, así que es un dato del despliegue y no un parámetro de la corrida.

## Decisión

1. `PUBLIC_ROUTES` es una lista ordenada de reglas `<patrón> <tipo> <destino>`, con tres tipos: `proxy`, `spa` y `static`. Gana la primera que matchea, que es la semántica de Caddy — el orden es información.
2. Vive en la configuración del repo, no en los parámetros del botón, porque **dos botones distintos tienen que leer exactamente el mismo valor**: el proxy y el build.
3. Se llama `PUBLIC_ROUTES` y no `CADDY_ROUTES` porque Caddy es un consumidor de la tabla, no su dueño.
4. `$CLAVE` en el destino se resuelve contra la configuración, para no repetir un valor que ya está cargado.
5. Una fila que no se entiende **corta**: una regla ignorada en silencio no falla al escribir, falla en producción cuando el tráfico que iba al backend cae en el catch-all de la SPA.
6. El catch-all `*` tiene que ser la última regla.
7. La tabla se interpreta en funciones sin efectos (`parse_routes`, `_caddyfile`), que es lo único que se puede probar sin un VPS.

## Consecuencias

- El build de cada SPA sabe con qué `base` compilar, leyendo la misma tabla ([ADR-0020](0020-ruta-publica-no-implica-proxy.md)).
- La tabla se escribe a mano, con una gramática propia que hay que documentar y validar.
- El nombre viejo `CADDY_ROUTES` se sigue leyendo como respaldo.

## Descartado

- **Deducir la topología de la forma del repo.** No sabe expresar la raíz, ni `/api`, ni un orden.
- **Un eje del panel por SPA.** Sería la misma decisión guardada en dos botones, con la oportunidad de que discrepen.
