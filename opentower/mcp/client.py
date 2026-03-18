"""MCP Client — connect to external MCP servers and import their tools as Skills.

Launches MCP servers as subprocesses (via stdio transport), sends
JSON-RPC messages to discover tools, and wraps them as callable Skills.

Usage::

    client = MCPClient()
    skills = await client.connect("npx -y @anthropic/mcp-github")
    # skills now contains SkillInfo entries for every MCP tool
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from opentower.skills import SkillInfo

logger = logging.getLogger("opentower.mcp.client")

_JSONRPC_VERSION = "2.0"


class MCPClient:
    """Connect to MCP servers via stdio and expose their tools as Skills."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._request_id = 0

    async def connect(self, command: str, *, name: str = "", env: dict = None) -> list[SkillInfo]:
        """Launch an MCP server process and discover its tools.

        Args:
            command: Shell command to launch the MCP server.
            name: Friendly name for this server.
            env: Extra environment variables.

        Returns:
            List of SkillInfo for each discovered tool.
        """
        name = name or command.split()[-1]
        logger.info("MCP connecting: %s (%s)", name, command[:60])

        proc_env = {**os.environ}
        if env:
            proc_env.update(env)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
            )
            self._processes[name] = proc

            # Initialize
            await self._send(proc, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "OpenTower", "version": "3.1"},
            })

            init_response = await self._receive(proc)
            logger.debug("MCP init response: %s", str(init_response)[:200])

            # Send initialized notification
            await self._notify(proc, "notifications/initialized", {})

            # Discover tools
            await self._send(proc, "tools/list", {})
            tools_response = await self._receive(proc)

            tools = tools_response.get("result", {}).get("tools", [])
            logger.info("MCP %s: discovered %d tools", name, len(tools))

            # Convert to SkillInfo
            skills = []
            for tool in tools:
                tool_name = f"mcp_{name}_{tool['name']}"
                description = tool.get("description", tool["name"])
                schema = tool.get("inputSchema", {})
                params = json.dumps(schema.get("properties", {}), ensure_ascii=False)[:300]

                # Create callable wrapper
                skill_info = SkillInfo(
                    name=tool_name,
                    description=f"[MCP:{name}] {description}",
                    parameters=params,
                    execute=self._make_caller(proc, tool["name"]),
                )
                skills.append(skill_info)

            return skills

        except FileNotFoundError:
            logger.error("MCP command not found: %s", command)
            return []
        except Exception as e:
            logger.error("MCP connect failed (%s): %s", name, e)
            return []

    def _make_caller(self, proc: asyncio.subprocess.Process, tool_name: str):
        """Create an async callable that invokes an MCP tool."""
        async def call_tool(**kwargs: Any) -> dict:
            try:
                await self._send(proc, "tools/call", {
                    "name": tool_name,
                    "arguments": kwargs,
                })
                resp = await self._receive(proc)
                result = resp.get("result", {})

                # Extract content from MCP response
                content = result.get("content", [])
                if content and isinstance(content, list):
                    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    return {"output": "\n".join(texts), "raw": content}
                return {"output": str(result)[:2000]}

            except Exception as e:
                return {"error": f"MCP tool '{tool_name}' failed: {e}"}

        return call_tool

    async def _send(self, proc: asyncio.subprocess.Process, method: str, params: dict) -> None:
        """Send a JSON-RPC request via stdin."""
        self._request_id += 1
        msg = {
            "jsonrpc": _JSONRPC_VERSION,
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(msg) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()

    async def _notify(self, proc: asyncio.subprocess.Process, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no id)."""
        msg = {
            "jsonrpc": _JSONRPC_VERSION,
            "method": method,
            "params": params,
        }
        line = json.dumps(msg) + "\n"
        proc.stdin.write(line.encode("utf-8"))
        await proc.stdin.drain()

    async def _receive(self, proc: asyncio.subprocess.Process, timeout: float = 10.0) -> dict:
        """Read a JSON-RPC response from stdout."""
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not line:
                return {"error": "MCP server closed connection"}
            return json.loads(line.decode("utf-8"))
        except asyncio.TimeoutError:
            return {"error": "MCP response timeout"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON from MCP server"}

    async def disconnect_all(self) -> None:
        """Terminate all MCP server processes."""
        for name, proc in self._processes.items():
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()
            logger.info("MCP disconnected: %s", name)
        self._processes.clear()
