# ADR-0073 · El respaldo no se arranca desde «Control del servicio»

- **Estado:** Aceptada
- **Fecha:** 2026-11-02
- **Alcance:** core/vps.py, core/tasks/vps_server.py

## Contexto

El [ADR-0068](0068-el-eje-de-servicios-sale-de-las-unidades-de-canone.md) puso `backup` en el eje `service`. En canone, el respaldo lo pide la receptora con `backup-request`, que primero comprueba el túnel. `<app>-backup.service`, arrancada a mano, no lo comprueba, y sin túnel restic reintenta hasta las 4 h de `TimeoutStartSec`.

## Decisión

1. **«Control del servicio» corta con `start` sobre `backup`**, antes de entrar al VPS.
2. **También con `restart`**, que arranca la unidad igual.
3. **`backup` sigue en el eje:** su estado y su journal son lo que se lee cuando un respaldo falla.

## Consecuencias

- El respaldo se pide con «Pedir respaldo», cuando exista (plan de despliegue, fase 6). Hasta entonces, no hay forma de pedirlo desde Consola.

## Descartado

- **Sacar `backup` del eje.** Se pierde su journal en «Ver logs del servicio», que comparte el eje.
