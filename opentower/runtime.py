"""Runtime — the thin boot loader.

Loads config → inits LLM → discovers skills → connects MCP → starts channels → runs agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

import aiosqlite

from opentower.config import load_config, Config
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory
from opentower.agent import Agent
from opentower.skills import SkillRegistry
from opentower.channels.cli import CLIChannel
from opentower.scheduler import Scheduler
from opentower.mcp.client import MCPClient
from opentower.mcp.server import MCPServer

logger = logging.getLogger("opentower")

C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


async def run(config_path: str = "config.yaml") -> None:
    """Boot the Agent OS."""
    config = load_config(config_path)

    print(f"\n{C_BOLD}  🏢 OpenTower Agent OS v{config.agent.version}{C_RESET}")
    print(f"  {C_DIM}{'─' * 45}{C_RESET}")

    # ── LLM ─────────────────────────────────────────────────
    llm = LLMClient(
        base_url=config.agent.llm.base_url,
        api_key=config.agent.llm.api_key,
        model=config.agent.llm.model,
    )
    print(f"  {C_DIM}LLM     : {config.agent.llm.base_url} ({config.agent.llm.model}){C_RESET}")

    # ── Memory ──────────────────────────────────────────────
    mem_db = await aiosqlite.connect(config.agent.memory.path)
    memory = NodeMemory("agent", mem_db, max_history=config.agent.memory.max_history)
    await memory.init()

    # ── Skills ──────────────────────────────────────────────
    registry = SkillRegistry()
    registry.load_from_config(config.enabled_skills)

    # ── MCP Client (connect to external MCP servers) ───────
    mcp_client = MCPClient()
    mcp_configs = registry.mcp_server_configs
    if mcp_configs:
        print(f"  {C_DIM}MCP     : connecting to {len(mcp_configs)} server(s)...{C_RESET}")
        await mcp_client.connect_from_config(mcp_configs)
        # Merge MCP-discovered skills into registry
        for name, skill in mcp_client.discovered_skills.items():
            registry.register(skill)
        status = mcp_client.status
        for sname, sinfo in status.items():
            health = "✓" if sinfo["healthy"] else "✗"
            print(f"  {C_DIM}  {health} {sname}: {sinfo['tools']} tools, "
                  f"{sinfo['resources']} resources{C_RESET}")

    print(f"  {C_DIM}Skills  : {len(registry.available)} loaded "
          f"({', '.join(registry.available[:8])}{'...' if len(registry.available) > 8 else ''}){C_RESET}")

    # ── Agent ───────────────────────────────────────────────
    agent = Agent(config, llm, memory=memory, skills=registry.all_skills)

    # ── MCP Server (expose our skills to other agents) ─────
    mcp_server = None
    if config.mcp_server.enabled:
        expose = config.mcp_server.expose_skills or None
        mcp_server = MCPServer(registry, port=config.mcp_server.port, expose_skills=expose)
        transport = config.mcp_server.transport
        if transport == "http":
            await mcp_server.start_http()
            print(f"  {C_DIM}MCP Srv : HTTP/SSE on port {config.mcp_server.port}{C_RESET}")
        else:
            # stdio mode runs as the main loop — only when no channels
            print(f"  {C_DIM}MCP Srv : stdio mode{C_RESET}")

    # ── Scheduler ───────────────────────────────────────────
    scheduler = None
    if config.heartbeat.enabled:
        async def on_wake():
            logger.debug("Heartbeat wake")

        scheduler = Scheduler(interval=config.heartbeat.interval, on_wake=on_wake)
        for sched in config.schedules:
            scheduler.add_schedule(sched.cron, sched.action, lambda a: agent.run(a))
        await scheduler.start()
        print(f"  {C_DIM}Heartbeat: every {config.heartbeat.interval}s{C_RESET}")

    # ── Channels ────────────────────────────────────────────
    channels = []
    for ch_config in config.enabled_channels:
        if ch_config.type == "cli":
            channels.append(CLIChannel())
        elif ch_config.type == "webhook":
            from opentower.channels.webhook import WebhookChannel
            wh = WebhookChannel(port=ch_config.port)
            await wh.start()
            channels.append(wh)
        elif ch_config.type == "feishu":
            from opentower.channels.feishu import FeishuChannel
            fei = FeishuChannel(
                app_id=ch_config.token or "",
                app_secret=getattr(ch_config, "app_secret", ""),
                port=ch_config.port,
            )
            await fei.start()
            channels.append(fei)

    ch_names = [type(c).__name__ for c in channels]
    print(f"  {C_DIM}Channels: {', '.join(ch_names)}{C_RESET}")
    print(f"\n  {C_GREEN}✓ Agent online. Ready.{C_RESET}")
    print(f"  {C_DIM}Type 'exit' to shutdown.{C_RESET}\n")

    # ── Main loop ───────────────────────────────────────────
    try:
        # If MCP Server in stdio mode and no interactive channels, run MCP server
        if mcp_server and config.mcp_server.transport == "stdio" and not channels:
            await mcp_server.start_stdio()
        else:
            for channel in channels:
                async for msg in channel.listen():
                    ctx = await memory.get_context(n=10) if memory else ""
                    response = await agent.run(msg.text, context=ctx)
                    await channel.send(response)

    except KeyboardInterrupt:
        print(f"\n{C_DIM}Interrupted.{C_RESET}")

    # ── Cleanup ─────────────────────────────────────────────
    if scheduler:
        await scheduler.stop()
    if mcp_server:
        mcp_server.stop()
    await mcp_client.disconnect_all()
    for ch in channels:
        await ch.stop()
    await mem_db.close()
    print(f"{C_DIM}Goodbye.{C_RESET}")


def main():
    """CLI entry point."""
    config_path = os.environ.get("OPENTOWER_CONFIG", "config.yaml")
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(run(config_path))


if __name__ == "__main__":
    main()
