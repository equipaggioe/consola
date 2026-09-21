# ADR-0003 · El nombre de un eje y el id de un paso son el nombre del parámetro de la función

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/registry.py, core/catalog.py, core/tasks/, ui/params_panel.py

## Contexto

Entre lo que marcaba el panel y los argumentos de la función había una tabla de adaptadores, una entrada por capacidad. Esa tabla se volvió una compuerta: veinte capacidades escritas y probadas se simulaban porque les faltaba una línea ahí.

Al medir por qué hacía falta, las causas resultaron ser cuatro, y tres eran evitables: el eje se llamaba distinto que el parámetro por nada; un segmentado de dos valores era en realidad un booleano y alguien tenía que comparar la cadena a mano; `composed_of` derivaba casillas cuyos ids eran ids de capacidad y jamás coincidían con un parámetro; y una compuesta recibía una lista de ids en vez de un booleano por paso.

## Decisión

1. **El `name` de un eje y el `id` de un paso son el nombre del keyword-argument.** Lo que lee el humano vive aparte, en `label` y `labels`.
2. `Capability.kwargs_from(payload)` arma los kwargs de **cualquier** capacidad desde su propia declaración. No hay tabla de adaptadores.
3. Lo irreducible se declara como dato en el eje, no se resuelve en código: `truthy` (qué valor significa `True`), `cast='int'`, `multiline` (una lista, un valor por renglón), `combine` y `join`.
4. `composed_of` es **documentación** de qué botones encadena este botón; no deriva pasos. Quien quiere una casilla por paso declara `steps=`.
5. Sin `steps`, la capacidad es un solo paso obligatorio y el panel no dibuja esa sección.

## Consecuencias

- Tener cuerpo es la única condición para correr de verdad.
- Renombrar un parámetro obliga a renombrar su eje, y al revés: el contrato es real y se rompe ruidosamente.
- El catálogo queda más declarativo y más largo: cosas que antes se resolvían en una línea de adaptador ahora son un campo del eje.

## Descartado

- **Mantener el adaptador por capacidad.** Era una segunda declaración de lo mismo, que había que acordarse de escribir.
- **Derivar las casillas de `composed_of`.** Produce ids que no le corresponden a ningún parámetro; once capacidades ya declaraban `steps=` a mano para taparlo.
