from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

"""
Inspección rápida de la base de datos (PostgreSQL).

Flujo:
- Asegura que se ejecute con el Python del venv del servidor.
- Resuelve DATABASE_URL según RUN_REMOTE (scripts/.env; ver common.resolve_database_url).
- Carga configuración desde app.core.settings.
- Prueba conectividad y muestra versión del servidor.
- Lista tablas del esquema indicado y cuenta registros.
- Muestra tamaño total de la base de datos.
- Opcionalmente imprime una muestra de filas de una tabla.
"""


def _repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists():
            return path
    raise RuntimeError("No se encontró la raíz del repo (.git).")


sys.path.insert(0, str(_repo_root(Path(__file__).resolve()) / "scripts"))
from common import load_env_file, require_env, resolve_database_url, venv_python


def log(stage: str, message: str) -> None:
    print(f"[{stage}] {message}")


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _parse_table_ref(table_ref: str, default_schema: str) -> tuple[str, str]:
    value = table_ref.strip()
    if not value:
        raise ValueError("Tabla vacía.")
    if "." in value:
        schema, table = value.split(".", 1)
        schema = schema.strip()
        table = table.strip()
        if not schema or not table:
            raise ValueError("Formato de tabla inválido. Usa tabla o esquema.tabla.")
        return schema, table
    return default_schema, value


async def _print_connectivity(conn: AsyncConnection, database_url: str) -> None:
    url = make_url(database_url)
    safe_url = database_url
    if url.password:
        safe_url = database_url.replace(url.password, "****")

    host = url.host or "localhost"
    port = url.port or 5432
    log("INFO", f"Probando conexión a: {host}:{port}")
    log("INFO", f"URL: {safe_url}")

    version = (await conn.execute(text("SELECT version();"))).scalar()
    db_name = (await conn.execute(text("SELECT current_database();"))).scalar()
    db_user = (await conn.execute(text("SELECT current_user;"))).scalar()
    log("OK", "Conexión establecida correctamente.")
    if version:
        log("INFO", f"Servidor: {str(version)[:80]}...")
    if db_name:
        log("INFO", f"Base de datos: {db_name}")
    if db_user:
        log("INFO", f"Usuario: {db_user}")


