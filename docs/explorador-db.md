# Explorador de base de datos

Plan para ver las tablas de la base de un repo desde Consola, al estilo de HeidiSQL pero **solo
lectura**: árbol de esquemas y tablas a la izquierda, datos y estructura a la derecha. Todo sale de
la introspección del catálogo de Postgres; no hay nada que configurar por tabla.

Reemplaza a PLAN.md §6 («fusión de Exploratore»), que se escribió antes de que existieran
`config.env`, `core/database.py`, las vistas de pestaña y los launchers. Lo que §6 decía y ya no
aplica está en §10.

## 1. Qué es y qué no

**Es:** mirar. Qué esquemas hay, qué tablas, cuántas filas, qué columnas con qué tipos, qué llaves
y a dónde apuntan, qué índices. Hojear los datos de una tabla, ordenarlos y seguir una llave foránea
hasta la fila a la que apunta.

**No es:** un cliente SQL. No hay editor de consultas, ni edición de celdas, ni DDL, ni exportar.
Escribir sobre la base ya tiene sus botones —con seguro— en el grupo Base de datos, y un segundo
camino de escritura sin seguro sería un agujero.

La lectura no es solo una promesa de la interfaz: la conexión se abre en modo read-only (§4), así
que un bug en la vista no puede escribir.

## 2. Lo que ya existe y se reusa

Medido en el repo antes de proponer:

| Pieza | Dónde | Cómo se usa aquí |
|---|---|---|
| Conexión por ámbito, con túnel si es remota | `core/database.py::connect` | Tal cual: da la URL a `127.0.0.1`, local o por túnel. Nunca a la IP pública. |
| Credenciales | `config.env`: `DB_USER` (vacío, el usuario de despliegue), `DB_PASSWORD`, `DB_NAME` (`db.credentials`) | Las mismas de todos los botones de Base de datos. Sin formulario ni contraseña pedida al conectar. |
| Eje `scope` local/remoto | `AxisDef('scope', …)` en `core/catalog.py` | El mismo eje, en el panel de parámetros. |
| Tarea viva que publica un endpoint | `kind='live'` + `ctx.serve()` + `session` | La conexión es una tarea viva: vive lo que vive la pestaña (§3). |
| Segunda vista de la pestaña | `ui/tab_view.py` (consola ⇄ navegador) | Su docstring ya reservaba el lugar: «la misma caja sirve para la pestaña de Base de datos». |
| Consultas de introspección | `exploratore/app/src/core/db/postgres_service.py` | Punto de partida, con dos correcciones (§5). |
| Driver | `psycopg` 3.3.4 instalado en el entorno | No estaba en `requirements.txt`; ahora sí (`psycopg[binary]>=3.2`). |

Motor: solo PostgreSQL. Los cinco repos hermanos con base (banditore, concordia, navetta, presenze,
vettore) declaran `DATABASE_URL=postgresql…`.

Script original para homologar: `scripts/database/inspect_db.py` (conectividad, versión, tablas del
esquema con conteo, tamaño de la base, muestra de filas). El explorador cubre todo eso y lo muestra
en una vista en vez de imprimirlo. `inspect_db` —el botón que lo imprime en la consola— sigue igual.

## 3. La capacidad

```python
Capability(id='explore_db', name='Explorar base', group='Base de datos', section='Conexión',
           kind='live', view='db', icon='🗂️',
           description='Navega esquemas, tablas y datos de la base, en solo lectura.',
           axes=[AxisDef('scope', ['local', 'remoto'], 'scope', labels=_SCOPE_LABELS)])
```

**`kind='live'`, no un `kind='view'` nuevo.** El comentario de `Capability.kind` menciona `'view'`,
pero nada lo registra ni lo maneja. Lo que el explorador necesita es exactamente lo que ya tiene un
launcher: una tarea que arranca, publica dónde está lo que entrega y sigue viva hasta que cierras la
pestaña. En remoto lo que se mantiene vivo es el túnel SSH; cerrar la pestaña cancela la tarea, y
`Connection.close()` mata el túnel. Nada queda colgado.

**Ejecutar es conectar.** Abrir la pestaña no conecta, igual que ningún botón corre al abrirse
(`MainWindow._on_action_requested`). Remoto abre un túnel, y eso es un efecto que se pide.

La tarea, en `core/tasks/database.py`:

