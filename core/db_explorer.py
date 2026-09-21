from __future__ import annotations
from dataclasses import dataclass, field

from .errors import TaskError

"""
Introspeccion de solo lectura de una base Postgres (ADR-0015).

Sin Qt: funciones sobre una conexion psycopg, que la vista llama desde su hilo
(`ui/db_worker.py`) y la tarea `explore_db` desde el suyo.

Todo sale de `pg_catalog`, no de `information_schema`: esta ultima solo muestra
lo que el rol puede tocar, y el explorador conecta como el rol de la app — una
tabla sin GRANT desapareceria del arbol en silencio (§5).
"""

STATEMENT_TIMEOUT_MS = 15000
PAGE_SIZE = 200
# Una celda trae como mucho esto: un `text` de megas no viaja entero para
# mostrarse cortado. Un caracter de mas avisa que hubo recorte.
CELL_CHARS = 2000

# Tipos que no se leen como texto: la geometria llega como EWKB hexadecimal y
# un bytea como su volcado entero. Se traen convertidos desde el servidor.
GEOMETRY_TYPES = ('geometry', 'geography')
BYTEA = 'bytea'

# La URL con contrasena no viaja por la barra de la pestana (esa muestra la
# enmascarada): la tarea la deja en la sesion con esta clave y la vista la lee.
_SESSION_PREFIX = 'explore_db:url:'


def session_key(safe_url: str) -> str:
    return _SESSION_PREFIX + safe_url


KIND_LABELS = {
    'r': 'tabla', 'p': 'tabla particionada', 'v': 'vista',
    'm': 'vista materializada', 'f': 'tabla foránea',
}


@dataclass
class ServerInfo:
    version: str
    database: str
    user: str
    size_bytes: int
    port: int


@dataclass
class Relation:
    schema: str
    name: str
    kind: str              # relkind: r p v m f
    estimate: int | None   # reltuples; sin ANALYZE todavia, las filas vivas que
                           # cuenta el colector. None en una vista.
    size_bytes: int
    comment: str | None
    parent: str | None     # tabla madre, si es una particion
    readable: bool         # el rol tiene SELECT
    extension: bool = False   # la creo una extension (spatial_ref_sys de PostGIS)

    @property
    def qualified(self) -> str:
        return f'{self.schema}.{self.name}'

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Column:
    name: str
    type: str              # con modificador: varchar(120), geometry(Point,4326)
    base_type: str         # typname: int4, jsonb, geometry
    nullable: bool
    default: str | None
    identity: str          # '' | 'a' (ALWAYS) | 'd' (BY DEFAULT)
    generated: str         # '' | 's' (STORED)
    comment: str | None
    pk: bool = False
    fk: 'ForeignKey | None' = None   # solo si la FK es de esta unica columna


@dataclass
class ForeignKey:
    name: str
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]


@dataclass
class Constraint:
    name: str
    kind: str              # contype: p u f c x
    definition: str


@dataclass
class Index:
    name: str
    definition: str
    unique: bool
    primary: bool


@dataclass
class TableDetail:
    relation: Relation
    columns: list[Column]
    constraints: list[Constraint]
    indexes: list[Index]
    outgoing: list[ForeignKey]
    incoming: list[ForeignKey]   # quien apunta a esta tabla: columns = las de la otra

    @property
    def primary_key(self) -> list[str]:
        return [c.name for c in self.columns if c.pk]


@dataclass
class Page:
    columns: list[str]
    rows: list[tuple]
    offset: int
    has_more: bool


@dataclass
class Filter:
    """Igualdades por columna, en AND. Es lo que arma seguir una FK."""
    equals: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.equals)


# --- conexion ----------------------------------------------------------------

def _psycopg():
    try:
        import psycopg
    except ImportError as exc:                              # pragma: no cover
        raise TaskError('Falta el driver de Postgres: pip install "psycopg[binary]"') from exc
    return psycopg


def open_readonly(url: str):
    """Conexion de solo lectura, garantizada por el servidor y no por la vista.

    `autocommit` y no una transaccion larga: una sesion que queda «idle in
    transaction» retiene los AccessShareLock de cada tabla que miro, y un
    `DROP TABLE` o una migracion en otra pestana se quedaria colgado esperando
    a que cierres el explorador. Con autocommit cada SELECT suelta sus locks al
    terminar, y `default_transaction_read_only` hace que el servidor rechace
    cualquier escritura de todas formas.
    """
    psycopg = _psycopg()
    options = (f'-c default_transaction_read_only=on '
               f'-c statement_timeout={STATEMENT_TIMEOUT_MS}')
    try:
        return psycopg.connect(url, options=options, connect_timeout=10, autocommit=True)
    except psycopg.OperationalError as exc:
        raise TaskError(f'No se pudo conectar: {_first_line(exc)}') from exc


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__


