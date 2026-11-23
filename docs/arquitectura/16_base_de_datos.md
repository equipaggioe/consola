# 16 · Base de datos

## 1. El eje `scope`

Cinco botones tienen el eje `local` / `remote`: «Levantar backend», «Correr seeders», «Correr mock seeders», «Explorar datos» y «Reconstruir base». La función corre siempre en Consola, y lo que cambia es contra qué base apunta ([ADR-0012](../adr/0012-el-eje-scope.md)). Contra el VPS, lo que cambia su base lo hace `database.py` de canone ([ADR-0082](../adr/0082-contra-el-vps-los-botones-de-base-corren-database-py.md)).

| Canal | Qué corre | Local | Remoto |
|---|---|---|---|
| `database.Connection` | La aplicación conectándose | `postgresql://…@127.0.0.1:<puerto local>` | «Explorar datos»: `<app>_read`, sin contraseña, por un túnel al socket del VPS (`db.connect_vps`). «Levantar backend»: `DB_USER` por un túnel al puerto (H8 del [30](30_riesgos_y_pendientes.md)) |
| `database.Admin` | SQL como superusuario | `psql` local por TCP con `PGPASSWORD` | — |
| `runner.Runner` | Programas Python del repo | El venv de `<SERVER_DIR>/.venv` | — |
| `database.py` de canone | Vaciar, migrar y sembrar | — | `/usr/local/sbin/<app>-database <comando>`, con `sudo` desde la cuenta que administra (`vps_setup.admin`) |

El canal de superusuario existe aparte porque crear un rol, crear una base o borrarlas necesitan permisos que el rol de la aplicación no tiene, y por eso pasa por `psql` y no por el driver.

«Configurar base de datos», «Correr migraciones», «Respaldar base de datos», «Restaurar base de datos», «Habilitar extensiones», «Reiniciar historial de migraciones» y «Borrar base y rol» no tienen el eje: actúan solo sobre la base local. En un VPS de canone la base, sus roles y sus extensiones los crea `install.py`, migra `deploy.py`, respalda la receptora ([ADR-0060](../adr/0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md)) y vacía `database.py`. Sus claves de base las exige la capacidad (`_DB_FIXED` de `services/settings.py`), porque no hay eje que las declare; las del superusuario, `_PG_FIXED`.

## 2. Nunca por la IP pública

`database.vps_tunnel` abre un `ssh -N -L` del puerto 5432 de esta máquina, o el siguiente libre, al socket `/run/postgresql/.s.PGSQL.5432` del VPS. El tráfico va siempre por `127.0.0.1`; la base del VPS no se expone ([ADR-0016](../adr/0016-siempre-por-tunel.md)).

Los roles de canone no tienen contraseña y entran por `peer`. Por el socket, PostgreSQL ve la cuenta con la que `sshd` abre el túnel —la que administra—, e `install.py` la deja entrar solo como `<app>_read`: lee lo que crea `<app>_owner`, salvo `event_log`, y no cambia nada. La base es `<app>`, no `DB_NAME`, que nombra la local. `<app>` sale del remoto `origin` (`canone.origin`).

El túnel vive lo que vive la tarea: `ctx.hold_tunnel` lo anota, `Connection.close` lo cierra y «Limpiar» detiene la tarea si tiene uno vivo. «Abrir túnel a Postgres» es el mismo mecanismo con botón propio, para conectarse con otra herramienta: informa el extremo local, el rol y la base.

«Levantar backend» con ámbito remoto sigue por `database.connect`: pregunta el puerto con `sudo -n` y entra con `DB_USER` y su contraseña (H8 del [30](30_riesgos_y_pendientes.md)).

En local, el puerto sale de leer `postgresql.conf` de la instalación más nueva —`C:\Program Files\PostgreSQL\<versión>\data` en Windows, `/etc/postgresql/<versión>/main` en Linux—: una máquina con varias versiones no siempre deja la buena en 5432, y el síntoma era un «no conecta» contra el puerto equivocado. `psql`, `pg_dump` y `pg_restore` salen de la misma versión más nueva, ordenada por número ([ADR-0048](../adr/0048-las-diferencias-de-sistema-viven-en-host.md)).

