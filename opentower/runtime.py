"""Runtime — the thin boot loader.

Loads config → inits LLM → discovers skills → starts channels → runs agent.
Under 80 lines of actual code. That's the point.
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

logger = logging.getLogger("opentower")

# Colors
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


async def run(config_path: str = "config.yaml") -> None:
    """Boot the Agent OS."""
    # ── Load config ────────────────────────────────────────────
    config = load_config(config_path)

    print(f"\n{C_BOLD}  🏢 OpenTower Agent OS v{config.agent.version}{C_RESET}")
    print(f"  {C_DIM}{'─' * 45}{C_RESET}")

    # ── LLM ────────────────────────────────────────────────────
    llm = LLMClient(
        base_url=config.agent.llm.base_url,
        api_key=config.agent.llm.api_key,
        model=config.agent.llm.model,
    )
    print(f"  {C_DIM}LLM    : {config.agent.llm.base_url} ({config.agent.llm.model}){C_RESET}")

    # ── Memory ─────────────────────────────────────────────────
    mem_db = await aiosqlite.connect(config.agent.memory.path)
    memory = NodeMemory("agent", mem_db, max_history=config.agent.memory.max_history)
    await memory.init()

    # ── Skills ─────────────────────────────────────────────────
    registry = SkillRegistry()
    registry.load_from_config(config.enabled_skills)
    print(f"  {C_DIM}Skills : {', '.join(registry.available) or '(none)'}{C_RESET}")

    # ── Agent ──────────────────────────────────────────────────
    agent = Agent(config, llm, memory=memory, skills=registry.all_skills)

    # ── Scheduler ──────────────────────────────────────────────
    scheduler = None
    if config.heartbeat.enabled:
        async def on_wake():
            logger.debug("Heartbeat wake — checking pending tasks")

        scheduler = Scheduler(interval=config.heartbeat.interval, on_wake=on_wake)
        for sched in config.schedules:
            scheduler.add_schedule(
                sched.cron, sched.action,
                lambda action: agent.run(action),
            )
        await scheduler.start()
        print(f"  {C_DIM}Heartbeat: every {config.heartbeat.interval}s{C_RESET}")

    # ── Channels ───────────────────────────────────────────────
    channels = []
    for ch_config in config.enabled_channels:
        if ch_config.type == "cli":
            channels.append(CLIChannel())
        elif ch_config.type == "webhook":
            from opentower.channels.webhook import WebhookChannel
            wh = WebhookChannel(port=ch_config.port)
            await wh.start()
            channels.append(wh)
        # telegram, discord, etc — future

    ch_names = [type(c).__name__ for c in channels]
    print(f"  {C_DIM}Channels: {', '.join(ch_names)}{C_RESET}")
    print(f"\n  {C_GREEN}✓ Agent online. Ready.{C_RESET}")
    print(f"  {C_DIM}Type 'exit' to shutdown.{C_RESET}\n")

    # ── Main loop ──────────────────────────────────────────────
    try:
        for channel in channels:
            async for msg in channel.listen():
                # Get memory context
                ctx = await memory.get_context(n=10) if memory else ""

                # Run agent
                response = await agent.run(msg.text, context=ctx)

                # Send response
                await channel.send(response)

    except KeyboardInterrupt:
        print(f"\n{C_DIM}Interrupted.{C_RESET}")

    # ── Cleanup ────────────────────────────────────────────────
    if scheduler:
        await scheduler.stop()
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