```python
def explore_db(ctx, scope: str = db.LOCAL) -> None:
    with db.connect(ctx, scope) as conn:                  # abre el túnel si es remoto
        with db_explorer.open_readonly(conn.url) as probe:
            info = db_explorer.server_info(probe)         # falla temprano, con el rol de la app
            relaciones = db_explorer.list_relations(probe)
        ctx.info(...)                                     # lo mismo que imprimía inspect_db
        ctx.publish(db_explorer.session_key(conn.safe_url), conn.url)   # §4
        ctx.serve(conn.safe_url, key=f'explore_db:{scope}', label=info.database, web=False)
        while not ctx.wait_cancelled(1.0):                # vive hasta que se cierre la pestaña
            if conn.tunnel is not None and not conn.tunnel.alive:
                raise TaskError('El túnel SSH se cerró: vuelve a conectar.')
```

`ctx.serve` ya sondea el puerto por TCP (`ports.wait_until_serving`), así que el LED de la barra
pasa a verde cuando Postgres contesta, sin código nuevo. La URL publicada es `safe_url`: la barra
nunca muestra la contraseña.

Dos piezas nuevas en `TaskContext`: `publish(key, value)` deja un valor en la sesión del proyecto y
lo borra `release_endpoints` al terminar la tarea; `wait_cancelled(timeout)` duerme sobre el `Event`
de cancelación que ya existía.

Lo que se publica es la URL con contraseña, no el objeto `Connection`. La vista abre su propia
conexión (§4) y la encuentra con `session_key(safe_url)`: la URL enmascarada es lo único que ya
conocen los dos lados, porque es la que llega por `serve()`. La contraseña queda en memoria y nunca
pasa por la barra de la pestaña.

## 4. Capas

```
core/db_explorer.py     sin Qt. Funciones puras sobre una conexión psycopg.
ui/db_worker.py         un QThread dueño de la conexión; pedidos por señal, respuestas por señal.
ui/db_explorer_view.py  árbol + (Datos | Columnas | Índices | Constraints). Solo habla con el worker.
ui/tab_view.py          segunda vista de la pestaña, según capability.view: navegador o explorador.
```

### `core/db_explorer.py`

```python
def open_readonly(url) -> psycopg.Connection
def server_info(conn) -> ServerInfo                 # version(), base, usuario, tamaño, puerto
def list_relations(conn) -> list[Relation]          # todo el catálogo en una consulta
def describe(conn, relation) -> TableDetail          # columnas, constraints, índices, FKs de ida y vuelta
def fetch_rows(conn, detail, *, offset=0, limit=200,
               order_by=None, descending=False, where=None) -> Page
def count_exact(conn, relation, where=None) -> int   # solo a pedido: COUNT(*) puede tardar
```

Dataclasses: `Relation(schema, name, kind, estimate, size_bytes, comment, parent, readable)`,
`Column(name, type, base_type, nullable, default, identity, generated, comment, pk, fk)`,
`ForeignKey(name, columns, ref_schema, ref_table, ref_columns)`, `Constraint(name, kind, definition)`,
`Index(name, definition, unique, primary)`, `TableDetail(…, outgoing, incoming)`,
`Page(columns, rows, offset, has_more)`, `Filter(equals)`.

**Solo lectura de verdad**, garantizada por el servidor y no por la vista:
`options='-c default_transaction_read_only=on -c statement_timeout=15000'` al conectar. Probado: un
`CREATE TABLE` sobre esa conexión da `ReadOnlySqlTransaction`.

La conexión va en **`autocommit`**, y no en una transacción larga como decía la primera versión de
este plan. Una sesión que queda «idle in transaction» retiene los `AccessShareLock` de cada tabla que
miró. Entonces un `DROP TABLE` de Reconstruir DB, o una migración en otra pestaña, se quedaría
colgado hasta cerrar el explorador. Con autocommit, cada `SELECT` suelta sus locks al terminar.

`statement_timeout` evita que un `ORDER BY` sobre una tabla enorme sin índice congele la pestaña.

### `ui/db_worker.py`

psycopg no admite dos consultas a la vez sobre la misma conexión, y la interfaz no puede
esperar a la red. Un solo hilo es dueño de la conexión y atiende los pedidos en fila
(`relations`, `describe`, `rows`, `count`). Cada respuesta lleva el id del pedido, así que la vista
descarta las que llegan tarde: cambiaste de tabla antes de que terminara la anterior.