En Linux el canal de superusuario local entra por TCP igual que en Windows, así que `PG_PASSWORD` tiene que ser la contraseña real de `postgres`. Debian no le pone una al instalar: hay que dársela una vez (`sudo -u postgres psql -c '\password'`).

## 3. Dónde corre el código del repo

`services/runner.py` corre el código del repo —Alembic, los seeders, las particiones— en esta máquina, con el venv de `<SERVER_DIR>/.venv`, contra la base local. En el VPS ese código lo corren `deploy.py` y `database.py` de canone.

El programa viaja en la línea de comandos (`-m alembic …`, `-c <fuente>`) y `DATABASE_URL` va por el entorno, nunca escrita a un archivo.

«Restaurar» saca las extensiones de lo que restaura (`pg_restore -l` y `-L`): las crea el superusuario, y con `--clean` el rol de la aplicación intentaría borrarlas y cortaría.

En un repo de canone, el `Settings` del servidor no lee `DATABASE_URL`: `runner.local` escribe `credentials/migrate/` y corre con `CREDENTIALS_DIRECTORY` apuntando ahí, como el dueño del esquema ([ADR-0069](../adr/0069-un-repo-de-canone-corre-en-desarrollo-con-sus-credenciales.md), [ADR-0070](../adr/0070-las-credenciales-del-dueno-van-dentro-de-credentials.md)). «Levantar backend» usa `credentials/` y corta si el ámbito es remoto.

En un repo sin ese `Settings`, `runner.local` usa `runner.here`, que pasa la URL de `db.connect` por `DATABASE_URL`.

## 4. Los payloads

`services/tasks/payloads.py` es la excepción deliberada a «nada se ejecuta como script»: programas Python cortos que viajan por `-c` al intérprete del proyecto, porque necesitan importar `app.` y `seeders.` del repo administrado. Lo único que toman del entorno es el directorio de trabajo —de ahí sale el `sys.path`— y la base; las dos las pone el `Runner`.

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
| `rebuild_db` | La base existe. Vacía las tablas y vuelve a llenar. No toca el historial de migraciones. En el VPS, ver §6 |
| `teardown_db` | Borra la base local y el rol, por separado: borrar la base y dejar el rol es lo que se quiere antes de un bootstrap |

Las particiones van **entre** las migraciones y los seeders, y no es cosmético: `alembic revision --autogenerate` no las escribe, y sin ellas el primer INSERT de un seeder revienta con «no partition of relation found for row».

## 6. La base del VPS

Cada botón con ámbito remoto corre un comando de `database.py` (`canone.database_command`) desde la cuenta que administra, con `sudo -S` y la contraseña de `SUDO_PASSWORD` o pedida una vez por sesión, como `deploy.py`:

| Botón | Contra el VPS |
|---|---|
| «Reconstruir base» | Una casilla por paso: `empty` → `migrate` → `seed` → `seed --mock` |
| «Correr seeders» | `seed` |
| «Correr mock seeders» | `seed --mock` |

`empty` detiene el servidor, borra la base y `/var/lib/<app>/files/`, y la crea otra vez como `install.py`: vacía y sin migrar. `migrate` corre las migraciones y los seeders de la versión activa, en una transacción, y arranca el servidor; el `seed` siguiente corre los seeders otra vez, que son idempotentes.

Los pasos de «Reconstruir base» dependen del ámbito: `Step.scopes` deja «Borrar tablas» y «Crear particiones» solo en local, y «Vaciar la base y los archivos subidos» solo en el VPS. El panel oculta los del otro ámbito y no los corre (`Capability.kwargs_from`, `ParamsPanel.active_steps`), pero guarda sus casillas: volver al otro ámbito las deja como estaban. «Borrar tablas» pide `PG_SUPERUSER` y `PG_PASSWORD`, que el VPS no usa.

### Solo en desarrollo

`database.py empty` y `seed --mock` fallan en una máquina sin la marca `/etc/<app>/development`. La deja `install.py --development`, y Consola pasa esa bandera en «Configurar VPS» si el `README.md` del repo dice `Estado: en desarrollo` (`canone.state`, `canone.install_args`); sin ella, `install.py` borra la marca. Un README sin la línea `Estado:` corta: no se supone ningún estado.

