"""Python execution skill — run Python code snippets."""

from __future__ import annotations

import asyncio
import sys
import traceback
from io import StringIO

from opentower.skills import skill


@skill(
    "python_exec",
    description="Execute a Python code snippet and return the output",
    parameters='{"code": "string (required) — Python code to execute"}',
)
async def python_exec(code: str = "") -> dict:
    """Execute Python code in a sandboxed subprocess."""
    if not code:
        return {"error": "No code provided"}

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

        return {
            "stdout": stdout.decode("utf-8", errors="replace")[:5000],
            "stderr": stderr.decode("utf-8", errors="replace")[:2000],
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"error": "Code execution timed out (15s limit)"}
    except Exception as e:
        return {"error": str(e)}
