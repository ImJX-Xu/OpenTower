"""MCP Client — production-grade MCP server connector.

Launches MCP servers as subprocesses (stdio transport), performs
full protocol handshake (initialize → initialized → discover),
supports tools, resources, and prompts.

Features:
    - Auto-reconnect on server crash
    - Health checking with ping
    - Full tool/resource/prompt discovery
    - Capability negotiation
    - Multi-server management
    - Config-driven server startup

Usage::

    client = MCPClient()
    await client.connect_from_config([
        {"name": "github", "command": "npx -y @anthropic/mcp-github", "env": {"GITHUB_TOKEN": "..."}},
    ])
    skills = client.discovered_skills
    result = await client.call_tool("github", "list_repos", owner="user")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from dataclasses import dataclass, field

from opentower.skills import SkillInfo

logger = logging.getLogger("opentower.mcp.client")

_JSONRPC = "2.0"
_PROTOCOL_VERSION = "2024-11-05"
_INIT_TIMEOUT = 15.0
_CALL_TIMEOUT = 30.0


@dataclass
class MCPServerInfo:
    """Metadata for a connected MCP server."""
    name: str
    command: str
    protocol_version: str = ""
    server_name: str = ""
    server_version: str = ""
    capabilities: dict = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)
    healthy: bool = False


class MCPClient:
    """Production MCP client — manages multiple MCP server connections."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerInfo] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._request_id = 0
        self._skills: dict[str, SkillInfo] = {}

    # ── Config-driven startup ─────────────────────────────────

    async def connect_from_config(self, server_configs: list[dict]) -> None:
        """Connect to multiple MCP servers from config entries.

        Each config entry: {"name": str, "command": str, "env": dict}
        """
        tasks = []
        for sc in server_configs:
            name = sc.get("name", "")
            command = sc.get("command", "")
            env = sc.get("env", {})
            if name and command:
                tasks.append(self.connect(command, name=name, env=env))
            else:
                logger.warning("Skipping MCP config (missing name/command): %s", sc)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.error("MCP connect failed: %s", r)

    # ── Single server connect ─────────────────────────────────

    async def connect(
        self,
        command: str,
        *,
        name: str = "",
        env: dict = None,
    ) -> MCPServerInfo:
        """Launch an MCP server and perform full protocol handshake."""
        name = name or command.split()[-1].replace("@", "").replace("/", "_")

        # Kill existing process if reconnecting
        if name in self._processes:
            await self._disconnect_one(name)

        logger.info("MCP connecting: %s → %s", name, command[:80])

        proc_env = {**os.environ}
        if env:
            # Resolve env vars that reference other env vars
            for k, v in env.items():
                if isinstance(v, str):
                    proc_env[k] = v
                    
        info = MCPServerInfo(name=name, command=command)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
            )
            self._processes[name] = proc

            # ── Protocol handshake ──
            # 1. initialize
            init_resp = await self._request(proc, "initialize", {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {
                    "roots": {"listChanged": True},
                },
                "clientInfo": {"name": "OpenTower", "version": "3.1"},
            }, timeout=_INIT_TIMEOUT)

            result = init_resp.get("result", {})
            info.protocol_version = result.get("protocolVersion", "unknown")
            info.server_name = result.get("serverInfo", {}).get("name", name)
            info.server_version = result.get("serverInfo", {}).get("version", "?")
            info.capabilities = result.get("capabilities", {})

            logger.info("MCP %s: handshake OK (server=%s v%s, proto=%s)",
                        name, info.server_name, info.server_version, info.protocol_version)

            # 2. notifications/initialized
            await self._notify(proc, "notifications/initialized", {})

            # 3. Discover capabilities
            if "tools" in info.capabilities:
                info.tools = await self._discover_tools(proc, name)
                self._register_tools(name, proc, info.tools)

            if "resources" in info.capabilities:
                info.resources = await self._discover_resources(proc, name)

            if "prompts" in info.capabilities:
                info.prompts = await self._discover_prompts(proc, name)

            # 4. Health check
            info.healthy = True
            self._servers[name] = info

            logger.info("MCP %s: ready — %d tools, %d resources, %d prompts",
                        name, len(info.tools), len(info.resources), len(info.prompts))

            return info

        except Exception as e:
            logger.error("MCP connect failed (%s): %s", name, e)
            info.healthy = False
            self._servers[name] = info
            return info

    # ── Discovery ─────────────────────────────────────────────

    async def _discover_tools(self, proc, name: str) -> list[dict]:
        resp = await self._request(proc, "tools/list", {})
        tools = resp.get("result", {}).get("tools", [])
        logger.debug("MCP %s: %d tools discovered", name, len(tools))
        return tools

    async def _discover_resources(self, proc, name: str) -> list[dict]:
        resp = await self._request(proc, "resources/list", {})
        resources = resp.get("result", {}).get("resources", [])
        logger.debug("MCP %s: %d resources discovered", name, len(resources))
        return resources

    async def _discover_prompts(self, proc, name: str) -> list[dict]:
        resp = await self._request(proc, "prompts/list", {})
        prompts = resp.get("result", {}).get("prompts", [])
        logger.debug("MCP %s: %d prompts discovered", name, len(prompts))
        return prompts

    # ── Tool registration as Skills ───────────────────────────

    def _register_tools(self, server_name: str, proc, tools: list[dict]) -> None:
        """Convert MCP tools to Skills and register them."""
        for tool in tools:
            raw_name = tool["name"]
            skill_name = f"mcp_{server_name}_{raw_name}"
            desc = tool.get("description", raw_name)
            schema = tool.get("inputSchema", {})

            # Build parameters string from JSON Schema
            props = schema.get("properties", {})
            required = schema.get("required", [])
            param_parts = []
            for pname, pdef in props.items():
                ptype = pdef.get("type", "any")
                pdesc = pdef.get("description", "")
                req = " (required)" if pname in required else ""
                param_parts.append(f'"{pname}": "{ptype}{req} — {pdesc}"')
            params_str = "{" + ", ".join(param_parts) + "}" if param_parts else ""

            skill_info = SkillInfo(
                name=skill_name,
                description=f"[MCP:{server_name}] {desc}",
                parameters=params_str[:400],
                execute=self._make_tool_caller(proc, raw_name, server_name),
            )
            self._skills[skill_name] = skill_info

    def _make_tool_caller(self, proc, tool_name: str, server_name: str):
        """Create an async callable that invokes an MCP tool."""
        async def call_tool(**kwargs: Any) -> dict:
            # Check if process is alive
            if proc.returncode is not None:
                return {"error": f"MCP server '{server_name}' has exited (code={proc.returncode})"}
            try:
                resp = await self._request(proc, "tools/call", {
                    "name": tool_name,
                    "arguments": kwargs,
                }, timeout=_CALL_TIMEOUT)

                if "error" in resp:
                    return {"error": f"MCP error: {resp['error']}"}

                result = resp.get("result", {})
                content = result.get("content", [])
                is_error = result.get("isError", False)

                # Extract text content
                texts = []
                images = []
                for item in content if isinstance(content, list) else []:
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        images.append(item.get("data", "")[:100] + "...")
                    elif item.get("type") == "resource":
                        texts.append(f"[resource: {item.get('resource', {}).get('uri', '?')}]")

                output = "\n".join(texts) if texts else str(result)[:2000]
                result_dict = {"output": output}
                if images:
                    result_dict["images"] = images
                if is_error:
                    result_dict["error"] = output

                return result_dict

            except Exception as e:
                return {"error": f"MCP tool '{tool_name}' failed: {e}"}

        return call_tool

    # ── Resource reading ──────────────────────────────────────

    async def read_resource(self, server_name: str, uri: str) -> dict:
        """Read a resource from an MCP server."""
        proc = self._processes.get(server_name)
        if not proc or proc.returncode is not None:
            return {"error": f"MCP server '{server_name}' not connected"}

        resp = await self._request(proc, "resources/read", {"uri": uri})
        if "error" in resp:
            return {"error": str(resp["error"])}

        contents = resp.get("result", {}).get("contents", [])
        texts = []
        for c in contents:
            if "text" in c:
                texts.append(c["text"])
            elif "blob" in c:
                texts.append(f"[binary: {c.get('mimeType', 'unknown')}]")
        return {"uri": uri, "content": "\n".join(texts)}

    # ── Prompt execution ──────────────────────────────────────

    async def get_prompt(self, server_name: str, prompt_name: str, arguments: dict = None) -> dict:
        """Get a prompt from an MCP server."""
        proc = self._processes.get(server_name)
        if not proc or proc.returncode is not None:
            return {"error": f"MCP server '{server_name}' not connected"}

        resp = await self._request(proc, "prompts/get", {
            "name": prompt_name,
            "arguments": arguments or {},
        })
        if "error" in resp:
            return {"error": str(resp["error"])}

        result = resp.get("result", {})
        messages = result.get("messages", [])
        return {
            "description": result.get("description", ""),
            "messages": messages,
        }

    # ── Health & Status ───────────────────────────────────────

    async def ping(self, server_name: str) -> bool:
        """Check if an MCP server is alive."""
        proc = self._processes.get(server_name)
        if not proc or proc.returncode is not None:
            return False
        try:
            resp = await self._request(proc, "ping", {}, timeout=5.0)
            return "result" in resp
        except Exception:
            return False

    async def reconnect(self, server_name: str) -> bool:
        """Reconnect to a crashed MCP server."""
        info = self._servers.get(server_name)
        if not info:
            return False
        logger.info("MCP reconnecting: %s", server_name)
        new_info = await self.connect(info.command, name=server_name)
        return new_info.healthy

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all connected servers."""
        results = {}
        for name in list(self._servers):
            alive = await self.ping(name)
            results[name] = alive
            if not alive and self._servers[name].healthy:
                logger.warning("MCP %s: unhealthy, attempting reconnect", name)
                await self.reconnect(name)
                results[name] = await self.ping(name)
        return results

    @property
    def status(self) -> dict:
        """Get status summary of all MCP servers."""
        return {
            name: {
                "healthy": info.healthy,
                "server": info.server_name,
                "version": info.server_version,
                "tools": len(info.tools),
                "resources": len(info.resources),
                "prompts": len(info.prompts),
            }
            for name, info in self._servers.items()
        }

    @property
    def discovered_skills(self) -> dict[str, SkillInfo]:
        """All MCP-discovered skills."""
        return dict(self._skills)

    # ── JSON-RPC transport ────────────────────────────────────

    async def _request(self, proc, method: str, params: dict, timeout: float = _CALL_TIMEOUT) -> dict:
        """Send JSON-RPC request and wait for response."""
        self._request_id += 1
        req_id = self._request_id

        msg = {"jsonrpc": _JSONRPC, "id": req_id, "method": method, "params": params}
        line = json.dumps(msg) + "\n"

        try:
            proc.stdin.write(line.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            return {"error": "MCP server pipe broken"}

        # Read response, skipping notifications
        try:
            while True:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
                if not raw:
                    return {"error": "MCP server closed"}
                resp = json.loads(raw.decode("utf-8"))
                # Skip notifications (no id)
                if "id" in resp:
                    return resp
        except asyncio.TimeoutError:
            return {"error": f"MCP timeout after {timeout}s"}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}"}

    async def _notify(self, proc, method: str, params: dict) -> None:
        """Send JSON-RPC notification (no response expected)."""
        msg = {"jsonrpc": _JSONRPC, "method": method, "params": params}
        line = json.dumps(msg) + "\n"
        try:
            proc.stdin.write(line.encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            logger.warning("Failed to send notification: pipe broken")

    # ── Cleanup ───────────────────────────────────────────────

    async def _disconnect_one(self, name: str) -> None:
        proc = self._processes.pop(name, None)
        if proc:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                proc.kill()
        # Remove associated skills
        to_remove = [k for k in self._skills if k.startswith(f"mcp_{name}_")]
        for k in to_remove:
            del self._skills[k]
        self._servers.pop(name, None)
        logger.info("MCP disconnected: %s", name)

    async def disconnect_all(self) -> None:
        for name in list(self._processes):
            await self._disconnect_one(name)
