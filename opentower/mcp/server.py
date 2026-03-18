"""MCP Server — expose OpenTower's Skills as an MCP-compatible endpoint.

Other agents (Claude, Cursor, etc.) can connect to OpenTower
via the MCP protocol and call any registered Skill.

This is the "toll booth" model: our Skills become
required nodes on other agents' execution paths.

Usage::

    server = MCPServer(skill_registry, port=3100)
    await server.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from opentower.skills import SkillRegistry

logger = logging.getLogger("opentower.mcp.server")

_JSONRPC_VERSION = "2.0"


class MCPServer:
    """Expose Skills as MCP tools via stdio or HTTP transport.

    Currently implements stdio transport (read from stdin, write to stdout).
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry
        self._running = False

    async def start_stdio(self) -> None:
        """Run as stdio MCP server (for integration with Claude, etc.)."""
        self._running = True
        logger.info("MCP Server started (stdio mode, %d skills)", len(self._registry.available))

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, __import__('sys').stdin)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, __import__('sys').stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break

                request = json.loads(line.decode("utf-8"))
                response = await self._handle_request(request)

                if response is not None:
                    writer.write((json.dumps(response) + "\n").encode("utf-8"))
                    await writer.drain()

            except json.JSONDecodeError:
                logger.warning("Invalid JSON received")
            except Exception:
                logger.exception("MCP server error")

    async def _handle_request(self, request: dict) -> dict | None:
        """Process a JSON-RPC request."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        # Notifications (no id) don't get responses
        if req_id is None:
            return None

        if method == "initialize":
            return self._response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "OpenTower", "version": "3.1"},
            })

        if method == "tools/list":
            tools = []
            for name in self._registry.available:
                skill = self._registry[name]
                tool = {
                    "name": name,
                    "description": skill.description,
                }
                if skill.parameters:
                    try:
                        tool["inputSchema"] = {
                            "type": "object",
                            "properties": json.loads(skill.parameters),
                        }
                    except json.JSONDecodeError:
                        tool["inputSchema"] = {"type": "object"}
                tools.append(tool)

            return self._response(req_id, {"tools": tools})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})

            result = await self._registry.call(tool_name, **arguments)

            # Format as MCP content
            content = [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]
            is_error = "error" in result

            return self._response(req_id, {
                "content": content,
                "isError": is_error,
            })

        # Unknown method
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }

    @staticmethod
    def _response(req_id: Any, result: dict) -> dict:
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": req_id,
            "result": result,
        }

    def stop(self) -> None:
        self._running = False
