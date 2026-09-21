# ADR-0034 · Lo que se consulta se relee al mostrar la pestaña, sin botón de recargar

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** ui/params_panel.py, ui/tab_panel.py

## Contexto

Los ejes que salen de preguntarle al SDK o al VPS envejecen: se crea un AVD, se instala una imagen, se configura coturn. Un botón «recargar» al lado de la lista le pide al usuario que se acuerde de apretarlo justo cuando la lista ya está mostrando algo viejo.

## Decisión

1. Lo consultado se **relee al mostrar la pestaña** (`reload_catalogs`). Abrir la pestaña es el momento en que se mira la lista, así que es cuando tiene que estar al día.
2. Esa relectura **respeta la caché**: lo que caduca en un minuto se vuelve a preguntar de verdad, y los dos catálogos grandes del SDK no se releen en cada clic.
3. El camino **forzado**, que saltea la caché, tiene dos disparadores: el botón Recargar de Configuración —que además puede haber cambiado a qué VPS se pregunta— y el final de una tarea de máquina, que invalida lo que pudo haber cambiado y avisa a los paneles de su grupo.
4. Mientras la consulta corre, el panel se dibuja con las listas vacías y el botón dice «leyendo el catálogo…».

## Consecuencias

- No hay un botón de recargar por eje.
- La consulta corre en un hilo, y reponer lo guardado ocurre **después** de que las listas se llenan.

## Descartado

- **Un botón de recargar al lado de cada lista.** Pide dos veces lo mismo, y el momento en que se necesita es el de abrir.
- **Releer salteando siempre la caché.** Paga los catálogos grandes del SDK en cada clic para nada.
