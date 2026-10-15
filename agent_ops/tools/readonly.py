"""Read-only investigation tools. None of these can change the warehouse or the repo."""
from __future__ import annotations

import re

import duckdb
from pydantic import BaseModel, Field

from .. import config, pipeline
from ..policy import FILE_FUNCTION_RE
from .base import Tool, ToolError

_IDENT = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$"


class NoArgs(BaseModel):
    pass


class ReadLogArgs(BaseModel):
    tail_lines: int = Field(80, ge=1, le=400, description="How many trailing log lines to return.")
    grep: str | None = Field(None, max_length=100, description="Optional case-insensitive substring filter.")


class ListTablesArgs(BaseModel):
    schema_name: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", description="Optional schema filter, e.g. 'raw'.")


class DescribeTableArgs(BaseModel):
    table: str = Field(pattern=_IDENT, description="Table as 'schema.table' or 'table'.")


class SqlArgs(BaseModel):
    query: str = Field(max_length=4000, description="A single read-only SELECT statement.")
    max_rows: int = Field(50, ge=1, le=200)


class ModelArgs(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", description="dbt model or singular test name, e.g. 'stg_orders'.")


class RunbookArgs(BaseModel):
    query: str = Field(min_length=2, max_length=200, description="Keywords describing the problem.")


def _ro_conn() -> duckdb.DuckDBPyConnection:
    try:
        con = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    except duckdb.Error as exc:
        raise ToolError(f"Cannot open warehouse: {exc}") from None
    try:
        con.execute("SET enable_external_access=false")
    except duckdb.Error:
        pass
    return con


def _get_status(_: NoArgs):
    return pipeline.pipeline_status()


def _read_log(a: ReadLogArgs):
    return pipeline.read_log(a.tail_lines, a.grep)


def _list_tables(a: ListTablesArgs):
    con = _ro_conn()
    try:
        q = (
            "select table_schema, table_name, table_type from information_schema.tables "
            "where table_schema not in ('information_schema', 'pg_catalog')"
        )
        params: list = []
        if a.schema_name:
            q += " and table_schema = ?"
            params.append(a.schema_name)
        rows = con.execute(q + " order by 1, 2", params).fetchall()
        return [{"schema": r[0], "table": r[1], "type": r[2]} for r in rows]
    finally:
        con.close()


def _describe_table(a: DescribeTableArgs):
    schema, _, table = a.table.rpartition(".")
    con = _ro_conn()
    try:
        cols = con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_name = ? and (? = '' or table_schema = ?) order by ordinal_position",
            [table, schema, schema],
        ).fetchall()
        if not cols:
            raise ToolError(f"Table '{a.table}' does not exist (check list_tables).")
        qualified = f'"{schema}"."{table}"' if schema else f'"{table}"'
        n = con.execute(f"select count(*) from {qualified}").fetchone()[0]
        return {"table": a.table, "row_count": n, "columns": [{"name": c, "type": t} for c, t in cols]}
    finally:
        con.close()


def _run_sql(a: SqlArgs):
    query = a.query.strip().rstrip(";")
    if FILE_FUNCTION_RE.search(query):
        raise ToolError("Filesystem functions are not allowed.")
    con = _ro_conn()
    try:
        stmts = con.extract_statements(query)
        if len(stmts) != 1 or stmts[0].type != duckdb.StatementType.SELECT:
            raise ToolError("Only a single SELECT statement is allowed.")
        cur = con.execute(query)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(a.max_rows + 1)
        return {"columns": cols, "rows": [list(r) for r in rows[: a.max_rows]], "truncated": len(rows) > a.max_rows}
    except duckdb.Error as exc:
        raise ToolError(f"SQL error: {exc}") from None
    finally:
        con.close()


def _read_model(a: ModelArgs):
    for sub in ("models", "tests"):
        for path in (config.PIPELINE_DIR / sub).rglob(f"{a.name}.sql"):
            return {"path": str(path.relative_to(config.PIPELINE_DIR)), "sql": path.read_text()}
    raise ToolError(f"No model or test named '{a.name}'.")


def _search_runbooks(a: RunbookArgs):
    words = set(re.findall(r"[a-z_]{3,}", a.query.lower()))
    scored = []
    for path in sorted((config.PIPELINE_DIR / "runbooks").glob("*.md")):
        text = path.read_text()
        tokens = set(re.findall(r"[a-z_]{3,}", (path.stem + " " + text).lower()))
        score = len(words & tokens)
        if score:
            scored.append((score, path.stem, text))
    scored.sort(reverse=True)
    return [{"runbook": name, "score": s, "content": text[:1500]} for s, name, text in scored[:3]] or "No runbook matched."


def readonly_tools() -> list[Tool]:
    return [
        Tool("get_pipeline_status", "Summarise the most recent pipeline run: overall status and per-node results.", NoArgs, _get_status),
        Tool("read_pipeline_log", "Read the tail of the most recent pipeline run log, optionally filtered.", ReadLogArgs, _read_log, untrusted=True),
        Tool("list_tables", "List warehouse tables and views.", ListTablesArgs, _list_tables),
        Tool("describe_table", "Show columns and row count for a table.", DescribeTableArgs, _describe_table),
        Tool("run_readonly_sql", "Run one read-only SELECT against the warehouse. Results are capped.", SqlArgs, _run_sql, untrusted=True),
        Tool("read_model_sql", "Read the SQL of a dbt model or singular test.", ModelArgs, _read_model, untrusted=True),
        Tool("search_runbooks", "Keyword search over the operations runbooks.", RunbookArgs, _search_runbooks, untrusted=True),
    ]
