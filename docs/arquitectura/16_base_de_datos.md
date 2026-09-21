# 16 · Base de datos

## 1. El eje `scope`

Una docena de botones tienen el eje `local` / `remoto`. No significa «corré este script allá», como hacía el `RUN_REMOTE` de los scripts: la función corre siempre en Consola y lo que cambia es contra qué base apunta, y con qué intérprete ([ADR-0012](../adr/0012-el-eje-scope.md)).

Hay dos canales, hermanos y con el mismo reparto:

| Canal | Qué corre | Local | Remoto |
|---|---|---|---|
| `database.Connection` | La aplicación conectándose | `postgresql://…@127.0.0.1:<puerto local>` | Igual, a través de un túnel SSH |
| `database.Admin` | SQL como superusuario | `psql.exe` con `PGPASSWORD` | `sudo -u postgres psql` por SSH |
| `runner.Runner` | Programas Python del repo | El venv de `<SERVER_DIR>/.venv` | El venv del repo desplegado, por SSH |

El canal de superusuario existe aparte porque crear un rol, crear una base o borrarlas necesitan permisos que el rol de la aplicación no tiene, y por eso pasa por `psql` y no por el driver.

## 2. Nunca por la IP pública

Con ámbito remoto, `database.connect` pregunta el puerto real de Postgres al propio VPS, elige un puerto local libre y abre un `ssh -N -L`. El tráfico va siempre por `127.0.0.1`; la base del VPS no se expone ([ADR-0016](../adr/0016-siempre-por-tunel.md)).

El túnel vive lo que vive la tarea: `ctx.hold_tunnel` lo anota, `Connection.close` lo cierra y «Limpiar» detiene la tarea si tiene uno vivo. `Túnel Postgres` es el mismo mecanismo con botón propio, para conectarse con otra herramienta.

Cuando el proceso corre **del otro lado** el túnel sobra, y su puerto local no significaría nada allá: `database.vps_url` arma la URL como la ve el VPS.

En local, el puerto sale de leer `postgresql.conf` de la instalación más nueva bajo `C:\Program Files\PostgreSQL`: una máquina con varias versiones no siempre deja la buena en 5432, y el síntoma era un «no conecta» contra el puerto equivocado.

## 3. Dónde corre el código del repo

`core/runner.py` es la mitad que faltaba del eje. Lo que solo toca la base —aplicar migraciones, sembrar, asegurar particiones— corre **del lado de la base**: con ámbito remoto, en el VPS, sin túnel y con el intérprete que `publish_code` ya dejó instalado. Reconstruir la base del VPS borraba las tablas por SSH y después moría buscando un `python.exe` local que en un equipo que solo opera el servidor no tiene por qué existir.

No se copia nada al otro lado: el programa viaja en la línea de comandos (`-m alembic …`, `-c <fuente>`) y `DATABASE_URL` va por el entorno, nunca escrita a un archivo.

La excepción es `runner.here`, que corre siempre acá: lo usa lo que además de tocar la base **escribe en el repo abierto** ([ADR-0013](../adr/0013-generar-en-local-aplicar-donde-este-la-base.md)).

## 4. Los payloads

`core/tasks/payloads.py` es la excepción deliberada a «nada se ejecuta como script»: programas Python cortos que viajan por `-c` al intérprete del proyecto, porque necesitan importar `app.` y `seeders.` del repo administrado. Lo único que toman del entorno es el directorio de trabajo —de ahí sale el `sys.path`— y `DATABASE_URL`; las dos las pone el `Runner`, y por eso el mismo texto sirve igual acá y en el VPS.

El log muestra un resumen y no el argv real: `-c` lleva el programa entero como un solo argumento.

## 5. Ciclo de vida del esquema

| Atómica | Qué hace |
|---|---|
| `create_role` | Crea el rol si falta y le fija la contraseña |
| `create_database` | Crea la base con el rol como dueño; si existe, solo le cambia el dueño |
| `grant_privileges` | Permisos sobre la base y sobre el esquema `public` |
| `enable_extensions` | Las de `DB_EXTENSIONS`, como superusuario |
| `drop_tables` | Vacía `public`, respetando `spatial_ref_sys` |
| `drop_database` | Corta las conexiones vivas y borra la base |
| `drop_role` | Borra el rol |

Las tres compuestas se arman sobre eso y comparten `populate_db` (migrar → particiones → seeders), que no tiene botón propio: lo que se elige en el menú es por cuál de los dos caminos se llega —crear de cero o reconstruir—, y «llenar una base que ya está ahí» no es una intención que alguien tenga suelta.

| Compuesta | Punto de partida |
|---|---|
| `bootstrap_db` | No hay nada. Crea el continente y lo llena. Termina en una base **usable**, no en un esquema vacío |
| `rebuild_db` | La base existe. Vacía las tablas y vuelve a llenar. No toca el historial de migraciones |
| `teardown_db` | Borra la base y el rol, por separado: borrar la base y dejar el rol es lo que se quiere antes de un bootstrap |

