# ADR-0012 · El ámbito local/remoto cambia contra qué base se apunta, no dónde corre el script

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/database.py, core/runner.py, core/catalog.py

## Contexto

Los scripts de base de datos compartían un `RUN_REMOTE` que **reenviaba el script entero** al VPS por SSH. Eso obliga a que el otro lado tenga el script, deja la salida a merced del reenvío y convierte cada operación en dos programas distintos según el flag.

## Decisión

1. `scope` es un eje de una docena de botones, con valores `local` y `remoto`, y lo que cambia es **contra qué base** se trabaja.
2. Hay tres canales, con el mismo reparto: `Connection` (la aplicación, por el driver), `Admin` (superusuario, por `psql`) y `Runner` (programas Python del proyecto).
3. El ámbito declara sus propias claves (`AxisDef.requires_env`): `remoto` pide además las del VPS. Exigirlas en la capacidad dejaba en ámbar la base local de un repo sin VPS.
4. Lo que **solo toca la base** corre del lado de la base: con `remoto`, en el VPS, con el intérprete que el despliegue ya dejó y sin túnel.
5. Nada se copia al otro lado: el programa viaja en la línea de comandos y `DATABASE_URL` por el entorno.

## Consecuencias

- Reconstruir la base del VPS ya no muere buscando un `python.exe` local en una máquina que solo opera el servidor.
- `Runner` y `Admin` son hermanos y hay que mantener los dos repartos coherentes.
- Un botón sin eje `scope` lo está diciendo: `backup_db` vuelca la base **del VPS** y no es una omisión.

## Descartado

- **Reenviar el script al VPS.** Exige que el otro lado tenga el código de Consola y vuelve a partir cada operación en dos.
