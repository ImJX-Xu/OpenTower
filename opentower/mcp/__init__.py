"""MCP package — Model Context Protocol dual-mode support.

Client: Connect to external MCP servers, discover tools/resources/prompts.
Server: Expose OpenTower's Skills as an MCP endpoint (stdio + HTTP/SSE).
"""

from .client import MCPClient, MCPServerInfo
from .server import MCPServer

__all__ = ["MCPClient", "MCPServer", "MCPServerInfo"]