Las particiones van **entre** las migraciones y los seeders, y no es cosmético: `alembic revision --autogenerate` no las escribe, y sin ellas el primer INSERT de un seeder revienta con «no partition of relation found for row».

## 6. Extensiones

`CREATE EXTENSION` de una extensión *untrusted* —PostGIS es la que importa— exige superusuario, y Alembic corre como el rol de la aplicación: una migración que la pidiera moriría con «permission denied to create extension».

Cuáles se crean sale de `DB_EXTENSIONS`, declarada, no deducida. Ninguna fuente la tiene: `pg_available_extensions` dice lo que **se puede** crear (cientos con contrib), `pg_extension` lo que **ya está** creado, y las migraciones no la traen porque `--autogenerate` nunca escribe un `CREATE EXTENSION` — un modelo con columnas `Geometry` no deja rastro. Y una migración que sí lo declarara sería la que necesita la extensión ya creada para poder aplicarse ([ADR-0014](../adr/0014-extensiones-declaradas.md)).

Antes de crear cada una se mira `pg_available_extensions`: no todo VPS tiene el paquete de sistema, y sin ese chequeo el bootstrap entero fallaba en vez de avisar y seguir.

## 7. Migraciones

| Botón | Qué hace |
|---|---|
| `migrate_db` | Generar la revisión pendiente, aplicar, o las dos. Son casillas sueltas porque se piden sueltas: generar para revisar el diff antes de tocar nada; aplicar para poner al día una base atrasada |
| `reinit_migrations` | Vacía la base, borra `alembic/versions/` y escribe la inicial |

Vaciar la base es un paso **de** `reinit_migrations`, no una precondición que haya que recordar: el autogenerate compara contra la base viva, así que sobre una base con tablas la «inicial» sale vacía.

Generar corre siempre en esta máquina, aunque el ámbito sea remoto: deja un archivo que hay que revisar y comitear, y generado en el VPS caería en el repo desplegado, donde el `reset --hard` del próximo despliegue se lo lleva puesto. La base remota la alcanza por el túnel, como cualquier otro proceso local.

Los dos botones tienen `requires_repo='migrations'`: en un repo sin Alembic no están ([ADR-0007](../adr/0007-lo-inaplicable-desaparece.md)).

## 8. Respaldo

`backup_db` no tiene eje `scope`, y no es una omisión: vuelca la base **del VPS** a un archivo local. Corre `pg_dump -Fc` allá, baja el archivo a `<repo>/.backups/`, borra el temporal remoto y rota los respaldos viejos (7 por defecto).

## 9. El explorador

Una tarea viva, como un launcher: sostiene la conexión —y en remoto el túnel— hasta que se cierre la pestaña, y lo que entrega no es su log sino la vista de árbol y datos ([ADR-0015](../adr/0015-explorador-de-solo-lectura.md)). Antes de publicarla prueba la conexión con el rol de la aplicación y deja en la consola lo que imprimía el script de inspección: servidor, base, usuario, tamaño y tablas con su conteo estimado.

| Decisión | Por qué |
|---|---|
| Solo lectura garantizada por el servidor | La sesión se abre en modo `read only`, no por disciplina de la vista |
| `autocommit`, no una transacción larga | Una sesión «idle in transaction» retiene los `AccessShareLock` de cada tabla que miró, y un `DROP TABLE` o una migración en otra pestaña se quedaría esperando |
| Todo sale de `pg_catalog` | `information_schema` solo muestra lo que el rol puede tocar, y el explorador conecta como el rol de la aplicación: una tabla sin `GRANT` desaparecería del árbol en silencio |
| Las columnas se piden como texto | El texto de Postgres es la forma canónica de cualquier tipo —rangos, intervalos, enums, numeric de cuarenta dígitos— sin que el driver tenga que saber cargarlo |
| El orden es del servidor | Ordenar solo lo ya cargado mentiría. Sin columna elegida se ordena por la clave primaria, que además desempata |
| Las consultas corren en `DbWorker` | Una consulta lenta no congela el árbol; la vista pide páginas al desplazar y las filas entran cuando llegan |

La URL con contraseña que la vista necesita no viaja por la pantalla: la tarea la deja con `ctx.publish` bajo una clave derivada de la URL enmascarada, y se borra sola cuando la tarea termina.

`core/db_models.py` compara la base viva contra los modelos del repo. No parsea archivos: importa `app.models` con el Python del proyecto y devuelve JSON, porque los tipos salen de `type_annotation_map`, de alias `Annotated` y de enums cuyo largo solo se sabe ejecutando. Es lo mismo que compara Alembic.
