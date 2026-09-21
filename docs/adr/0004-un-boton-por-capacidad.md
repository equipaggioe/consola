# ADR-0004 · Una variación que solo cambia una constante es un eje del panel, no otro botón

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/catalog.py, ui/params_panel.py

## Contexto

Varios scripts eran el mismo flujo repetido con una constante distinta: tres emuladores, tres SPA, tres modos de instalación de paquetes, nueve acciones de systemd. Un botón por script duplica la interfaz en vez de exponer la variación, y obliga a mantener N copias del mismo flujo.

## Decisión

1. Lo que varía entre dos corridas del mismo flujo es un **eje**, y la capacidad es una sola.
2. `select='many'` cuando pedir dos valores a la vez es legítimo (panel + backoffice); `select='one'` cuando es un absurdo (start + stop). El control lo dice: casillas o segmentado.
3. Los pasos de una compuesta son **casillas del mismo formulario**, no botones sueltos, cuando la operación casi siempre se pide entera (`clean_vps`, `bootstrap_db`).
4. Un paso se separa en botón propio cuando **tiene sentido re-ejecutarlo solo**, sin repetir el resto: «solo recopiar los certificados», «solo volver a correr los seeders mock».
5. Un paso con catálogo propio de opciones ya no entra en una casilla: ahí se vuelve botón aunque nadie lo pida suelto (los tres del emulador).

## Consecuencias

- El catálogo se cuenta en capacidades, no en botones: cuántos controles produce cada una depende de sus ejes y del repo abierto.
- La decisión de partir o no partir se toma dos veces —al declarar y al implementar— y tiene que dar lo mismo.

## Descartado

- **Un botón por script.** Duplicaba interfaz y escondía los pasos que se piden sueltos.
- **Un eje `preset` para los emuladores.** Las tres constantes escondían dos catálogos reales del SDK: habría sido una amputación, no una simplificación.
