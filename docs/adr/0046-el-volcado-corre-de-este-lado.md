# ADR-0046 · El volcado y la restauración corren de este lado y alcanzan la base remota por el túnel

- **Estado:** Reemplazada por [ADR-0060](0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md)
- **Fecha:** 2026-09-23
- **Alcance:** core/database.py, core/tasks/database.py, core/catalog.py, core/settings.py

## Contexto

`backup_database` estaba escrita contra SSH de punta a punta: resolvía el `Remote`, comprobaba que el VPS tuviera `pg_dump`, volcaba a `/tmp`, bajaba el archivo por `scp` y borraba el temporal. El catálogo no le daba eje `scope` y eso estaba documentado como deliberado: era lo que la función hacía.

La consecuencia era que **la base local no se podía respaldar**. Todos los demás botones del grupo tienen el eje; este no, por una razón de implementación que se había vuelto una propiedad del producto.

`db.connect(ctx, scope)` ya devuelve, en los dos ámbitos, una URL que apunta a `127.0.0.1` —en remoto abriendo el túnel SSH—, y `generate_migration` ya usaba ese camino: corre en esta máquina y alcanza la base remota por el túnel.

## Decisión

1. **`pg_dump` y `pg_restore` corren en esta máquina en los dos ámbitos**, contra la URL que da `db.connect`. Desaparecen el archivo en `/tmp` del VPS, el `scp` y la limpieza del temporal en cada camino de error.
2. **`backup_db` gana el eje `scope`**, que ahí significa lo mismo que en el resto del grupo: cuál de las dos bases se toca.
3. **Las herramientas se buscan como ya se buscaba `psql`.** `_windows_psql` se generaliza a `db.pg_tool(name)`, que recorre las versiones instaladas de la más nueva a la más vieja: una máquina con 15 y 17 tiene que usar la de 17, porque la de 15 se niega a leer un servidor 17.
4. **La incompatibilidad de versión se comprueba antes de volcar**, comparando `<tool> --version` contra `version()` del servidor, y corta con un mensaje que nombra las dos versiones y la ruta del binario elegido. Dejarlo para `pg_dump` da un «server version mismatch» crudo a mitad de la corrida.
5. **La contraseña no va en el argv.** Las dos herramientas reciben `-h/-p/-U` y la contraseña por `PGPASSWORD`, igual que el canal de superusuario: un argv queda escrito en el log de la corrida. Por eso `Connection` expone `host` y `port` sueltos además de la URL.
6. **`backup_db` sale de `_DB_REMOTE` en `core/settings.py`.** Las claves de la base ahora las declara el eje, que es quien sabe cuáles hacen falta en cada ámbito; exigirlas desde la capacidad las pedía también para el ámbito local, y con ellas `VPS_USER`.

## Consecuencias

- **Respaldar el VPS ahora exige tener las herramientas cliente de PostgreSQL en esta máquina.** Antes no hacía falta ninguna: todo pasaba del otro lado. Quien respalde sin tener PostgreSQL instalado acá no puede hasta instalarlo. El ámbito `local` ya lo exigía para el canal de superusuario, así que lo que se agrega es el requisito en `remoto`.
- El binario tiene que ser de versión igual o mayor que la del servidor. Es una restricción nueva, y la decisión 4 existe para que se lea como tal y no como una falla.
- Restaurar sale simétrico: el dump no se sube al VPS ni necesita espacio en `/tmp` allá.
- El volcado ya no pasa por el disco del servidor, así que un VPS con `/tmp` chico deja de ser un límite para el tamaño de la base.

## Descartado

- **Dos caminos, uno por ámbito**: dejar `remoto` exactamente como estaba y agregar un `local` aparte. No exige nada nuevo en esta máquina para el camino que ya funcionaba, pero deja dos implementaciones de lo mismo en una función y obliga a que la restauración remota suba el dump por `scp` y corra `pg_restore` del otro lado, con su propio temporal que limpiar.
- **Reenviar la tarea entera al VPS por SSH**, como hacía `RUN_REMOTE` en los scripts viejos. Es lo que el eje `scope` reemplazó: acá la función corre siempre en la aplicación y lo único que cambia es contra qué base apunta.