Antes de llegar al VPS, «Reconstruir base» con «Vaciar» y «Correr mock seeders» cortan si el README dice `Estado: en producción` (`_in_development`). `seed` corre también en producción.

### Juntar las migraciones

No tiene botón. Se hace con los que hay:

1. «Reiniciar historial de migraciones», en local.
2. Commit, a mano.
3. «Publicar versión», sin el paso de desplegar.
4. «Reconstruir base» remota, solo con «Vaciar la base y los archivos subidos».
5. «Desplegar versión»: los heads cambiaron, así que `deploy.py` migra desde la base vacía, y corre los seeders.
6. «Correr mock seeders» remoto, si se quieren datos de ejemplo.

`empty` no migra: la versión activa todavía tiene el historial viejo, y migrarla dejaría en `alembic_version` una revisión que la nueva no conoce.

## 7. Extensiones

`CREATE EXTENSION` de una extensión *untrusted* —PostGIS es la que importa— exige superusuario, y Alembic corre como el rol de la aplicación: una migración que la pidiera moriría con «permission denied to create extension».

Cuáles se crean sale de `DB_EXTENSIONS`, declarada, no deducida. Ninguna fuente la tiene: `pg_available_extensions` dice lo que **se puede** crear (cientos con contrib), `pg_extension` lo que **ya está** creado, y las migraciones no la traen porque `--autogenerate` nunca escribe un `CREATE EXTENSION` — un modelo con columnas `Geometry` no deja rastro. Y una migración que sí lo declarara sería la que necesita la extensión ya creada para poder aplicarse ([ADR-0071](../adr/0071-las-extensiones-las-declara-el-repo-sin-valor-por-defecto.md)).

`DB_EXTENSIONS` no tiene valor por defecto: vacía no crea ninguna, y tampoco llega a `install.py` ni a los paquetes del VPS. Antes de crear cada una se mira `pg_available_extensions`, y la tarea corta si el sistema no la tiene ([ADR-0071](../adr/0071-las-extensiones-las-declara-el-repo-sin-valor-por-defecto.md)).

## 8. Migraciones

| Botón | Qué hace |
|---|---|
| `migrate_db` | Generar la revisión pendiente, aplicar, o las dos. Son casillas sueltas porque se piden sueltas: generar para revisar el diff antes de tocar nada; aplicar para poner al día una base atrasada |
| `reinit_migrations` | Vacía la base local, borra `alembic/versions/` y escribe la inicial. El VPS toma el historial nuevo como dice §6, «Juntar las migraciones» |

Vaciar la base es un paso **de** `reinit_migrations`, no una precondición que haya que recordar: el autogenerate compara contra la base viva, así que sobre una base con tablas la «inicial» sale vacía.

Generar corre siempre en esta máquina, contra la base local: deja un archivo que hay que revisar y comitear.

Los dos botones tienen `requires_repo='migrations'`: en un repo sin Alembic no están ([ADR-0007](../adr/0007-lo-inaplicable-desaparece.md)).

## 9. Respaldo y restauración

`backup_db` vuelca la base local a un archivo y `restore_db` carga uno de esos archivos de vuelta. Las dos corren `pg_dump`/`pg_restore` en esta máquina, contra la URL de `db.connect` ([ADR-0060](../adr/0060-crear-migrar-respaldar-y-restaurar-solo-en-local.md)).

| Decisión | Por qué |
|---|---|
| Se busca el binario de la versión más nueva instalada | Una máquina con 15 y 17 tiene que usar la de 17: la de 15 se niega a leer un servidor 17 |
| La versión se compara **antes** de volcar | El error de `pg_dump` es un «server version mismatch» crudo a mitad de la corrida; el mensaje propio nombra las dos versiones y la ruta del binario elegido |
| La contraseña va por `PGPASSWORD`, no en el argv | Un argv queda escrito en el log de la corrida. Por eso `Connection` expone `host` y `port` sueltos además de la URL |
| `restore_db` corre con `--clean --if-exists --no-owner --exit-on-error` | Restaura sobre la base existente sin tocar el rol ni la base, con el dueño de este repo, y corta en el primer error en vez de resumir al final |

