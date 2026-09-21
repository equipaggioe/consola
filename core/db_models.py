from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import db_explorer, process
from .errors import TaskError

"""
Los modelos del repo contra la base viva (ADR-0015).

Sin Qt. Lo que se compara es lo mismo que compara Alembic: el `Base.metadata`
que arma `app.models`, el paquete que importa `alembic/env.py` en todos los
repos. No se parsean los archivos: los tipos salen de `type_annotation_map`, de
alias `Annotated` en `base.py` y de enums cuyo largo solo se sabe ejecutando.
Leerlos a mano daria diferencias que no existen.

Por eso se importa con el Python del proyecto (el venv de `server/`, o el del
PATH si el repo no tiene uno), como los payloads de seeders y particiones. El
programa viaja por `-c` y devuelve JSON; no toca la base.
"""

MODELS_PACKAGE = 'app.models'
MODELS_DIR = Path('app') / 'models'
# Tablas que no son de ningun modelo y no cuentan como diferencia: la de
# Alembic, y las que crea una extension (`Relation.extension`).
ALEMBIC_TABLE = 'alembic_version'
DEFAULT_SCHEMA = 'public'

_PAYLOAD = '''
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
'''
_MARK = '@@MODELS@@'


@dataclass
class ModelColumn:
    name: str
    type: str
    nullable: bool
    pk: bool


@dataclass
class ModelTable:
    schema: str
    name: str
    folder: str            # carpeta dentro de app/models: 'billing', '' en la raiz
    file: str              # 'invoice.py'
    columns: list[ModelColumn]

    @property
    def qualified(self) -> str:
        return f'{self.schema}.{self.name}'

    @property
    def source(self) -> str:
        return '/'.join(p for p in (self.folder, self.file) if p)


# --- leer ----------------------------------------------------------------------

def signature(server_root: Path) -> tuple:
    """Lo que cambia si cambia algun modelo: ruta y mtime de cada .py. Cuesta
    un `stat` por archivo, y evita relanzar Python cada vez que se muestra la
    pestana."""
    folder = server_root / MODELS_DIR
    if not folder.is_dir():
        return ()
    return tuple(sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns)
                        for p in folder.rglob('*.py')))


def _python(server_root: Path) -> str:
    for venv in ('.venv', 'venv'):
        exe = server_root / venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if exe.is_file():
            return str(exe)
    found = process.which_any(['python', 'python3'])
    if not found:
        raise TaskError(f'No hay venv en {server_root} ni Python en el PATH para leer los modelos.')
    return found


def read_models(server_root: Path) -> list[ModelTable]:
    if not (server_root / MODELS_DIR).is_dir():
        raise TaskError(f'No existe {server_root / MODELS_DIR}.')
    try:
        out = process.capture([_python(server_root), '-c', _PAYLOAD],
                              cwd=server_root, timeout=60)
    except TaskError as exc:
        # La ultima linea del traceback es la que dice que falto.
        lines = [l for l in str(exc).strip().splitlines() if l.strip()]
        raise TaskError(f'No se pudieron importar los modelos: {lines[-1] if lines else exc}') from exc
    payload = out[out.rfind(_MARK) + len(_MARK):] if _MARK in out else ''
    if not payload:
        raise TaskError('Leer los modelos no devolvio nada.')
    return [ModelTable(schema=t['schema'] or DEFAULT_SCHEMA, name=t['name'], folder=t['folder'],
                       file=t['file'], columns=[ModelColumn(*c) for c in t['columns']])
            for t in json.loads(payload)]


# --- comparar --------------------------------------------------------------------

OK = 'ok'
MISSING = 'missing'        # en los modelos, no en la base
UNMODELED = 'unmodeled'    # en la base, no en los modelos
CHANGED = 'changed'        # en los dos, con columnas distintas
SYSTEM = 'system'          # alembic_version, tablas de extensiones: no cuentan


@dataclass
class ColumnDiff:
    column: str
    db: str                # como esta en la base; '' si falta
    model: str             # como esta en el modelo; '' si sobra

    @property
    def text(self) -> str:
        if not self.db:
            return f'{self.column}: falta en la base ({self.model})'
        if not self.model:
            return f'{self.column}: sobra en la base ({self.db})'
        return f'{self.column}: base {self.db} · modelo {self.model}'


@dataclass
class TableStatus:
    status: str
    model: ModelTable | None = None
    diffs: list[ColumnDiff] = field(default_factory=list)


@dataclass
class Comparison:
    models: list[ModelTable]
    tables: dict[str, TableStatus]   # por `esquema.tabla`, de los dos lados

    def count(self, status: str) -> int:
        return sum(1 for t in self.tables.values() if t.status == status)

    def missing(self) -> list[ModelTable]:
        return [t.model for t in self.tables.values() if t.status == MISSING]


# Lo que SQLAlchemy escribe con otro nombre que `format_type`. Los timestamps
# no hacen falta: el dialecto de Postgres ya los escribe `WITH/WITHOUT TIME ZONE`.
_ALIASES = {
    'varchar': 'character varying', 'char': 'character',
    'float': 'double precision', 'decimal': 'numeric',
}
_LEADING_WORD = re.compile(r'^[a-z_]+')


def normalize_type(text: str) -> str:
    """El mismo tipo escrito por SQLAlchemy (`VARCHAR(7)`, `NUMERIC(14, 2)`)
    y por `format_type` de Postgres (`character varying(7)`, `numeric(14,2)`)."""
    t = ' '.join(text.strip().lower().replace('"', '').split())
    t = re.sub(r'\s*,\s*', ',', t)
    return _LEADING_WORD.sub(lambda m: _ALIASES.get(m.group(0), m.group(0)), t, count=1)


def compare(relations: list[db_explorer.Relation],
            columns: dict[str, list[tuple[str, str, bool]]],
            models: list[ModelTable]) -> Comparison:
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
        if rel.qualified in tables or rel.parent or rel.kind not in ('r', 'p', 'f'):
            # Las particiones siguen a su madre; las vistas no se modelan.
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
            diffs.append(ColumnDiff(col.name, '', want))
            continue
        type_, nullable = db[col.name]
        if normalize_type(type_) != normalize_type(col.type) or nullable != col.nullable:
            diffs.append(ColumnDiff(col.name, _describe(type_, nullable), want))
    modeled = {c.name for c in model.columns}
    for name, type_, nullable in db_columns:
        if name not in modeled:
            diffs.append(ColumnDiff(name, _describe(type_, nullable), ''))
    return diffs


def _describe(type_: str, nullable: bool) -> str:
    return f'{normalize_type(type_)}{"" if nullable else " not null"}'
