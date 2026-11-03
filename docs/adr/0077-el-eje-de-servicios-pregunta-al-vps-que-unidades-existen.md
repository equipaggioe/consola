# ADR-0077 · El eje de servicios le pregunta al VPS qué unidades existen

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/vps.py, core/catalog.py, core/tasks/vps_server.py

## Contexto

El [ADR-0023](0023-los-servicios-son-un-eje.md) fijó tres valores y un cierre común, `bring_up_service`, para los botones que configuraban servicios. Esos botones salieron con el [ADR-0059](0059-desplegar-con-los-programas-de-canone.md), y los valores los fija ahora el [ADR-0068](0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md). Este ADR reemplaza al 0023 y conserva lo demás.

## Decisión

1. **`service` es un eje de `systemd_action` y de `view_logs`** (del ADR-0023).
2. **Sus valores no se enumeran:** salen de preguntarle al VPS de ese repo cuáles existen, en una sola consulta, cacheada por host (del ADR-0023).
3. **`daemon-reload` es una acción del eje que no toma nombre de unidad** (del ADR-0023).

## Consecuencias

- Reiniciar otra unidad no pide un botón nuevo, sino sumarla al eje.

## Descartado

- **Un botón por servicio** (del ADR-0023). Es la misma función con una constante distinta.
