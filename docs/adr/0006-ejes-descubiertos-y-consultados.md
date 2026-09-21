# ADR-0006 · Los valores de un eje pueden salir de mirar el repo o de preguntarle a una herramienta

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, core/targets.py, ui/params_panel.py

## Contexto

Varios ejes no se pueden enumerar en el catálogo. Las SPA de un repo son tres en uno y una en otro; los AVD creados cambian mientras la aplicación está abierta; las system images publicadas son varios cientos y solo las conoce el SDK; y qué servicios systemd existen solo lo sabe el VPS de ese repo. El catálogo, en cambio, se arma una sola vez al arrancar.

## Decisión

1. Un eje **descubierto** (`discover=`) declara qué tipos de subproyecto lo llenan. `catalog.for_project(cap, root)` los resuelve mirando el repo, sobre una **copia** de la capacidad, justo antes de dibujar el panel.
2. Un eje **consultado** (`source=`) declara a qué fuente se le pregunta. `catalog.queried_values()` la consulta y devuelve valores y etiquetas.
3. Lo consultado corre **fuera del hilo de la interfaz** (`AxesLoader`): el SDK tarda segundos y el VPS es una vuelta de SSH. El panel se dibuja con las listas vacías y se completa solo.
4. Lo que es **catálogo** se cachea; lo que es **estado** no se cachea nunca. Los emuladores vivos se preguntan siempre.
5. La caché del VPS lleva el host en la clave: dos repos son casi siempre dos VPS.
6. Un fallo al consultar devuelve una lista vacía, no una excepción: un eje vacío ya se explica solo, y una excepción dejaría sin dibujar toda la pestaña.

## Consecuencias

- Un subproyecto nuevo aparece en los ejes sin tocar el catálogo.
- Un eje vacío necesita decir **dónde** miró: «no hay AVD en esta máquina» y «no hay servicio en este VPS» mandan a lugares distintos (`AxisDef.query_place`).
- Al reponer lo guardado hay que tolerar que un valor ya no exista (un AVD borrado): se ignora y queda el primero de la lista.

## Descartado

- **Enumerar los valores por proyecto en el catálogo.** Es la lista que había que mantener a mano en cada repo, que es justo lo que se estaba sacando.
- **Consultar en el hilo de la interfaz.** Congela la ventana cada vez que se abre la pestaña del emulador.
