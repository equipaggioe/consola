# ADR-0032 · Un clic en una acción abre su pestaña; ejecutar es un gesto aparte

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** ui/main_window.py, ui/tab_panel.py, ui/params_panel.py, ui/readiness.py

## Contexto

Casi todas las acciones tienen parámetros, y varias son destructivas. Si el clic del menú ejecutara, no habría ningún momento para mirar qué está marcado.

## Decisión

1. El clic en el menú o en el buscador **abre (o enfoca) la pestaña** de la acción. No ejecuta nada.
2. Ejecutar es apretar **Ejecutar** en el pie del panel, con los parámetros de esa pestaña a la vista.
3. El **▶** de cada fila del buscador es el atajo: abre la pestaña y corre de una, con los parámetros guardados para ese botón en ese repo — o los por defecto si nunca se tocaron.
4. El ▶ solo aparece en lo que **puede correr ya**: `readiness` mira exactamente lo que esos parámetros guardados van a correr, así que un paso apagado no reclama sus claves.
5. Si el buscador se equivocó y el panel bloquea, el motivo se escribe en la misma consola donde habría salido el resultado.
6. Las pestañas abiertas se reabren al arrancar, y **reabrirlas no corre nada**.

## Consecuencias

- Las dos formas de ejecutar pasan por el mismo punto, y ahí se aplica el seguro: ponerlo en el panel dejaría al ▶ sin red.
- `readiness` tiene que calcular lo mismo que el panel, con la misma selección, o el ▶ mentiría.

## Descartado

- **Que el clic ejecute.** No deja momento para mirar los parámetros, y con un destructivo es peor.
