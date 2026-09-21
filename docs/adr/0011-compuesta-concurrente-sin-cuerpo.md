# ADR-0011 · La compuesta que levanta un entorno entero no tiene función: su cuerpo es el despachador de la interfaz

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, ui/tab_panel.py

## Contexto

«Entorno de desarrollo» encadena backend, SPA y apps Python. No es una secuencia: los tres se lanzan a la vez, cada uno en su pestaña, y ninguno termina. «N pestañas vivas» no significa nada dentro de `core/`, que no sabe qué es una pestaña.

## Decisión

1. La capacidad declara `concurrent=True` y `stub=False` a mano, sin `func`.
2. La interfaz reparte sus pasos: cada uno es una capacidad con botón propio, y se lanza con **los parámetros que ya tiene guardados para este repo** — o sea, reusando el mismo camino que el ▶ del buscador.
3. El orden de la lista es el de despacho, y el único que importa es que el backend salga primero: los demás esperan su endpoint desde adentro, no por un `sleep` de la interfaz.

## Consecuencias

- Es la única capacidad del catálogo sin cuerpo, y `registry.implemented()` la cuenta aparte.
- Cambiar los parámetros de un launcher cambia también cómo lo levanta el entorno completo, que es lo que se quiere.

## Descartado

- **Una función que lance los tres.** Tendría que hablar de pestañas desde `core/`.
- **Esperar con un `sleep` entre lanzamientos.** El endpoint ya dice cuándo el backend contesta de verdad.
