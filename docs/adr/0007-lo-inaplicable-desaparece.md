# ADR-0007 · Lo que no aplica a este repo desaparece; lo que solo espera un dato queda en ámbar

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, core/registry.py, ui/params_panel.py

## Contexto

Hay dos motivos distintos por los que un botón no puede correr, y tratarlos igual confunde. A veces falta un dato que se puede cargar —la IP del VPS—; a veces falta el objeto sobre el que actuar: «Migrar» en un repo que no versiona su esquema no tiene nada que esperar, porque el repo no tiene Alembic.

## Decisión

1. **Falta un dato** → el botón se ve y queda en ámbar, con las claves que faltan a la vista y la configuración filtrada a ellas.
2. **Falta el objeto** → la capacidad **no existe** en ese repo (`Capability.requires_repo`) y el paso **no se dibuja** (`Step.requires_repo`).
3. Las características del repo se declaran en `core/targets.py` y se detectan mirando lo mismo que miraría la tarea al correr. Hoy la única es `migrations`, que es `alembic.ini` o `alembic/versions/`.
4. Los pasos se caen de la **copia** que mira el panel, no del catálogo: un paso que no se dibujó llega a la función en `False`, o sea apagado, no «sin decidir».
5. Sin repo abierto no se oculta nada: los menús ya están deshabilitados enteros.

## Consecuencias

- Dos repos de la barra pueden ofrecer catálogos distintos, y la lista se recalcula al cambiar de pestaña.
- Una característica nueva se declara en un solo lugar y la reclaman los pasos que la necesiten.

## Descartado

- **Dejar el botón en ámbar también en este caso.** El ámbar promete que cargando algo se destraba, y acá no hay nada que cargar.
- **Ofrecer el paso igual y que falle al correr.** Es prometer un paso que solo podía terminar en el error de Alembic.
