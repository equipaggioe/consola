"""Read-only introspection of a Postgres database (ADR-0015).

No Qt: functions over a psycopg connection, which the view calls from
its thread (`services/db_worker.py`) and the `explore_db` task from its
own.

It all comes from `pg_catalog`, not `information_schema`: the latter
only shows what the role can touch, and the explorer connects as the
app's role, so a table without GRANT would silently vanish from the
tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import Connection, sql
from psycopg.sql import SQL, Composed
from PySide6.QtCore import QLocale

from app.services.errors import TaskError

STATEMENT_TIMEOUT_MS = 15000
PAGE_SIZE = 200
# A cell brings at most this: a `text` of megabytes does not travel
# whole to be shown cut. One extra character warns of a cut.
CELL_CHARS = 2000

# Types that do not read as text: geometry comes as hex EWKB and a bytea
# as its whole dump. They arrive converted from the server.
GEOMETRY_TYPES = ("geometry", "geography")
BYTEA = "bytea"

# The URL with its password does not travel through the tab's bar, which
# shows the masked one: the task leaves it in the session under this key
# and the view reads it.
_SESSION_PREFIX = "explore_db:url:"


def session_key(safe_url: str) -> str:
    """Return the session key of a masked URL."""
    return _SESSION_PREFIX + safe_url


KIND_LABELS = {
    "r": "tabla",
    "p": "tabla particionada",
    "v": "vista",
    "m": "vista materializada",
    "f": "tabla foránea",
}


@dataclass
class ServerInfo:
    """What the server says about itself."""

    version: str
    database: str
    user: str
    size_bytes: int
    port: int


@dataclass
class Relation:
    """A table, view or partition."""

    schema: str
    name: str
    kind: str  # relkind: r p v m f
    # reltuples; without ANALYZE yet, the live rows the collector
    # counts. None on a view.
    estimate: int | None
    size_bytes: int
    comment: str | None
    parent: str | None  # parent table, if a partition
    readable: bool  # the role has SELECT
    # an extension created it (PostGIS's spatial_ref_sys)
    extension: bool = False

    @property
    def qualified(self) -> str:
        """Return `schema.table`."""
        return f"{self.schema}.{self.name}"

    @property
    def kind_label(self) -> str:
        """Return the readable kind."""
        return KIND_LABELS.get(self.kind, self.kind)


@dataclass
class Column:
    """A column of a table."""

    name: str
    type: str  # with modifier: varchar(120), geometry(Point,4326)
    base_type: str  # typname: int4, jsonb, geometry
    nullable: bool
    default: str | None
    identity: str  # '' | 'a' (ALWAYS) | 'd' (BY DEFAULT)
    generated: str  # '' | 's' (STORED)
    comment: str | None
    pk: bool = False
    # only if the FK is of this single column
    fk: "ForeignKey | None" = None


@dataclass
class ForeignKey:
    """A foreign key."""

    name: str
    columns: list[str]
    ref_schema: str
    ref_table: str
    ref_columns: list[str]


@dataclass
class Constraint:
    """A constraint."""

    name: str
    kind: str  # contype: p u f c x
    definition: str


@dataclass
class Index:
    """An index."""

    name: str
    definition: str
    unique: bool
    primary: bool


@dataclass
class TableDetail:
    """The whole structure of a table."""

    relation: Relation
    columns: list[Column]
    constraints: list[Constraint]
    indexes: list[Index]
    outgoing: list[ForeignKey]
    # who points to this table: columns = those of the other
    incoming: list[ForeignKey]

    @property
    def primary_key(self) -> list[str]:
        """Return the primary key's columns."""
        return [c.name for c in self.columns if c.pk]


@dataclass
class Page:
    """A page of rows."""

    columns: list[str]
    rows: list[tuple[Any, ...]]
    offset: int
    has_more: bool


