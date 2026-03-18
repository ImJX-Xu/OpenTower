"""Action: Shell Execute — run local commands with safety guardrails."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("opentower.actions.shell")

# Commands that are always blocked
_BLOCKED_PATTERNS = [
    "rm -rf",
    "rmdir /s",
    "del /f",
    "format ",
    "mkfs",
    ":(){:|:&};:",  # fork bomb
]

_TIMEOUT_SECONDS = 30


async def shell_execute(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a shell command and return stdout/stderr/exit_code.

    Payload:
        command (str): The command to run.

    Safety:
        - Blocked patterns are rejected immediately.
        - Timeout after 30 seconds.
    """
    command = payload.get("command", "")
    if not command:
        return {"error": "Missing 'command' in payload", "exit_code": -1}

    # Safety check
    cmd_lower = command.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return {
                "error": f"Blocked: command matches dangerous pattern '{pattern}'",
                "exit_code": -1,
            }

    logger.info("Shell executing: %s", command)

    try:
        import os
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        # Force UTF-8 output on Windows
        if os.name == "nt":
            env["CHCP"] = "65001"
            command = f"chcp 65001 >nul && {command}"
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=_TIMEOUT_SECONDS
        )
        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace").strip(),
            "stderr": stderr_bytes.decode("utf-8", errors="replace").strip(),
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore[union-attr]
        return {"error": f"Command timed out after {_TIMEOUT_SECONDS}s", "exit_code": -1}
    except Exception as exc:
        return {"error": str(exc), "exit_code": -1}


def register_shell_actions(registry) -> None:  # noqa: ANN001
    """Register all shell actions into the given ActionRegistry."""
    registry._handlers["shell_execute"] = shell_execute
