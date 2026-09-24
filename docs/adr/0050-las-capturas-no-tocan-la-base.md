# ADR-0050 · Las capturas no tocan la base: los datos salen de un escenario servido por un servidor ficticio

- **Estado:** Aceptada
- **Fecha:** 2026-09-24
- **Alcance:** la cámara de cada repo ([ADR-0049](0049-la-camara-de-capturas-es-un-script-del-repo.md)), `docs/planes/capturas.md`

## Contexto

La cámara de un repo necesita datos ficticios para que las pantallas se vean llenas. En un repo con Postgres, lo inmediato es cargar los seeders mock en la base de desarrollo y apuntar la app al backend real. Eso cambia la base con la que se está trabajando, y las capturas dependen de lo que haya en ella en ese momento: la misma pantalla no sale igual en dos corridas.

Vettore no puede hacerlo así —el servidor no ve el contenido cifrado— y lo resolvió sin tocar nada: un escenario (`demo/escenario.json`), un servidor ficticio que contesta lo que los clientes piden al arrancar, y los clientes de verdad apuntados a ese servidor.

## Decisión

1. **Capturar no cambia la base ni el backend.** Los datos de las capturas salen de un escenario del repo, nunca de cargar datos en una base existente.
2. **Los clientes hablan con un servidor ficticio** que la cámara levanta y que contesta desde el escenario. Sirve igual para la web y para el emulador, que no pasa por el interceptor del navegador.
3. **Una ruta que el servidor ficticio no tiene mapeada hace fallar la corrida.** No contesta 404: un 404 los clientes lo tratan como un fallo de red y la pantalla sale vacía sin que nadie se entere. El servidor anota la ruta y la cámara termina con código distinto de cero, nombrándola.

## Consecuencias

- Las capturas son deterministas: mismo escenario, misma pantalla. La comparación de hashes del manifiesto tiene sentido.
- La cámara corre sin Postgres ni backend levantados.
- Cada repo mantiene el mapa de rutas de su servidor ficticio con la forma de sus esquemas. Un endpoint nuevo que una pantalla empiece a pedir rompe la próxima corrida, que es lo buscado.
- El servidor ficticio de vettore contesta hoy 404 a lo no mapeado y hay que cambiarlo.

## Descartado

- **Cargar los seeders mock en la base de desarrollo** (`rebuild_db` con datos mock) y fotografiar contra el backend real: cambia la base de trabajo y las capturas dependen de su estado.
- **Una base aparte para las capturas**: no cambia la de trabajo, pero sigue necesitando Postgres y backend levantados, y el ciclo de crear, sembrar y borrar la base en cada corrida.
