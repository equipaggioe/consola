# ADR-0037 · Sincronizar env iguala solo los valores de las claves que los dos archivos ya tienen

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/tasks/utils.py, core/catalog.py

## Contexto

Un repo tiene dos archivos de configuración con propósitos distintos: el de Consola (`.consola/config.env`), con lo que hace falta para alcanzar el VPS, y el de la aplicación (`<SERVER_DIR>/.env`), con lo que el servidor lee al arrancar. Hay claves que están en los dos —el rol y la base, el secreto del TURN, el token de Cloudflare— y tenerlas discrepando es un despliegue que apunta a un lado y una aplicación que apunta a otro.

## Decisión

1. Se copian **solo las claves que ya existen en los dos archivos**. Ninguna clave nace de esta acción.
2. No hay tabla de equivalencias: cada archivo sigue decidiendo qué datos le corresponden.
3. La dirección es un eje, y el modo **simulacro** es una casilla más: primero se ve qué cambiaría.
4. Se escribe clave por clave (`upsert_value`): el archivo destino conserva sus comentarios, su orden y todo lo que no se tocó.
5. El `.env` del servidor se ubica por `SERVER_DIR`, que es de donde lo saca todo lo demás: en un repo cuya carpeta se llama `backend/`, el archivo tiene que ser el mismo que lee el servicio.
6. Es destructiva, con objetivo `local`: escribe dentro de este repo, pisando valores.

## Consecuencias

- Sigue siendo la única escritura de Consola sobre el `.env` de la aplicación, y es explícita.
- Una clave que debería estar en los dos y solo está en uno no se propaga: hay que crearla a mano primero.

## Descartado

- **Volcar un archivo entero sobre el otro.** Dejaría `VPS_KEY_NAME` en el `.env` de la aplicación y `SECRET_KEY` en el de Consola.
- **Una tabla de equivalencias entre nombres.** Es una tercera declaración que mantener sincronizada con las otras dos.
