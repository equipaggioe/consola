"""The repo's models against the live database (ADR-0015).

No Qt. It compares what Alembic compares: the `Base.metadata` that
`app.models` builds, the package `alembic/env.py` imports. Files are not
parsed: types come from `type_annotation_map`, from `Annotated` aliases
in `base.py` and from enums whose length is only known by executing.
Reading them by hand would give differences that do not exist.

That is why it imports with the project's Python (the `server/` venv, or
the PATH's if the repo has none), like the seeder and partition
payloads. The program travels through `-c` and returns JSON; it does not
touch the database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.core import db_explorer, process
from app.core.errors import TaskError
from app.core.host import HOST

MODELS_PACKAGE = "app.models"
MODELS_DIR = Path("app") / "models"
# Tables that belong to no model and count as no difference: Alembic's,
# and those an extension creates (`Relation.extension`).
ALEMBIC_TABLE = "alembic_version"
DEFAULT_SCHEMA = "public"

_PAYLOAD = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from sqlalchemy.dialects import postgresql
import app.models as package

base = getattr(package, "Base", None)
if base is None:
    from app.models.base import Base as base

modules = {}
for mapper in base.registry.mappers:
    for table in mapper.tables:
        modules.setdefault(table.key, mapper.class_.__module__)

dialect = postgresql.dialect()
prefix = package.__name__ + "."
tables = []
for table in base.metadata.sorted_tables:
    module = modules.get(table.key, "")
    parts = module[len(prefix):].split(".") if module.startswith(prefix) else []
    columns = []
    for col in table.columns:
        try:
            type_sql = str(col.type.compile(dialect=dialect))
        except Exception:
            type_sql = type(col.type).__name__
        columns.append([col.name, type_sql, bool(col.nullable), bool(col.primary_key)])
    tables.append({"schema": table.schema or "", "name": table.name,
                   "folder": "/".join(parts[:-1]),
                   "file": parts[-1] + ".py" if parts else "",
                   "columns": columns})
print("@@MODELS@@" + json.dumps(tables))
"""
_MARK = "@@MODELS@@"


@dataclass
class ModelColumn:
    """A column as a model declares it."""

    name: str
    type: str
    nullable: bool
    pk: bool


@dataclass
class ModelTable:
    """A table as a model declares it."""

    schema: str
    name: str
    folder: str  # folder inside app/models: 'billing', '' at the root
    file: str  # 'invoice.py'
    columns: list[ModelColumn]

    @property
    def qualified(self) -> str:
        """Return `schema.table`."""
        return f"{self.schema}.{self.name}"

    @property
    def source(self) -> str:
        """Return the file that declares it, relative to app/models."""
        return "/".join(p for p in (self.folder, self.file) if p)


# --- read ---


def signature(server_root: Path) -> tuple[tuple[str, int], ...]:
    """Return what changes if a model changes.

    Each .py's path and mtime.

    It costs one `stat` per file and avoids relaunching Python each time
    the tab shows.
    """
    folder = server_root / MODELS_DIR
    if not folder.is_dir():
        return ()
    return tuple(
        sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns) for p in folder.rglob("*.py"))
    )


def _python(server_root: Path) -> str:
    for venv in (".venv", "venv"):
        exe = HOST.venv_python(server_root / venv)
        if exe.is_file():
            return str(exe)
    found = process.which_any(["python", "python3"])
    if not found:
        raise TaskError(
            f"No hay venv en {server_root} ni Python en el PATH para leer los modelos."
        )
    return found


def read_models(server_root: Path) -> list[ModelTable]:
    """Return the models of the repo, importing them with its Python."""
    if not (server_root / MODELS_DIR).is_dir():
        raise TaskError(f"No existe {server_root / MODELS_DIR}.")
    try:
        out = process.capture([_python(server_root), "-c", _PAYLOAD], cwd=server_root, timeout=60)
    except TaskError as exc:
        # The traceback's last line is what says what was missing.
        lines = [row for row in str(exc).strip().splitlines() if row.strip()]
        raise TaskError(
            f"No se pudieron importar los modelos: {lines[-1] if lines else exc}"
        ) from exc
    payload = out[out.rfind(_MARK) + len(_MARK) :] if _MARK in out else ""
    if not payload:
        raise TaskError("Leer los modelos no devolvio nada.")
    return [
        ModelTable(
            schema=t["schema"] or DEFAULT_SCHEMA,
            name=t["name"],
            folder=t["folder"],
            file=t["file"],
            columns=[ModelColumn(*c) for c in t["columns"]],
        )
        for t in json.loads(payload)
    ]