def _sql():
    return _psycopg().sql


# --- consultas ---------------------------------------------------------------

def server_info(conn) -> ServerInfo:
    row = conn.execute(
        'SELECT version(), current_database(), current_user, '
        'pg_database_size(current_database()), inet_server_port()').fetchone()
    return ServerInfo(version=row[0], database=row[1], user=row[2],
                      size_bytes=row[3] or 0, port=row[4] or 0)


_RELATIONS = """
SELECT n.nspname, c.relname, c.relkind,
       CASE WHEN c.reltuples >= 0 THEN c.reltuples::bigint ELSE s.n_live_tup END,
       pg_total_relation_size(c.oid),
       obj_description(c.oid, 'pg_class'),
       CASE WHEN c.relispartition THEN p.relname END,
       has_table_privilege(c.oid, 'SELECT'),
       EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
               AND d.objid = c.oid AND d.deptype = 'e')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_inherits i ON i.inhrelid = c.oid AND c.relispartition
LEFT JOIN pg_class p ON p.oid = i.inhparent
LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
ORDER BY n.nspname, c.relname
"""


def list_relations(conn) -> list[Relation]:
    """El arbol entero en una consulta: el catalogo es chico y ya ordenado."""
    return [Relation(schema=r[0], name=r[1], kind=r[2], estimate=r[3],
                     size_bytes=r[4] or 0, comment=r[5], parent=r[6], readable=bool(r[7]),
                     extension=bool(r[8]))
            for r in conn.execute(_RELATIONS).fetchall()]


_ALL_COLUMNS = """
SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), NOT a.attnotnull
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition
  AND a.attnum > 0 AND NOT a.attisdropped
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
  AND n.nspname NOT LIKE 'pg_temp%'
ORDER BY n.nspname, c.relname, a.attnum
"""


def all_columns(conn) -> dict[str, list[tuple[str, str, bool]]]:
    """Columnas de todas las tablas (nombre, tipo, nulo), por `esquema.tabla`.

    Una sola consulta para comparar la base entera contra los modelos
    (`core/db_models.py`) sin un `describe` por tabla."""
    found: dict[str, list[tuple[str, str, bool]]] = {}
    for schema, table, name, type_, nullable in conn.execute(_ALL_COLUMNS).fetchall():
        found.setdefault(f'{schema}.{table}', []).append((name, type_, bool(nullable)))
    return found


_OID = """
SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s
"""

_COLUMNS = """
SELECT a.attname, format_type(a.atttypid, a.atttypmod), t.typname,
       NOT a.attnotnull, pg_get_expr(d.adbin, d.adrelid),
       a.attidentity::text, a.attgenerated::text,
       col_description(a.attrelid, a.attnum)
FROM pg_attribute a
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attrelid = %s AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY a.attnum
"""

# Las columnas de cada lado en el orden de la llave: `conkey`/`confkey` lo
# conservan, `information_schema.constraint_column_usage` no (§5).
_KEYS = """
ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(n, o)
      JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n ORDER BY k.o),
ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(n, o)
      JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n ORDER BY k.o)
"""

_CONSTRAINTS = f"""
SELECT con.conname, con.contype::text, pg_get_constraintdef(con.oid),
       fn.nspname, fc.relname, {_KEYS}
FROM pg_constraint con
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE con.conrelid = %s
ORDER BY CASE con.contype WHEN 'p' THEN 0 WHEN 'f' THEN 1 WHEN 'u' THEN 2 ELSE 3 END, con.conname
"""

_INCOMING = f"""
SELECT con.conname, sn.nspname, sc.relname, {_KEYS}
FROM pg_constraint con
JOIN pg_class sc ON sc.oid = con.conrelid
JOIN pg_namespace sn ON sn.oid = sc.relnamespace
WHERE con.confrelid = %s AND con.contype = 'f'
ORDER BY sn.nspname, sc.relname, con.conname
"""

_INDEXES = """
SELECT i.relname, pg_get_indexdef(x.indexrelid), x.indisunique, x.indisprimary
FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
WHERE x.indrelid = %s
ORDER BY x.indisprimary DESC, i.relname
"""