@dataclass
class Filter:
    """Per-column equalities, ANDed. Following an FK builds it."""

    equals: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Return whether it filters anything."""
        return bool(self.equals)


# --- connection ---


def open_readonly(url: str) -> Connection:
    """Return a read-only connection, guaranteed by the server.

    `autocommit` and not a long transaction: a session left «idle in
    transaction» retains the AccessShareLock of each table it looked at,
    and a `DROP TABLE` or a migration in another tab would hang until
    the explorer closes. With autocommit each SELECT releases its locks
    when it ends, and `default_transaction_read_only` makes the server
    reject any write anyway.
    """
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    try:
        return psycopg.connect(url, options=options, connect_timeout=10, autocommit=True)
    except psycopg.OperationalError as exc:
        raise TaskError(f"No se pudo conectar: {_first_line(exc)}") from exc


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__


# --- queries ---


def server_info(conn: Connection) -> ServerInfo:
    """Return what the server says about itself."""
    row = conn.execute(
        "SELECT version(), current_database(), current_user, "
        "pg_database_size(current_database()), inet_server_port()"
    ).fetchone()
    if row is None:
        raise TaskError("El servidor no devolvió sus datos.")
    return ServerInfo(
        version=row[0], database=row[1], user=row[2], size_bytes=row[3] or 0, port=row[4] or 0
    )


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


def list_relations(conn: Connection) -> list[Relation]:
    """Return the whole tree in one query.

    The catalog is small and sorted.
    """
    return [
        Relation(
            schema=r[0],
            name=r[1],
            kind=r[2],
            estimate=r[3],
            size_bytes=r[4] or 0,
            comment=r[5],
            parent=r[6],
            readable=bool(r[7]),
            extension=bool(r[8]),
        )
        for r in conn.execute(_RELATIONS).fetchall()
    ]


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


def all_columns(conn: Connection) -> dict[str, list[tuple[str, str, bool]]]:
    """Return (name, type, null) of every column by `schema.table`.

    One query to compare the whole database against the models
    (`services/db_models.py`) without a `describe` per table.
    """
    found: dict[str, list[tuple[str, str, bool]]] = {}
    for schema, table, name, type_, nullable in conn.execute(_ALL_COLUMNS).fetchall():
        found.setdefault(f"{schema}.{table}", []).append((name, type_, bool(nullable)))
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

# Each side's columns in key order: `conkey` and `confkey` keep it,
# `information_schema.constraint_column_usage` does not.
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


def describe(conn: Connection, relation: Relation) -> TableDetail:
    """Return the structure of a table."""
    found = conn.execute(_OID, (relation.schema, relation.name)).fetchone()
    if found is None:
        raise TaskError(f"{relation.qualified} ya no existe.")
    oid = found[0]

    columns = [
        Column(
            name=r[0],
            type=r[1],
            base_type=r[2],
            nullable=bool(r[3]),
            default=r[4],
            identity=r[5] or "",
            generated=r[6] or "",
            comment=r[7],
        )
        for r in conn.execute(_COLUMNS, (oid,)).fetchall()
    ]
    by_name = {c.name: c for c in columns}

    constraints: list[Constraint] = []
    outgoing: list[ForeignKey] = []
    for name, kind, definition, ref_schema, ref_table, cols, ref_cols in conn.execute(
        _CONSTRAINTS, (oid,)
    ).fetchall():
        constraints.append(Constraint(name, kind, definition))
        if kind == "p":
            for col in cols:
                if col in by_name:
                    by_name[col].pk = True
        elif kind == "f":
            fk = ForeignKey(name, list(cols), ref_schema, ref_table, list(ref_cols))
            outgoing.append(fk)
            if len(cols) == 1 and cols[0] in by_name and by_name[cols[0]].fk is None:
                by_name[cols[0]].fk = fk

    incoming = [
        ForeignKey(name, list(ref_cols), schema, table, list(cols))
        for name, schema, table, cols, ref_cols in conn.execute(_INCOMING, (oid,)).fetchall()
    ]
    # In `incoming`, `columns` are those of THIS table (pointed at) and
    # `ref_*` is the table pointing: it reads like an outgoing FK, from
    # here outward, and following it is the same gesture.

    indexes = [
        Index(r[0], r[1], bool(r[2]), bool(r[3]))
        for r in conn.execute(_INDEXES, (oid,)).fetchall()
    ]
    return TableDetail(relation, columns, constraints, indexes, outgoing, incoming)


def _select_list(columns: list[Column]) -> Composed:
    """Return each column as text, converted on the server by its type.

    As text and not with the driver's conversion: the view only shows,
    and Postgres's text is the canonical form of any type (ranges,
    intervals, enums, forty-digit numerics) without psycopg having to
    load it.
    """
    items = []
    for col in columns:
        ident = sql.Identifier(col.name)
        if col.base_type in GEOMETRY_TYPES:
            expr = sql.SQL("ST_AsText({})").format(ident)
        elif col.base_type == BYTEA:
            expr = sql.SQL("octet_length({})::text").format(ident)
        else:
            expr = sql.SQL("{}::text").format(ident)
        items.append(sql.SQL("left({}, {})").format(expr, sql.Literal(CELL_CHARS + 1)))
    return sql.SQL(", ").join(items)


def _where(where: Filter | None) -> Composed | SQL:
    if not where:
        return sql.SQL("")
    # An untyped literal: Postgres infers it from the column, so
    # `company_id = '7'` uses the index. Comparing `col::text = %s`
    # would walk the whole table.
    clauses = [
        sql.SQL("{} = {}").format(sql.Identifier(col), sql.Literal(value))
        for col, value in where.equals.items()
    ]
    return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)


def fetch_rows(
    conn: Connection,
    detail: TableDetail,
    *,
    offset: int = 0,
    limit: int = PAGE_SIZE,
    order_by: str | None = None,
    descending: bool = False,
    where: Filter | None = None,
) -> Page:
    """Return a page of rows.

    The server orders: ordering only what is loaded would lie. With no
    chosen column it orders by the PK, which also breaks ties.
    """
    rel = detail.relation
    query = sql.SQL("SELECT {} FROM {}.{}").format(
        _select_list(detail.columns), sql.Identifier(rel.schema), sql.Identifier(rel.name)
    )
    query += _where(where)

    keys = []
    if order_by:
        keys.append(
            sql.SQL("{} {} NULLS LAST").format(
                sql.Identifier(order_by), sql.SQL("DESC" if descending else "ASC")
            )
        )
    keys += [sql.Identifier(pk) for pk in detail.primary_key if pk != order_by]
    if keys:
        query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(keys)
    query += sql.SQL(" LIMIT {} OFFSET {}").format(sql.Literal(limit + 1), sql.Literal(offset))

    rows = conn.execute(query).fetchall()
    return Page(
        columns=[c.name for c in detail.columns],
        rows=rows[:limit],
        offset=offset,
        has_more=len(rows) > limit,
    )


def count_exact(conn: Connection, relation: Relation, where: Filter | None = None) -> int:
    """Return the exact row count."""
    query = sql.SQL("SELECT count(*) FROM {}.{}").format(
        sql.Identifier(relation.schema), sql.Identifier(relation.name)
    ) + _where(where)
    row = conn.execute(query).fetchone()
    if row is None:
        raise TaskError("El servidor no devolvió el conteo.")
    return row[0]


# --- format ---


def human_count(n: int | None, locale: QLocale) -> str:
    """Return a count as short text, with the numbers of `locale`."""
    if n is None:
        return "?"
    for limit, suffix in ((1_000_000_000, "G"), (1_000_000, "M"), (1_000, "k")):
        if n >= limit:
            value = n / limit
            return locale.toString(value, "f", 1 if value < 10 else 0) + suffix
    return locale.toString(n)
