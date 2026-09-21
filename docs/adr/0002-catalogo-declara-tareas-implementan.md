# ADR-0002 · El catálogo declara la forma de un botón y `core/tasks/` le da cuerpo

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, core/registry.py, core/tasks/

## Contexto

La forma de un botón —grupo, sección, ejes, pasos, icono, descripción— y su implementación cambian por motivos distintos y en momentos distintos. Mezcladas, no hay forma de dibujar la interfaz entera antes de que exista una sola función, ni de ver de un vistazo qué falta implementar.

## Decisión

1. `core/catalog.py::load_catalog()` **declara** las capacidades, todas con `stub=True`.
2. `core/tasks/<grupo>.py::bind_all()` llama a `Registry.bind(id, func)`, que le pone el cuerpo y baja el stub.
3. `main.py` llama a las dos, en ese orden, una vez por proceso.
4. Lo que nadie vincule **sigue siendo un stub** y la interfaz lo simula: reporta exactamente lo que correría.
5. `bind` levanta `KeyError` si el id no existe: un bind sin declaración es un error de programación, no un botón silencioso.

## Consecuencias

- La interfaz funcionó completa mientras se escribían las funciones, una por una.
- `registry.implemented()` dice en cualquier momento cuántas tienen cuerpo. Hoy son 61 de 62.
- Un id vive escrito en dos archivos, y renombrarlo obliga a tocar los dos.

## Descartado

- **Declarar la capacidad junto a su función.** Habría atado dibujar la interfaz a tener la implementación, y esparcido por nueve módulos la decisión de cómo se ve el catálogo entero.