def describe(conn, relation: Relation) -> TableDetail:
    found = conn.execute(_OID, (relation.schema, relation.name)).fetchone()
    if found is None:
        raise TaskError(f'{relation.qualified} ya no existe.')
    oid = found[0]

    columns = [Column(name=r[0], type=r[1], base_type=r[2], nullable=bool(r[3]),
                      default=r[4], identity=r[5] or '', generated=r[6] or '', comment=r[7])
               for r in conn.execute(_COLUMNS, (oid,)).fetchall()]
    by_name = {c.name: c for c in columns}

    constraints, outgoing = [], []
    for name, kind, definition, ref_schema, ref_table, cols, ref_cols in \
            conn.execute(_CONSTRAINTS, (oid,)).fetchall():
        constraints.append(Constraint(name, kind, definition))
        if kind == 'p':
            for col in cols:
                if col in by_name:
                    by_name[col].pk = True
        elif kind == 'f':
            fk = ForeignKey(name, list(cols), ref_schema, ref_table, list(ref_cols))
            outgoing.append(fk)
            if len(cols) == 1 and cols[0] in by_name and by_name[cols[0]].fk is None:
                by_name[cols[0]].fk = fk

    incoming = [ForeignKey(name, list(ref_cols), schema, table, list(cols))
                for name, schema, table, cols, ref_cols in
                conn.execute(_INCOMING, (oid,)).fetchall()]
    # En `incoming`, `columns` son las de ESTA tabla (a las que apuntan) y
    # `ref_*` la tabla que apunta: asi se lee igual que una FK saliente, desde
    # aca hacia afuera, y seguirla es el mismo gesto.

    indexes = [Index(r[0], r[1], bool(r[2]), bool(r[3]))
               for r in conn.execute(_INDEXES, (oid,)).fetchall()]
    return TableDetail(relation, columns, constraints, indexes, outgoing, incoming)


def _select_list(columns: list[Column]):
    """Cada columna como texto, convertida en el servidor segun su tipo.

    Como texto y no con la conversion del driver: la vista solo muestra, y el
    texto de Postgres es la forma canonica de cualquier tipo —rangos,
    intervalos, enums, numeric de cuarenta digitos— sin que psycopg tenga que
    saber cargarlo.
    """
    sql = _sql()
    items = []
    for col in columns:
        ident = sql.Identifier(col.name)
        if col.base_type in GEOMETRY_TYPES:
            expr = sql.SQL('ST_AsText({})').format(ident)
        elif col.base_type == BYTEA:
            expr = sql.SQL('octet_length({})::text').format(ident)
        else:
            expr = sql.SQL('{}::text').format(ident)
        items.append(sql.SQL('left({}, {})').format(expr, sql.Literal(CELL_CHARS + 1)))
    return sql.SQL(', ').join(items)


def _where(where: Filter | None):
    sql = _sql()
    if not where:
        return sql.SQL('')
    # Literal sin tipo: Postgres lo infiere de la columna, asi `empresa_id = '7'`
    # usa el indice. Comparar `col::text = %s` recorreria la tabla entera.
    clauses = [sql.SQL('{} = {}').format(sql.Identifier(col), sql.Literal(value))
               for col, value in where.equals.items()]
    return sql.SQL(' WHERE ') + sql.SQL(' AND ').join(clauses)


def fetch_rows(conn, detail: TableDetail, *, offset: int = 0, limit: int = PAGE_SIZE,
               order_by: str | None = None, descending: bool = False,
               where: Filter | None = None) -> Page:
    """Una pagina de filas. El orden es del servidor: ordenar solo lo cargado
    mentiria. Sin columna elegida se ordena por la PK, que tambien desempata."""
    sql = _sql()
    rel = detail.relation
    query = sql.SQL('SELECT {} FROM {}.{}').format(
        _select_list(detail.columns), sql.Identifier(rel.schema), sql.Identifier(rel.name))
    query += _where(where)

    keys = []
    if order_by:
        keys.append(sql.SQL('{} {} NULLS LAST').format(
            sql.Identifier(order_by), sql.SQL('DESC' if descending else 'ASC')))
    keys += [sql.Identifier(pk) for pk in detail.primary_key if pk != order_by]
    if keys:
        query += sql.SQL(' ORDER BY ') + sql.SQL(', ').join(keys)
    query += sql.SQL(' LIMIT {} OFFSET {}').format(sql.Literal(limit + 1), sql.Literal(offset))

    rows = conn.execute(query).fetchall()
    return Page(columns=[c.name for c in detail.columns], rows=rows[:limit],
                offset=offset, has_more=len(rows) > limit)


def count_exact(conn, relation: Relation, where: Filter | None = None) -> int:
    sql = _sql()
    query = sql.SQL('SELECT count(*) FROM {}.{}').format(
        sql.Identifier(relation.schema), sql.Identifier(relation.name)) + _where(where)
    return conn.execute(query).fetchone()[0]


# --- formato -------------------------------------------------------------------

def human_count(n: int | None) -> str:
    if n is None:
        return '?'
    for limit, suffix in ((1_000_000_000, 'G'), (1_000_000, 'M'), (1_000, 'k')):
        if n >= limit:
            value = n / limit
            return f'{value:.1f}{suffix}' if value < 10 else f'{value:.0f}{suffix}'
    return str(n)