async def _list_tables(conn: AsyncConnection, schema: str) -> list[str]:
    rows = (await conn.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relkind IN ('r','m')
            ORDER BY c.relname
            """
        ),
        {"schema": schema},
    )).scalars().all()
    return list(rows)


async def _count_table_rows(conn: AsyncConnection, schema: str, table: str) -> int:
    qualified = f"{_quote_ident(schema)}.{_quote_ident(table)}"
    value = (await conn.execute(text(f"SELECT COUNT(*) FROM {qualified}"))).scalar()
    return int(value or 0)


async def _get_database_size_bytes(conn: AsyncConnection) -> int | None:
    value = (await conn.execute(text("SELECT pg_database_size(current_database())"))).scalar()
    if value is None:
        return None
    return int(value)


def _format_bytes(size_bytes: int) -> str:
    units: list[tuple[str, int]] = [
        ("bytes", 1),
        ("kB", 1024),
        ("MB", 1024**2),
        ("GB", 1024**3),
        ("TB", 1024**4),
    ]
    for unit_name, unit_value in reversed(units):
        if size_bytes >= unit_value:
            return f"{size_bytes / unit_value:.2f} {unit_name}"
    return f"{size_bytes} bytes"


async def _get_primary_key_column(conn: AsyncConnection, schema: str, table: str) -> str | None:
    row = (await conn.execute(
        text(
            """
            SELECT a.attname
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a
              ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
            WHERE i.indisprimary
              AND n.nspname = :schema
              AND c.relname = :table
            ORDER BY array_position(i.indkey, a.attnum)
            LIMIT 1
            """
        ),
        {"schema": schema, "table": table},
    )).scalar()
    return str(row) if row else None


async def _fetch_table_sample(
    conn: AsyncConnection,
    *,
    schema: str,
    table: str,
    limit: int,
) -> list[dict[str, object]]:
    qualified = f"{_quote_ident(schema)}.{_quote_ident(table)}"
    pk = await _get_primary_key_column(conn, schema, table)
    if pk:
        query = text(
            f"SELECT * FROM {qualified} ORDER BY {_quote_ident(pk)} DESC NULLS LAST LIMIT :limit"
        )
    else:
        query = text(f"SELECT * FROM {qualified} LIMIT :limit")
    return (await conn.execute(query, {"limit": limit})).mappings().all()


def _print_rows(rows: list[dict[str, object]], max_col_width: int = 40) -> None:
    if not rows:
        print("(sin filas)")
        return

    keys = list(rows[0].keys())
    widths: dict[str, int] = {k: min(max_col_width, max(8, len(k))) for k in keys}

    def cell_str(value: object) -> str:
        if value is None:
            return "NULL"
        s = str(value)
        if len(s) > max_col_width:
            return s[: max_col_width - 3] + "..."
        return s

    for row in rows:
        for k in keys:
            widths[k] = min(max_col_width, max(widths[k], len(cell_str(row.get(k)))))

    header = " | ".join(k.ljust(widths[k]) for k in keys)
    sep = "-+-".join("-" * widths[k] for k in keys)
    print(header)
    print(sep)
    for row in rows:
        print(" | ".join(cell_str(row.get(k)).ljust(widths[k]) for k in keys))


async def run() -> None:
    parser = argparse.ArgumentParser(description="Inspecciona conectividad y estado de la DB.")
    parser.add_argument("--schema", type=str, default="public", help="Esquema a inspeccionar (default: public)")
    parser.add_argument("--table", type=str, default=None, help="Tabla a mostrar (tabla o esquema.tabla)")
    parser.add_argument("--limit", type=int, default=5, help="Filas a imprimir para --table (default: 5)")
    parser.add_argument("--skip-check", action="store_true", help="Saltar impresión de conectividad/version")
    args = parser.parse_args()

    safe_limit = max(1, min(int(args.limit), 200))

    repo_root = _repo_root(Path(__file__).resolve())
    load_env_file(repo_root / "scripts" / ".env")
    server_root = repo_root / require_env("SERVER_DIR")
    venv_python(server_root / ".venv", restart=True)
    sys.path.append(str(server_root))

    database_url, tunnel = resolve_database_url(repo_root)
    os.environ["DATABASE_URL"] = database_url

    try:
        from app.core.settings import settings

        engine = create_async_engine(settings.database_url_async, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                if not args.skip_check:
                    await _print_connectivity(conn, settings.database_url)

                schema = str(args.schema).strip() or "public"
                tables = await _list_tables(conn, schema)
                if not tables:
                    log("INFO", f"No se encontraron tablas en el esquema: {schema}")
                    return

                table_col_width = min(50, max(len("TABLA"), max(len(t) for t in tables)))
                print()
                print("=" * (table_col_width + 14))
                print(f"{'TABLA'.ljust(table_col_width)} | {'REGISTROS'.rjust(10)}")
                print("-" * (table_col_width + 14))

                for table in tables:
                    try:
                        count = await _count_table_rows(conn, schema, table)
                        count_str = str(count)
                    except Exception as exc:
                        count_str = "ERROR"
                        log("ERROR", f"COUNT falló para {schema}.{table}: {exc}")
                    print(f"{table.ljust(table_col_width)} | {count_str.rjust(10)}")

                print("=" * (table_col_width + 14))

                try:
                    size_bytes = await _get_database_size_bytes(conn)
                    if size_bytes is not None:
                        log("INFO", f"Tamaño de la base de datos: {_format_bytes(size_bytes)} ({size_bytes} bytes)")
                except Exception as exc:
                    log("ERROR", f"No se pudo obtener tamaño de la base de datos: {exc}")

                if args.table:
                    try:
                        table_schema, table_name = _parse_table_ref(args.table, schema)
                    except ValueError as exc:
                        log("ERROR", str(exc))
                        raise SystemExit(2) from exc

                    if table_schema != schema:
                        log("INFO", f"Mostrando tabla de esquema distinto: {table_schema}")

                    if table_schema == schema and table_name not in tables:
                        log("ERROR", f"La tabla no existe en {schema}: {table_name}")
                        raise SystemExit(2)

                    print()
                    log("INFO", f"Muestra de datos: {table_schema}.{table_name} (limit={safe_limit})")
                    rows = await _fetch_table_sample(conn, schema=table_schema, table=table_name, limit=safe_limit)
                    _print_rows(list(rows))
        finally:
            await engine.dispose()
    finally:
        if tunnel is not None:
            tunnel.terminate()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
