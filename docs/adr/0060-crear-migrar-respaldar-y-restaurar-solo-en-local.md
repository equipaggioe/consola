# ADR-0060 · Crear, migrar, respaldar y restaurar actúan solo sobre la base local

- **Estado:** Aceptada
- **Fecha:** 2026-10-31
- **Alcance:** core/tasks/database.py, core/catalog.py, core/settings.py, core/protection.py

## Contexto

El [ADR-0046](0046-el-volcado-corre-de-este-lado.md) hizo que `pg_dump` y `pg_restore` corrieran en esta máquina en los dos ámbitos y alcanzaran la base del VPS por el túnel. «Configurar base de datos» y «Correr migraciones» tenían el mismo eje `scope`.

En un VPS instalado con canone, la base y sus dos roles los crea `install.py`, migra `deploy.py` con el rol dueño del esquema, y el respaldo lo pide una receptora (ADR-0078, 0083 y 0085 de canone). Los roles no tienen contraseña y entran por `peer`, así que un túnel al 5432 no tendría con qué autenticarse *(sin confirmar)*.

## Decisión

1. **`bootstrap_db`, `migrate_db`, `backup_db` y `restore_db` actúan solo sobre la base local** y no tienen eje `scope`.
2. **Sus claves de base las exige la capacidad** (`DB_USER`, `DB_NAME`, `DB_PASSWORD`, en `core/settings.py::_DB_FIXED`), porque ya no hay eje que las declare por ámbito.
3. **`restore_db` toca solo el objetivo `db`** del seguro.
4. **`pg_dump` y `pg_restore` corren en esta máquina**, contra la URL de `db.connect` (del ADR-0046).
5. **Las herramientas se buscan de la versión más nueva a la más vieja** (`db.pg_tool`): la de una versión anterior se niega a leer un servidor más nuevo (del ADR-0046).
6. **La incompatibilidad de versión se comprueba antes de volcar**, nombrando las dos versiones y la ruta del binario (del ADR-0046).
7. **La contraseña no va en el argv**: va por `PGPASSWORD` (del ADR-0046).

## Consecuencias

- La base del VPS se respalda con la receptora de canone y se restaura con el programa que canone todavía no trae.
- Los demás botones de base conservan el eje `scope` con su valor remoto: «Reconstruir base», «Borrar base y rol», «Reiniciar historial de migraciones», los seeders, «Habilitar extensiones» y «Explorar datos». Contra un VPS de canone fallarían por lo mismo que los cuatro de arriba *(sin confirmar)*; qué pasa con ellos no está decidido.
- Los parámetros guardados del eje `scope` de los cuatro botones quedan en `params.json` sin que nadie los lea.

## Descartado

- **Dejar el ámbito remoto en los cuatro.** Contra un VPS de canone no se autentican, y crear o migrar la base del VPS es de `install.py` y `deploy.py`.
- **Dos caminos por ámbito, uno por SSH y otro local** (del ADR-0046). Dos implementaciones de lo mismo en una función.
