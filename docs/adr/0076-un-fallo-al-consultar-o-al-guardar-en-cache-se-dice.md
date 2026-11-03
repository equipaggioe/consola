# ADR-0076 · Un fallo al consultar o al guardar en caché se dice, y no se esconde

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/catalog.py, core/vps.py, core/cache.py, ui/params_panel.py

## Contexto

«Sin fallbacks» de `principios.md` no admite valores por defecto silenciosos ni handlers vacíos. Tres ADR los pedían: un fallo al consultar un eje devolvía una lista vacía (punto 6 del [ADR-0006](0006-ejes-descubiertos-y-consultados.md)), un VPS que no contesta ofrecía todos los servicios (punto 3 del [ADR-0023](0023-los-servicios-son-un-eje.md)), y una caché ilegible era una caché vacía (punto 6 del [ADR-0030](0030-cache-de-catalogo-no-de-estado.md)).

Este ADR reemplaza los tres puntos.

## Decisión

1. **Un eje consultado cuya fuente falla muestra el motivo**, en lugar del eje, y el botón queda bloqueado con ese mensaje. Vale para el SDK de Android, el VPS, la cámara y GitHub.
2. **`vps.installed_services` corta si no se entra al VPS.**
3. **El inventario de lo vivo muestra el motivo si no se pudo consultar.**
4. **Una entrada de caché que no se puede leer ni escribir corta**, nombrando el archivo. Una que no existe o que venció se vuelve a pedir.

## Consecuencias

- Sin el SDK de Android, los botones de emuladores dicen por qué están bloqueados en vez de ofrecer una lista vacía.
- Con el VPS caído, «Control del servicio» y «Ver logs del servicio» quedan bloqueados, con el motivo a la vista.
- Un archivo de caché dañado se borra a mano de la carpeta de datos de Consola.

## Descartado

- **Ofrecer todos los servicios si no se puede preguntar.** Ofrece coturn en un VPS que no lo tiene, y esconde que el VPS no contesta.
