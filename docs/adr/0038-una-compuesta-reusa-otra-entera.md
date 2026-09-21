# ADR-0038 · Una compuesta reusa a otra solo si quiere todos sus pasos

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/tasks/vps_server.py, core/tasks/database.py, core/tasks/vps_setup.py

## Contexto

Una compuesta puede encadenar a otra —`bootstrap_vps` llama a `publish_code` y a `bootstrap_db`—, pero solo si quiere **todo** lo que la otra hace. Llamarla con la mitad de sus pasos apagados es usar su nombre para algo que no es, y deja al lector del panel adivinando qué corre de verdad.

## Decisión

1. Si una compuesta quiere todos los pasos de otra, **la llama** y le reenvía sus banderas.
2. Si quiere solo una parte, esa parte se extrae a una compuesta propia con nombre, y las dos la usan: por eso existe `publish_code` aparte de `update_remote`, y `populate_db` aparte de `bootstrap_db` y `rebuild_db`.
3. Una compuesta intermedia **no tiene por qué tener botón**: `populate_db` no lo tiene, porque «llenar una base que ya está ahí» sin decir por cuál de los dos caminos se llegó no es una intención que alguien tenga suelta.
4. La compuesta de adentro **no se ve desde afuera**: el panel de `update_remote` muestra sus seis casillas planas.
5. Los parámetros que la externa no reenvía quedan clavados en su default, y eso es un agujero a revisar cada vez que se agrega un eje.
6. Si un paso falla, la receta se detiene ahí: cada compuesta interna ya sabe revertir lo suyo.

## Consecuencias

- Los pasos comunes existen una sola vez, con sus etiquetas: antes estaban copiados tal cual en las dos.
- Aparecen compuestas sin botón, que hay que reconocer como tales al leer el módulo.

## Descartado

- **Llamar a la otra compuesta con pasos apagados.** Usa su nombre para algo que no es.
- **Copiar los pasos comunes en las dos.** Es lo que hacía que una cambiara de etiqueta y la otra no.
