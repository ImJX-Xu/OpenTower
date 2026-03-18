"""Shell skill — execute shell commands.

The most fundamental skill: subprocess execution.
"""

from __future__ import annotations

import asyncio
import logging
import os

from opentower.skills import skill

logger = logging.getLogger("opentower.skills.shell")

_TIMEOUT = 30  # seconds


@skill(
    "shell",
    description="Execute a shell command and return stdout/stderr/exit_code",
    parameters='{"command": "string (required) — the shell command to run"}',
)
async def shell_execute(command: str = "") -> dict:
    """Execute a shell command via subprocess."""
    if not command:
        return {"error": "No command provided"}

    logger.info("Shell: %s", command[:80])

    try:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        if os.name == "nt":
            command = f"chcp 65001 >nul && {command}"

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=_TIMEOUT
        )

        stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        return {
            "stdout": stdout[:5000],
            "stderr": stderr[:2000] if stderr else "",
            "exit_code": proc.returncode,
        }

    except asyncio.TimeoutError:
        return {"error": f"Command timed out after {_TIMEOUT}s", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}
