"""MCP package — Model Context Protocol dual-mode support.

Client: Connect to external MCP servers, auto-discover their tools as Skills.
Server: Expose OpenTower's Skills as an MCP-compatible endpoint.
"""

from .client import MCPClient

__all__ = ["MCPClient"]
