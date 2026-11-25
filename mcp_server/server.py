"""Tiny MCP server exposing the local dbt + DuckDB lab to an LLM client.

Stdio transport: logs go to stderr only.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

load_dotenv()

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("DBT_DUCKDB_PATH", ROOT / "duckdb" / "lab.duckdb"))
SAFE_DBT_COMMANDS = {"parse", "seed", "run", "test", "build", "docs"}

mcp = MCPServer("dbt-duckdb-lab")


def _connect() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise ToolError(
            f"Database not found: {DB_PATH}. "
            "Run: uv run python scripts/process_seeds.py"
        )
    return duckdb.connect(str(DB_PATH), read_only=True)


@mcp.tool()
def query_duckdb(sql: str, limit: int = 50) -> str:
    """Run a read-only SELECT against the local DuckDB file and return rows as text.

    Args:
        sql: A SELECT / WITH / SHOW / DESCRIBE query. No writes or DDL allowed.
        limit: Maximum rows to return (default 50, capped at 200).
    """
    cleaned = sql.strip().rstrip(";")
    if not re.match(r"^(select|with|show|describe|pragma)\b", cleaned, re.IGNORECASE):
        raise ToolError("Only read-only queries are allowed.")
    limit = max(1, min(int(limit), 200))

    con = _connect()
    try:
        result = con.execute(cleaned)
        columns = [d[0] for d in result.description]
        rows = result.fetchmany(limit)
    finally:
        con.close()

    header = " | ".join(columns)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    return f"{header}\n{body}" if body else f"{header}\n(no rows)"


@mcp.tool()
def list_dbt_models() -> str:
    """List dbt models grouped by SA, INT and CA layer."""
    lines = []
    for layer in ("sa", "int", "ca"):
        files = sorted((ROOT / "models" / layer).glob("*.sql"))
        lines.append(f"[{layer}] " + (", ".join(f.stem for f in files) or "(none)"))
    return "\n".join(lines)


@mcp.tool()
def get_model_sql(model_name: str) -> str:
    """Return the SQL source of a dbt model.

    Args:
        model_name: Model file name without .sql, e.g. stg_orders.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", model_name):
        raise ToolError("Invalid model name.")
    matches = list((ROOT / "models").glob(f"**/{model_name}.sql"))
    if not matches:
        raise ToolError(f"Model not found: {model_name}")
    return matches[0].read_text()


@mcp.tool()
def run_dbt(command: str = "build") -> str:
    """Run a whitelisted dbt command in the project root and return its output.

    Args:
        command: One of parse, seed, run, test, build, docs. No extra flags.
    """
    if command not in SAFE_DBT_COMMANDS:
        raise ToolError(
            f"Command not allowed. Choose from: {sorted(SAFE_DBT_COMMANDS)}"
        )

    env = {**os.environ, "DBT_PROFILES_DIR": str(ROOT)}
    result = subprocess.run(
        ["uv", "run", "dbt", command],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise ToolError(
            f"dbt {command} failed (exit {result.returncode}):\n{output[-4000:]}"
        )
    return output[-4000:] or f"dbt {command} completed."


if __name__ == "__main__":
    mcp.run(transport="stdio")