El worker abre su propia conexión con la URL que publicó la tarea
(`session.read(project, session_key(safe_url))`), porque una conexión psycopg no se puede pasar de un
hilo a otro. La tarea es dueña del túnel y el worker, de la sesión SQL. Si la conexión se cae, el
worker la reabre en el siguiente pedido. Detener no espera: cancela la consulta en curso
(`cancel_safe`), y el hilo sigue referenciado hasta salir, porque soltar un `QThread` que todavía
corre tumba la app.

## 5. Las consultas: `pg_catalog`, no `information_schema`

Exploratore usaba `information_schema` para columnas y llaves. Aquí se cambia, por tres motivos:

1. `information_schema` **solo muestra lo que el rol puede tocar**. El explorador conecta como el rol
   de la app, y una tabla sin `GRANT` desaparecería del árbol en silencio. `pg_class` las lista
   todas.
2. **Bug a no portar:** `list_columns` de Exploratore une `pg_statio_all_tables` solo por `relname`.
   Con dos esquemas que tengan una tabla del mismo nombre, los comentarios de columna se cruzan o
   se duplican.
3. `information_schema.constraint_column_usage` no conserva el orden de las columnas en una FK
   compuesta. `pg_constraint.conkey/confkey` sí.

`list_relations` trae todo el árbol de una sola vez:

```sql
SELECT n.nspname, c.relname, c.relkind, c.reltuples::bigint, pg_total_relation_size(c.oid),
       obj_description(c.oid, 'pg_class'), c.relispartition, p.relname AS parent
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_inherits i ON i.inhrelid = c.oid
LEFT JOIN pg_class p ON p.oid = i.inhparent
WHERE c.relkind IN ('r','p','v','m','f')
  AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY 1, 2;
```

El estimado es `reltuples`. Una tabla que nunca pasó por `ANALYZE` lo tiene en `-1`, y entonces
se usa `n_live_tup` de `pg_stat_all_tables`. Sin ese respaldo, las tablas recién migradas se veían
todas con «?».

Las **particiones** (`relispartition`) cuelgan de su tabla madre y no del esquema. En los repos con
tablas particionadas (`ensure_partitions`), listarlas planas llenaría el árbol de
`mensajes_2026_09`. `spatial_ref_sys` de PostGIS se muestra, pero atenuada, igual que las vistas (`◇`), las vistas
materializadas (`◈`) y las tablas foráneas (`⇢`). Una tabla sin `SELECT` para el rol sale en gris,
con el motivo en el tooltip.

`describe` usa `pg_attribute` + `format_type` (tipo con su modificador: `varchar(120)`,
`geometry(Point,4326)`), `pg_get_expr` para los defaults, `pg_constraint` + `pg_get_constraintdef`,
`pg_index` + `pg_get_indexdef`, y las FKs **entrantes** (`confrelid = esta tabla`). Las entrantes
responden «¿quién apunta a esta tabla?», que en un visor es tan útil como las salientes.

## 6. La vista

```
┌ Explorar base · local ─ ● concordia_db · listo ─ postgresql://concordia@127.0.0.1:5432/… ─ [Consola] ┐
│ [filtrar tablas…]           │  usuarios   public · tabla · ~12.408 filas · 3,1 MB        [Contar] │
│ ▾ public                    │  ┌ Datos ┬ Columnas ┬ Índices ┬ Constraints ┐                     │
│   ▸ mensajes   ~1,2M  (12)  │  │ id ▲ │ email          │ creado_en           │ empresa_id → │     │
│     usuarios   ~12k         │  │ 1    │ ana@…          │ 2026-01-04 10:22    │ 7 ↗          │     │
│     empresas   ~300         │  │ 2    │ luis@…         │ 2026-01-04 10:31    │ 7 ↗          │     │
│ ▸ auth                      │  │ …  (desplazar carga 200 más)                                │     │
│ ▸ vistas (3)                │  └─────────────────────────────────────────────────────────────┘     │
└─────────────────────────────┴───────────────────────────────────────────────────────────────────────┘
```

