# ADR-0088 · «Actualizar Cloudflare» apunta el host de cada pieza web de la app, sin el proxy

- **Estado:** Propuesta
- **Fecha:** 2026-11-14
- **Alcance:** `core/tasks/utils.py`, `core/canone.py`, `core/settings.py`

## Contexto

Canone sirve cada pieza web en su host —la landing en `<dominio>`, la web en `app.<dominio>` y el
panel en `panel.<dominio>`— y pide que cada uno apunte a la máquina antes de `install.py`
(`despliegue.md` de canone, «Caddy» y «Máquina»). «Actualizar Cloudflare» cambiaba un solo
registro, `CF_RECORD_NAME`, fallaba si no existía y lo dejaba con el proxy de Cloudflare. Al
instalar concordia el 2026-11-14 hubo que crear dos registros y quitar el proxy del tercero a mano.

## Decisión

1. **Los hosts salen del repo**: `canone.hosts` da `DOMAIN` si hay `landing/`, `app.DOMAIN` si hay
   `web/` y `panel.DOMAIN` si hay `panel/`. `CF_RECORD_NAME` desaparece.
2. **Cada registro A queda en la IP sin proxy**: se crea si falta, se cambia si apunta a otra IP o
   tiene el proxy, y si ya está bien no se escribe.
3. `CF_DOMAIN_NAME` sigue siendo la zona de Cloudflare, que puede ser un dominio padre de `DOMAIN`.

## Consecuencias

- Sin el proxy, Caddy obtiene cada certificado por ACME y el servidor ve la IP del cliente, que
  cuentan los límites por IP.
- Un repo sin `landing/`, `web/` ni `panel/` no tiene qué apuntar, y la tarea corta.

## Descartado

- **Un eje para el proxy.** Ninguna máquina de canone va detrás del proxy de Cloudflare.
- **Seguir con `CF_RECORD_NAME` y un registro por botón.** Tres corridas con tres valores distintos
  para lo que el repo ya dice.
