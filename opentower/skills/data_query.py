"""Data query skill — CSV/SQLite/Excel analysis + LLM-guided SQL.

Enterprise #2 most-called skill: pull data, auto-analyze,
generate reports. Finance/ops teams need this daily.
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
from pathlib import Path

from opentower.skills import skill

logger = logging.getLogger("opentower.skills.data_query")


@skill(
    "query_csv",
    description="Load a CSV file and query it with SQL (auto-creates SQLite table from CSV)",
    parameters='{"path": "string (required) — CSV file path", "sql": "string (required) — SQL query (table name is `data`)"}',
)
async def query_csv(path: str = "", sql: str = "") -> dict:
    """Load CSV into SQLite in-memory, run SQL, return results."""
    if not path:
        return {"error": "No CSV path provided"}
    if not sql:
        return {"error": "No SQL query provided"}

    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}

    try:
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return {"error": "CSV is empty"}
            columns = list(rows[0].keys())

        # Create in-memory SQLite
        conn = sqlite3.connect(":memory:")
        # Create table
        col_defs = ", ".join(f'"{c}" TEXT' for c in columns)
        conn.execute(f"CREATE TABLE data ({col_defs})")

        # Insert rows
        placeholders = ", ".join("?" for _ in columns)
        for row in rows:
            values = [row.get(c, "") for c in columns]
            conn.execute(f"INSERT INTO data VALUES ({placeholders})", values)
        conn.commit()

        # Execute query
        cursor = conn.execute(sql)
        result_cols = [d[0] for d in cursor.description] if cursor.description else []
        result_rows = cursor.fetchall()
        conn.close()

        # Format as table
        formatted = []
        for row in result_rows[:100]:  # cap at 100 rows
            formatted.append(dict(zip(result_cols, row)))

        return {
            "columns": result_cols,
            "row_count": len(result_rows),
            "rows": formatted,
            "source": path,
            "total_source_rows": len(rows),
        }

    except sqlite3.OperationalError as e:
        return {"error": f"SQL error: {e}", "available_columns": columns if 'columns' in dir() else []}
    except Exception as e:
        return {"error": str(e)[:300]}


@skill(
    "query_sqlite",
    description="Run a SQL query on an existing SQLite database file",
    parameters='{"path": "string (required) — SQLite .db file path", "sql": "string (required) — SQL query"}',
)
async def query_sqlite(path: str = "", sql: str = "") -> dict:
    """Query an existing SQLite database."""
    if not path or not sql:
        return {"error": "path and sql are required"}

    p = Path(path)
    if not p.exists():
        return {"error": f"Database not found: {path}"}

    try:
        conn = sqlite3.connect(str(p))

        # If asking about schema, also list tables
        if sql.strip().lower().startswith(("pragma", ".tables", "show")):
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            conn.close()
            return {"tables": tables}

        cursor = conn.execute(sql)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()

        formatted = [dict(zip(cols, r)) for r in rows[:200]]
        return {"columns": cols, "row_count": len(rows), "rows": formatted}

    except Exception as e:
        return {"error": str(e)[:300]}


@skill(
    "csv_summary",
    description="Get a quick summary of a CSV file: columns, row count, sample data",
    parameters='{"path": "string (required) — CSV file path"}',
)
async def csv_summary(path: str = "") -> dict:
    """Quick overview of a CSV file."""
    if not path:
        return {"error": "No path provided"}

    p = Path(path)
    if not p.exists():
        return {"error": f"File not found: {path}"}

    try:
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return {"error": "CSV is empty"}

        columns = list(rows[0].keys())
        sample = rows[:5]

        return {
            "path": path,
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "sample_rows": sample,
        }
    except Exception as e:
        return {"error": str(e)[:300]}