**Árbol.** Esquema → tablas, vistas, vistas materializadas y foráneas, cada una con su estimado de
filas (`reltuples`, gratis). Las particionadas muestran cuántas particiones tienen. El filtro de
arriba filtra en el cliente, porque el catálogo ya está en memoria. No hay selector de agrupación:
el árbol va por modelos (§7) en cuanto se leen, y por esquema mientras cargan o si no se pueden
importar.

El lado del árbol tiene un ancho mínimo (240 px) y el título de la derecha se recorta. Sin eso, en
la pestaña real —que comparte el ancho con el panel de parámetros— la cabecera de la derecha pedía
~780 px y el árbol se quedaba en 50: no se veía ninguna tabla.

**Datos.** Un `QTableView` sobre un `QAbstractTableModel` con `canFetchMore`/`fetchMore`: 200 filas
por página, `LIMIT/OFFSET`, y al llegar al fondo se cargan más. Clic en una cabecera ordena **en el
servidor** (`ORDER BY col, pk`); ordenar solo lo cargado mentiría. Orden por defecto: la PK. Una
vista sin PK queda sin ordenar.

Cada columna viaja **como texto convertido en el servidor** (`left(col::text, 2001)`), no con la
conversión del driver. La vista solo muestra, y el texto de Postgres es la forma canónica de
cualquier tipo —rangos, intervalos, enums, `numeric` de cuarenta dígitos— sin que psycopg tenga que
saber cargarlo. El corte evita que un `text` de megas viaje entero para mostrarse recortado.

Encima de eso, un trato por tipo. `NULL` se ve atenuado y en cursiva, distinto de la cadena vacía.
`json/jsonb` va en una línea en la celda y con sangría en el tooltip. `bytea` se trae como
`octet_length` y se muestra `‹bytea 1.2 KB›`, sin los bytes. `geometry/geography` va como
`ST_AsText(col)`. Los números se alinean a la derecha y el texto largo se ve completo en el tooltip.
La lista de columnas se arma desde `describe` y no con `SELECT *`: eso es lo que permite ese trato.

**Seguir una FK.** La cabecera de una columna con FK lleva `↗` (la PK lleva `🔑`), y sus celdas van
en el color de acento. **Doble clic** en una celda abre la tabla destino con
`WHERE destino_col = valor` y una miga de pan (`arrangement_intent › user id=b3ca…`) para volver.
Es doble y no simple porque con un clic simple no se podría seleccionar una celda sin salir de la
tabla. El valor va como literal sin tipo, así que Postgres lo infiere de la columna y usa el índice;
comparar `col::text = valor` recorrería la tabla entera. Es el único filtro de la fase 1, y es el que
más se usa al revisar datos relacionados.

Una tabla vacía lo dice («La tabla no tiene filas») en vez de mostrar solo las cabeceras, que se
confundía con una carga que no terminó.

**Columnas, Índices y Constraints.** Una pestaña cada uno, al lado de Datos. Columnas: nombre,
tipo, nulo, default, PK/FK/identity. Constraints lleva debajo «Referenciada por», con las FKs
entrantes (constraints de otras tablas hacia esta): doble clic abre la tabla que apunta.

**Túneles.** Limpiar vacía el log y, si la tarea de la pestaña tiene un túnel SSH vivo, la detiene:
el túnel es de la tarea y se cierra con ella. Cerrar Consola detiene todas las tareas; y cada `ssh`
del túnel va en un Job Object de Windows (`process.bind_to_app`), así que muere con Consola aunque
se cierre de golpe.

**Conteo exacto.** `~12.408` es el estimado. [Contar] corre `COUNT(*)` en el worker, con el timeout
de sesión, y reemplaza el número. No es un «recargar»: es otra pregunta.

**Refrescar al abrir.** Al volver a mostrar la pestaña (`TabPanel._activate` → `TabView.on_shown`)
se relee el catálogo (`list_relations`) y la estructura de la tabla abierta. Así, si migraste en
otra pestaña, lo ves. El árbol conserva la tabla elegida y los esquemas abiertos. Las filas que ya
mirabas se quedan si las columnas no cambiaron; si cambiaron, se piden de nuevo. No hay botón de
recargar.

**Sin conexión.** Antes de Ejecutar, o con la tarea caída, la vista explorador no se ofrece y la
pestaña queda en la consola, con el error del intento. Es lo mismo que hace `endpoint_down` con el
navegador.

## 7. Comparar con los modelos

