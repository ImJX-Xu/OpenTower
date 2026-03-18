"""MCP Server — expose OpenTower as a protocol node.

Other agents (Claude Desktop, Cursor, VS Code, etc.) connect to
OpenTower via MCP protocol and invoke its Skills as tools.

This is the "toll booth" / "protocol node" model:
- Our Skills become required nodes on other agents' execution paths
- Once integrated, switching cost is high → default position secured
- "协议即软件" — protocol IS the product

Supports:
    - stdio transport (for Claude Desktop, Cursor integration)
    - HTTP/SSE transport (for web-based agents, multi-agent systems)
    - Full MCP spec: tools, resources, prompts
    - Access control per skill
    - Request logging/metrics

Usage::

    # stdio mode (for Claude Desktop integration)
    server = MCPServer(skill_registry)
    await server.start_stdio()

    # HTTP/SSE mode (for web agents)
    server = MCPServer(skill_registry, port=3100)
    await server.start_http()
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from typing import Any

from opentower.skills import SkillRegistry

logger = logging.getLogger("opentower.mcp.server")

_JSONRPC = "2.0"
_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "OpenTower"
_SERVER_VERSION = "3.1"


class MCPServer:
    """Production MCP server — exposes Skills as MCP tools.

    Supports both stdio and HTTP/SSE transports.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        *,
        port: int = 3100,
        expose_skills: list[str] | None = None,
        resources: list[dict] | None = None,
        prompts: list[dict] | None = None,
    ) -> None:
        self._registry = registry
        self._port = port
        self._expose_skills = expose_skills  # None = expose all
        self._resources = resources or []
        self._prompts = prompts or []
        self._running = False
        self._metrics = {"requests": 0, "tool_calls": 0, "errors": 0, "start_time": 0.0}

    # ── stdio Transport ───────────────────────────────────────

    async def start_stdio(self) -> None:
        """Run as stdio MCP server (Claude Desktop, Cursor, etc.)."""
        self._running = True
        self._metrics["start_time"] = time.time()

        tool_count = len(self._get_exposed_tools())
        logger.info("MCP Server (stdio) started — %d tools exposed", tool_count)

        # Set up stdin/stdout streams
        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(w_transport, w_protocol, None, loop)

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
                request = json.loads(line.decode("utf-8"))
                response = await self._handle(request)
                if response is not None:
                    out = json.dumps(response, ensure_ascii=False) + "\n"
                    writer.write(out.encode("utf-8"))
                    await writer.drain()
            except json.JSONDecodeError:
                logger.warning("Invalid JSON on stdin")
            except Exception:
                logger.exception("MCP stdio error")

    # ── HTTP/SSE Transport ────────────────────────────────────

    async def start_http(self) -> None:
        """Run as HTTP MCP server with SSE support."""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp required for HTTP transport: pip install aiohttp")
            return

        self._running = True
        self._metrics["start_time"] = time.time()

        app = web.Application()
        app.router.add_post("/mcp", self._http_handle)
        app.router.add_get("/mcp/sse", self._sse_handle)
        app.router.add_get("/health", self._health_handle)
        app.router.add_get("/metrics", self._metrics_handle)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()

        tool_count = len(self._get_exposed_tools())
        logger.info("MCP Server (HTTP) started on port %d — %d tools exposed", self._port, tool_count)

    async def _http_handle(self, request):
        """Handle JSON-RPC over HTTP POST."""
        from aiohttp import web
        self._metrics["requests"] += 1
        try:
            data = await request.json()
            response = await self._handle(data)
            if response:
                return web.json_response(response)
            return web.json_response({"ok": True})
        except Exception as e:
            self._metrics["errors"] += 1
            return web.json_response(
                {"jsonrpc": _JSONRPC, "id": None, "error": {"code": -32603, "message": str(e)}},
                status=500,
            )

    async def _sse_handle(self, request):
        """Server-Sent Events endpoint for real-time MCP communication."""
        from aiohttp import web
        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        await response.prepare(request)

        # Send initial connection event
        await self._sse_write(response, "connected", {
            "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
            "tools": len(self._get_exposed_tools()),
        })

        # Keep connection alive
        try:
            while self._running:
                await asyncio.sleep(30)
                await self._sse_write(response, "ping", {"time": time.time()})
        except (ConnectionResetError, asyncio.CancelledError):
            pass

        return response

    @staticmethod
    async def _sse_write(response, event: str, data: dict) -> None:
        await response.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())

    async def _health_handle(self, request):
        from aiohttp import web
        uptime = time.time() - self._metrics["start_time"] if self._metrics["start_time"] else 0
        return web.json_response({
            "status": "ok", "server": _SERVER_NAME, "version": _SERVER_VERSION,
            "uptime_seconds": round(uptime), "tools": len(self._get_exposed_tools()),
            "metrics": self._metrics,
        })

    async def _metrics_handle(self, request):
        from aiohttp import web
        return web.json_response(self._metrics)

    # ── Core Protocol Handler ─────────────────────────────────

    async def _handle(self, request: dict) -> dict | None:
        """Process a JSON-RPC request — implements full MCP spec."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        self._metrics["requests"] += 1

        # Notifications (no id) → no response
        if req_id is None:
            logger.debug("MCP notification: %s", method)
            return None

        try:
            if method == "initialize":
                return self._ok(req_id, {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"subscribe": False, "listChanged": True} if self._resources else {},
                        "prompts": {"listChanged": True} if self._prompts else {},
                    },
                    "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
                })

            if method == "ping":
                return self._ok(req_id, {})

            # ── Tools ──
            if method == "tools/list":
                return self._ok(req_id, {"tools": self._get_exposed_tools()})

            if method == "tools/call":
                return await self._handle_tool_call(req_id, params)

            # ── Resources ──
            if method == "resources/list":
                return self._ok(req_id, {"resources": self._resources})

            if method == "resources/read":
                return await self._handle_resource_read(req_id, params)

            # ── Prompts ──
            if method == "prompts/list":
                return self._ok(req_id, {"prompts": self._prompts})

            if method == "prompts/get":
                return await self._handle_prompt_get(req_id, params)

            # Unknown method
            return self._error(req_id, -32601, f"Unknown method: {method}")

        except Exception as e:
            self._metrics["errors"] += 1
            logger.exception("MCP handler error: %s", method)
            return self._error(req_id, -32603, f"Internal error: {e}")

    # ── Tool Execution ────────────────────────────────────────

    async def _handle_tool_call(self, req_id: Any, params: dict) -> dict:
        """Execute a tool call with full error handling."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        self._metrics["tool_calls"] += 1
        logger.info("MCP tool call: %s(%s)", tool_name, str(arguments)[:80])

        # Check access
        if self._expose_skills and tool_name not in self._expose_skills:
            return self._error(req_id, -32602, f"Tool '{tool_name}' not exposed")

        if tool_name not in self._registry:
            return self._error(req_id, -32602, f"Unknown tool: {tool_name}")

        try:
            result = await self._registry.call(tool_name, **arguments)

            # Format as MCP content blocks
            content = []
            if isinstance(result, dict):
                if "error" in result:
                    content.append({"type": "text", "text": f"Error: {result['error']}"})
                    return self._ok(req_id, {"content": content, "isError": True})
                else:
                    text = json.dumps(result, ensure_ascii=False, default=str)
                    content.append({"type": "text", "text": text})
            else:
                content.append({"type": "text", "text": str(result)})

            return self._ok(req_id, {"content": content, "isError": False})

        except Exception as e:
            self._metrics["errors"] += 1
            content = [{"type": "text", "text": f"Execution error: {e}"}]
            return self._ok(req_id, {"content": content, "isError": True})

    # ── Resource Reading ──────────────────────────────────────

    async def _handle_resource_read(self, req_id: Any, params: dict) -> dict:
        """Read a resource by URI."""
        uri = params.get("uri", "")
        for res in self._resources:
            if res.get("uri") == uri:
                # Static resource
                return self._ok(req_id, {
                    "contents": [{"uri": uri, "text": res.get("content", ""), "mimeType": res.get("mimeType", "text/plain")}]
                })
        return self._error(req_id, -32602, f"Resource not found: {uri}")

    # ── Prompt Retrieval ──────────────────────────────────────

    async def _handle_prompt_get(self, req_id: Any, params: dict) -> dict:
        """Get a prompt by name."""
        prompt_name = params.get("name", "")
        for prompt in self._prompts:
            if prompt.get("name") == prompt_name:
                return self._ok(req_id, {
                    "description": prompt.get("description", ""),
                    "messages": prompt.get("messages", []),
                })
        return self._error(req_id, -32602, f"Prompt not found: {prompt_name}")

    # ── Tool listing ──────────────────────────────────────────

    def _get_exposed_tools(self) -> list[dict]:
        """Get list of tools to expose via MCP."""
        tools = []
        for name in self._registry.available:
            if self._expose_skills and name not in self._expose_skills:
                continue

            skill = self._registry[name]
            tool: dict[str, Any] = {
                "name": name,
                "description": skill.description,
            }

            # Build proper JSON Schema for input
            if skill.parameters:
                try:
                    props = json.loads(skill.parameters)
                    tool["inputSchema"] = {"type": "object", "properties": props}
                except json.JSONDecodeError:
                    tool["inputSchema"] = {
                        "type": "object",
                        "description": skill.parameters,
                    }
            else:
                tool["inputSchema"] = {"type": "object", "properties": {}}

            tools.append(tool)

        return tools

    # ── JSON-RPC helpers ──────────────────────────────────────

    @staticmethod
    def _ok(req_id: Any, result: dict) -> dict:
        return {"jsonrpc": _JSONRPC, "id": req_id, "result": result}

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": _JSONRPC, "id": req_id, "error": {"code": code, "message": message}}

    def stop(self) -> None:
        self._running = False