# --- compare ---

OK = "ok"
MISSING = "missing"  # in the models, not in the database
UNMODELED = "unmodeled"  # in the database, not in the models
CHANGED = "changed"  # in both, with different columns
# alembic_version, extension tables: they do not count
SYSTEM = "system"


@dataclass
class ColumnDiff:
    """One column that differs."""

    column: str
    db: str  # as it is in the database; '' if missing
    model: str  # as it is in the model; '' if extra

    @property
    def text(self) -> str:
        """Return the difference as text."""
        if not self.db:
            return f"{self.column}: falta en la base ({self.model})"
        if not self.model:
            return f"{self.column}: sobra en la base ({self.db})"
        return f"{self.column}: base {self.db} · modelo {self.model}"


@dataclass
class TableStatus:
    """A table's state against its model."""

    status: str
    model: ModelTable | None = None
    diffs: list[ColumnDiff] = field(default_factory=list)


@dataclass
class Comparison:
    """The whole comparison."""

    models: list[ModelTable]
    tables: dict[str, TableStatus]  # by `schema.table`, from both sides

    def count(self, status: str) -> int:
        """Return how many tables have that status."""
        return sum(1 for t in self.tables.values() if t.status == status)

    def missing(self) -> list[ModelTable]:
        """Return the models whose table the database lacks."""
        return [t.model for t in self.tables.values() if t.status == MISSING and t.model]


# What SQLAlchemy writes under another name than `format_type`.
# Timestamps need no entry: the Postgres dialect already writes
# `WITH/WITHOUT TIME ZONE`.
_ALIASES = {
    "varchar": "character varying",
    "char": "character",
    "float": "double precision",
    "decimal": "numeric",
}
_LEADING_WORD = re.compile(r"^[a-z_]+")


def normalize_type(text: str) -> str:
    """Normalize a type as SQLAlchemy and `format_type` write it.

    SQLAlchemy writes `VARCHAR(7)` and `NUMERIC(14, 2)`; Postgres's
    `format_type` writes `character varying(7)` and `numeric(14,2)`.
    """
    t = " ".join(text.strip().lower().replace('"', "").split())
    t = re.sub(r"\s*,\s*", ",", t)
    return _LEADING_WORD.sub(lambda m: _ALIASES.get(m.group(0), m.group(0)), t, count=1)


def compare(
    relations: list[db_explorer.Relation],
    columns: dict[str, list[tuple[str, str, bool]]],
    models: list[ModelTable],
) -> Comparison:
    """Compare the database's relations against the models."""
    tables: dict[str, TableStatus] = {}
    by_name = {r.qualified: r for r in relations}

    for model in models:
        rel = by_name.get(model.qualified)
        if rel is None:
            tables[model.qualified] = TableStatus(MISSING, model)
            continue
        diffs = _column_diffs(columns.get(model.qualified, []), model)
        tables[model.qualified] = TableStatus(CHANGED if diffs else OK, model, diffs)

    for rel in relations:
        if rel.qualified in tables or rel.parent or rel.kind not in ("r", "p", "f"):
            # Partitions follow their parent; views are not modeled.
            continue
        system = rel.extension or rel.name == ALEMBIC_TABLE
        tables[rel.qualified] = TableStatus(SYSTEM if system else UNMODELED)
    return Comparison(models, tables)


def _column_diffs(db_columns: list[tuple[str, str, bool]], model: ModelTable) -> list[ColumnDiff]:
    db = {name: (type_, nullable) for name, type_, nullable in db_columns}
    diffs = []
    for col in model.columns:
        want = _describe(col.type, col.nullable)
        if col.name not in db:
            diffs.append(ColumnDiff(col.name, "", want))
            continue
        type_, nullable = db[col.name]
        if normalize_type(type_) != normalize_type(col.type) or nullable != col.nullable:
            diffs.append(ColumnDiff(col.name, _describe(type_, nullable), want))
    modeled = {c.name for c in model.columns}
    for name, type_, nullable in db_columns:
        if name not in modeled:
            diffs.append(ColumnDiff(name, _describe(type_, nullable), ""))
    return diffs


def _describe(type_: str, nullable: bool) -> str:
    return f"{normalize_type(type_)}{'' if nullable else ' not null'}"