La base se compara contra los modelos del repo abierto, y el árbol se agrupa como están
organizados en `app/models/`.

**Qué se compara: lo que ve Alembic.** `alembic/env.py` hace `from app.models import Base` en los
cinco repos, así que la fuente es `Base.metadata` y no los archivos leídos a mano. Los tipos salen
de `type_annotation_map`, de alias `Annotated` en `base.py` (`PkUuid`, `Money`) y de enums
`native_enum=False` cuyo largo solo se sabe ejecutando. Un parser daría diferencias que no existen.
Un modelo que no se importa en `app/models/__init__.py` (el `table_config.py` de concordia) tampoco
existe para las migraciones, y aquí tampoco.

**Cómo se lee.** `core/db_models.py::read_models` corre un programa corto con `-c` en el Python del
proyecto: el venv de `server/` o, si el repo no tiene (concordia), el Python del PATH. Es el mismo
mecanismo que los payloads de seeders y particiones. Devuelve por tabla: esquema, nombre, carpeta y
archivo del modelo (del `__module__` de su clase), y cada columna con el tipo compilado por el
dialecto de Postgres, nulo y PK. Tarda ~1,5 s. El worker lo guarda con la firma de los `.py` de
`app/models/` (ruta + mtime), así que al volver a la pestaña solo se relanza si tocaste un modelo.

Siempre son los modelos **de esta máquina**, también con ámbito remoto: la pregunta es «¿la base
del VPS está al día con lo que tengo en el repo?».

**La comparación** (`compare`) usa `list_relations` y una sola consulta de columnas de toda la base
(`all_columns`). Estados:

| Marca | Estado | Qué quiere decir |
|---|---|---|
| `✕` rojo | `missing` | Está en los modelos y no en la base: falta migrar. Sale en el árbol igual, en su lugar. |
| `≠` ámbar | `changed` | Columnas que faltan o sobran, o con otro tipo o nulabilidad. |
| `+` violeta | `unmodeled` | Está en la base y ningún modelo la declara. |
| — | `system` | `alembic_version` y las tablas de una extensión (`pg_depend` `deptype='e'`: `spatial_ref_sys`). No cuentan. |

Las particiones siguen a su tabla madre y las vistas no se comparan. Los tipos se normalizan antes
de comparar (`normalize_type`): `VARCHAR(7)` ≡ `character varying(7)`, `NUMERIC(14, 2)` ≡
`numeric(14,2)`. Probado contra concordia local (47 modelos, 0 diferencias) y vettore local
(29 tablas faltan, 4 difieren, todas reales).

**En la vista.** Debajo del filtro, el resumen: «47 modelos: ✕ 29 faltan en la base · ≠ 4
difieren», o «✓ Al día con los 47 modelos». Si los modelos no se pudieron importar, el motivo va
ahí y el árbol queda por esquema, sin comparar. En Columnas, una tabla `changed` abre con
«Diferencias con el modelo» (columna, en la base, en el modelo); una `missing` muestra las columnas
del modelo, porque no hay datos que pedir.

**Por modelos.** Carpetas de `app/models/` → tablas, con los modelos de la raíz después de las
carpetas, como en el disco, y al final «sin modelo» con lo que no declara ningún modelo. Las
carpetas no se guardan ni se configuran: salen del `__module__` de cada clase. Es la única
agrupación mientras haya modelos: ya incluye todas las tablas de la base, así que un selector
[Esquemas | Modelos] mostraba lo mismo dos veces.

No compara índices, FKs ni defaults: eso ya lo hace `alembic revision --autogenerate` (Generar
migración). Esto responde lo que se ve de un vistazo: qué tablas y columnas no coinciden.

## 8. Qué se toca