### Dónde caen los archivos

`BACKUP_DIR` (por omisión `.backups`) y `BACKUP_KEEP` (por omisión `7`) son claves de `config.env`, no ejes: son datos que la tarea lee, no decisiones de la corrida ([ADR-0045](../adr/0045-la-carpeta-y-el-conteo-de-respaldos-son-configuracion.md)). Una ruta relativa cuelga de la raíz del repo; una absoluta se usa tal cual, que es como se sacan los volcados del árbol de trabajo. `BACKUP_KEEP` corta con error si no es un entero de 1 o más.

La rotación filtra por `<DB_NAME>-*.dump` y no por `*.dump`: desde que la carpeta puede ser compartida entre repos, un glob a secas borraría los respaldos de las otras bases.

### Elegir qué restaurar

El eje `dump` es un `pick` cuyos valores salen de mirar `BACKUP_DIR` (fuente `BACKUP_FILES`). No se cachea —es estado, no catálogo: una lista vieja ofrecería un dump que la rotación acaba de borrar— y va del más nuevo al más viejo, para que el preseleccionado sea el último respaldo. Es el único eje consultado que necesita la raíz del repo además de la configuración.

`restore_db` es destructiva y entra en el seguro por repositorio con el objetivo `db` ([14](14_seguro_de_destructivos.md)).

## 10. El explorador

Una tarea viva, como un launcher: sostiene la conexión —y en remoto el túnel— hasta que se cierre la pestaña, y lo que entrega no es su log sino la vista de árbol y datos ([ADR-0015](../adr/0015-explorador-de-solo-lectura.md)). Antes de publicarla prueba la conexión —en local con el rol de la aplicación, en el VPS como `<app>_read`— y deja en la consola lo que imprimía el script de inspección: servidor, base, usuario, tamaño y tablas con su conteo estimado.

| Decisión | Por qué |
|---|---|
| Solo lectura garantizada por el servidor | La sesión se abre en modo `read only`, no por disciplina de la vista |
| `autocommit`, no una transacción larga | Una sesión «idle in transaction» retiene los `AccessShareLock` de cada tabla que miró, y un `DROP TABLE` o una migración en otra pestaña se quedaría esperando |
| Todo sale de `pg_catalog` | `information_schema` solo muestra lo que el rol puede tocar: una tabla sin `GRANT`, como `event_log` para `<app>_read`, desaparecería del árbol en silencio |
| Las columnas se piden como texto | El texto de Postgres es la forma canónica de cualquier tipo —rangos, intervalos, enums, numeric de cuarenta dígitos— sin que el driver tenga que saber cargarlo |
| El orden es del servidor | Ordenar solo lo ya cargado mentiría. Sin columna elegida se ordena por la clave primaria, que además desempata |
| Las consultas corren en `DbWorker` | Una consulta lenta no congela el árbol; la vista pide páginas al desplazar y las filas entran cuando llegan |

La vista va en la sección «EXPLORADOR», debajo de la consola ([12](12_interfaz.md)). Entre el árbol y los datos hay una sola línea, la del separador, de 1 px. La cabecera de esa sección lleva la tabla abierta, su tipo, filas y tamaño, y «Contar», que pide el `COUNT(*)` exacto y solo aparece con una tabla abierta. Sobre los datos, una banda muestra la miga de pan al seguir una clave foránea y el estado de la consulta, y desaparece cuando no hay ninguno de los dos (`DbExplorerView._fit_head`).

La URL con contraseña que la vista necesita no viaja por la pantalla: la tarea la deja con `ctx.publish` bajo una clave derivada de la URL enmascarada, y se borra sola cuando la tarea termina.

`services/db_models.py` compara la base viva contra los modelos del repo. No parsea archivos: importa `app.models` con el Python del proyecto y devuelve JSON, porque los tipos salen de `type_annotation_map`, de alias `Annotated` y de enums cuyo largo solo se sabe ejecutando. Es lo mismo que compara Alembic.
