# ADR-0015 · El explorador es de solo lectura, garantizado por el servidor, y vive como tarea viva

- **Estado:** Aceptada
- **Fecha:** 2026-09-21
- **Alcance:** core/db_explorer.py, core/tasks/database.py, ui/db_explorer_view.py

## Contexto

Mirar una base desde la misma herramienta que la administra es útil y peligroso: la misma ventana que muestra una tabla podría borrarla. Y una sesión abierta durante media hora, si es una transacción larga, bloquea a quien intente migrar desde otra pestaña.

## Decisión

1. La conexión se abre con `default_transaction_read_only=on` y un `statement_timeout`: **lo garantiza el servidor**, no la disciplina de la vista.
2. `autocommit`, no una transacción larga: una sesión «idle in transaction» retiene los `AccessShareLock` de cada tabla que miró, y un `DROP TABLE` o una migración en otra pestaña se quedaría esperando.
3. Todo sale de **`pg_catalog`**, no de `information_schema`: esta última solo muestra lo que el rol puede tocar, y el explorador conecta como el rol de la aplicación — una tabla sin `GRANT` desaparecería del árbol en silencio.
4. Es una **tarea viva**, como un launcher: sostiene la conexión —y en remoto el túnel— hasta que se cierre la pestaña, y lo que entrega es la vista (`view='db'`), no su log.
5. Las columnas se piden **como texto**, convertidas en el servidor: es la forma canónica de cualquier tipo sin que el driver tenga que saber cargarlo.
6. El orden lo hace el servidor. Sin columna elegida se ordena por la clave primaria, que además desempata.
7. Las consultas corren en un hilo propio (`DbWorker`).

## Consecuencias

- Una tabla sin `GRANT` aparece en el árbol y sus datos dan «permission denied»: la vista lo dice en la tabla, no como error de la pestaña.
- La URL con contraseña no viaja por la pantalla: la tarea la deja en la sesión y se borra sola al terminar.
- Si el túnel se cae, la tarea corta con un mensaje en vez de quedarse mostrando datos viejos.

## Descartado

- **Conectar como superusuario.** Vería todo, pero en remoto ese canal es `psql` por SSH y no el driver.
- **Filtros `WHERE` escritos a mano.** Fuera de alcance; si entran, se arman con los constructores de `psycopg`, nunca con texto del usuario.
