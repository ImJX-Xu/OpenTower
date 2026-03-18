"""Configuration — flat YAML-driven config for the Agent OS.

No hierarchy, no rigid roles. Just: agent + skills + channels + heartbeat.
Supports environment variable interpolation via ${VAR:-default} syntax.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


def _interpolate_env(value: Any) -> Any:
    """Recursively interpolate ${VAR:-default} patterns in strings."""
    if isinstance(value, str):
        def _replace(m):
            var = m.group(1)
            default = m.group(3) if m.group(3) is not None else ""
            return os.environ.get(var, default)
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:(:-)([^}]*))?\}", _replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


# ── Models ─────────────────────────────────────────────────────

class LLMConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "no-key"
    model: str = "default"
    max_tokens: int = 2048
    temperature: float = 0.3


class MemoryConfig(BaseModel):
    backend: str = "sqlite"
    path: str = "opentower.db"
    max_history: int = 50


class AgentConfig(BaseModel):
    name: str = "OpenTower"
    version: str = "3.0"
    system_prompt: str = "You are a helpful AI agent."
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)


class SkillConfig(BaseModel):
    name: str
    type: str = "python"  # python | cli | mcp
    module: Optional[str] = None
    command: Optional[str] = None
    description: str = ""
    enabled: bool = True
    env: dict[str, str] = Field(default_factory=dict)


class ChannelConfig(BaseModel):
    type: str  # cli | telegram | webhook
    enabled: bool = True
    token: Optional[str] = None
    port: int = 8080


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    interval: int = 300
    on_wake: list[str] = Field(default_factory=list)


class ScheduleConfig(BaseModel):
    cron: str
    action: str


class MCPServerConfig(BaseModel):
    """Config for exposing OpenTower as an MCP server."""
    enabled: bool = False
    transport: str = "stdio"  # stdio | http
    port: int = 3100
    expose_skills: list[str] = Field(default_factory=list)  # empty = expose all


class Config(BaseModel):
    """Root configuration for the Agent OS."""
    agent: AgentConfig = Field(default_factory=AgentConfig)
    skills: list[SkillConfig] = Field(default_factory=list)
    channels: list[ChannelConfig] = Field(default_factory=list)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    schedules: list[ScheduleConfig] = Field(default_factory=list)
    mcp_server: MCPServerConfig = Field(default_factory=MCPServerConfig)

    @property
    def enabled_skills(self) -> list[SkillConfig]:
        return [s for s in self.skills if s.enabled]

    @property
    def enabled_channels(self) -> list[ChannelConfig]:
        return [c for c in self.channels if c.enabled]


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load and validate config.yaml with env interpolation."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw = _interpolate_env(raw)
    return Config(**raw)
