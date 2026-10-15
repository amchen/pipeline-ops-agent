"""Expose the read-only investigation tools over MCP (stdio). Write tools are intentionally NOT exposed.

    python -m agent_ops.mcp_server

Claude Desktop / Claude Code config:
    {"mcpServers": {"pipeline-ops": {"command": "python", "args": ["-m", "agent_ops.mcp_server"],
                                     "cwd": "/path/to/pipeline-ops-agent"}}}
"""
from __future__ import annotations

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP -> MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from .tools.base import ToolError
from .tools.readonly import readonly_tools

mcp = FastMCP("pipeline-ops")
_TOOLS = {t.name: t for t in readonly_tools()}


def _call(name: str, **kwargs) -> str:
    try:
        return _TOOLS[name].invoke(kwargs)
    except ToolError as exc:
        return f"error: {exc}"


@mcp.tool()
def get_pipeline_status() -> str:
    """Summarise the most recent pipeline run: overall status and per-node results."""
    return _call("get_pipeline_status")


@mcp.tool()
def read_pipeline_log(tail_lines: int = 80, grep: str | None = None) -> str:
    """Read the tail of the most recent pipeline run log, optionally filtered."""
    return _call("read_pipeline_log", tail_lines=tail_lines, grep=grep)


@mcp.tool()
def list_tables(schema_name: str | None = None) -> str:
    """List warehouse tables and views."""
    return _call("list_tables", schema_name=schema_name)


@mcp.tool()
def describe_table(table: str) -> str:
    """Show columns and row count for a table ('schema.table')."""
    return _call("describe_table", table=table)


@mcp.tool()
def run_readonly_sql(query: str, max_rows: int = 50) -> str:
    """Run one read-only SELECT against the warehouse."""
    return _call("run_readonly_sql", query=query, max_rows=max_rows)


@mcp.tool()
def read_model_sql(name: str) -> str:
    """Read the SQL of a dbt model or singular test."""
    return _call("read_model_sql", name=name)


@mcp.tool()
def search_runbooks(query: str) -> str:
    """Keyword search over the operations runbooks."""
    return _call("search_runbooks", query=query)


if __name__ == "__main__":
    mcp.run()