| Archivo | Cambio |
|---|---|
| `requirements.txt` | `psycopg[binary]>=3.2` |
| `core/db_explorer.py` | **nuevo** — §4 y §5 |
| `core/context.py` | `publish()`, `wait_cancelled()` |
| `core/settings.py` | `explore_db` en `_DB_REMOTE`: reclama `DB_NAME` y `DB_PASSWORD` como las demás de su grupo |
| `core/tasks/database.py` | `explore_db` + `registry.bind` |
| `core/catalog.py` | la `Capability` de §3 |
| `core/command_docs.py` | la entrada de `explore_db` |
| `core/registry.py` | quitar `'view'` del comentario de `kind`; documentar `view='db'` junto a `'web'` |
| `ui/db_worker.py` | **nuevo** |
| `ui/db_explorer_view.py` | **nuevo** — árbol, modelo de datos paginado, estructura |
| `core/db_models.py` | **nuevo** — leer los modelos del repo y compararlos con la base (§7) |
| `ui/tab_view.py` | segunda vista según `capability.view` (`VIEW_NAMES`); recibe el proyecto para leer la sesión; con `view='db'` esconde Copiar y Abrir ↗, que sobre una URL enmascarada no sirven |
| `ui/tab_panel.py` | `_activate` llama a `view.on_shown()`; `close_tab` llama a `view.shutdown()` antes de destruirla |
| `docs/PLAN.md` | §6 y las filas `db_connections`/`db_table_folders` de §8 apuntan aquí |

`import psycopg` es perezoso (`db_explorer._psycopg`): sin el paquete, la app arranca igual, la
capacidad sale en el menú y Ejecutar explica qué instalar.

## 9. Etapas

Las cuatro están hechas. Se probaron contra el Postgres 17 local: vettore con el rol de la app
(camino completo: tarea, pestaña, cierre) y concordia con datos (particiones, FKs, jsonb, bytea,
geography, 8.500 filas de `spatial_ref_sys` para paginar). **Falta probar el ámbito remoto por
túnel contra un VPS real.**

1. **Núcleo sin interfaz.** `core/db_explorer.py` más la tarea `explore_db` que solo imprime lo que
   imprimía `inspect_db`: versión, base, tamaño y tablas con estimado y tamaño. Se prueba contra la
   base local de concordia y contra la remota por túnel. Aquí se validan las consultas de §5
   (particiones, esquemas repetidos, tabla sin `GRANT`).
2. **Árbol + Estructura.** Worker, vista, tercera vista de `TabView`, refresco en `_activate`.
3. **Datos.** Modelo paginado, orden en servidor, formateo por tipo, Contar.
4. **Seguir FK** y miga de pan.

Cada etapa se puede usar sola: la 1 ya reemplaza la salida de `inspect_db` con más datos.

## 10. Lo que cambia respecto de PLAN.md §6

| §6 decía | Ahora | Por qué |
|---|---|---|
| Formulario de conexión, contraseña pedida al conectar | Credenciales de `config.env` | Ya están ahí, y todos los botones de Base de datos las usan. Un segundo lugar para la misma contraseña es cómo terminan desincronizadas. |
| Tablas `db_connections`/`db_table_folders` en un SQLite | Nada persistido | El SQLite de §8 no existe. La conexión se deduce del repo y el ámbito, así que no hay «conexiones» que guardar. |
| Carpetas para organizar tablas | Las carpetas de `app/models/` (§7) | No se arman a mano ni se guardan: salen del repo, que ya organiza los modelos así. |
| Consultas de lectura y escritura | Fuera | Pedido explícito: solo visualizar. |
| Asegurar que el servicio de fondo Túnel Postgres esté corriendo | La tarea abre su propio túnel | `ssh_tunnel` es un stub y `kind='background'` no tiene maquinaria en la interfaz. `generate_migration` ya abre el suyo con `db.connect`; el explorador hace lo mismo. |
| `core/db.py`, `core/models.py` | `core/db_explorer.py` | `core/database.py` ya existe y es el ciclo de vida. Explorar es otra cosa y va en su propio módulo. |

## 11. Pendiente, sin decidir

1. **Rol de la app o superusuario.** El plan conecta como el rol de la app, que es lo que la app ve
   de verdad. Una tabla sin `GRANT` aparece en el árbol (§5), pero sus datos darán «permission
   denied»: la vista lo dice en la tabla, no como error de la pestaña. Conectar como superusuario lo
   vería todo, pero en remoto el canal de superusuario es `psql` por SSH (`db.Admin`), no el driver.
2. **Varias bases por repo.** Hoy `DB_NAME` es una sola. Si un repo tiene dos, sería un eje más, y
   no hace falta decidirlo antes.
3. **Filtros por columna** (`WHERE` libre o por valor). Fuera de la fase 1. Si entran, van armados
   con `psycopg.sql.Identifier`/`Literal`, nunca con texto escrito por el usuario.
