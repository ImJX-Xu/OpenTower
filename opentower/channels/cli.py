"""CLI Channel — interactive terminal interface.

The simplest channel: reads from stdin, writes to stdout.
Used for development and direct interaction.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from opentower.channels import Channel, Message

logger = logging.getLogger("opentower.channels.cli")

# Colors
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"


class CLIChannel(Channel):
    """Terminal-based channel for interactive use."""

    def __init__(self) -> None:
        self._running = True

    async def listen(self) -> AsyncIterator[Message]:
        """Read lines from stdin."""
        while self._running:
            try:
                text = await asyncio.to_thread(
                    input, f"{C_CYAN}🏢 OpenTower>{C_RESET} "
                )
            except (EOFError, KeyboardInterrupt):
                break

            text = text.strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit", "q"):
                break

            yield Message(text=text, sender="user", channel="cli")

    async def send(self, text: str) -> None:
        """Print response to stdout."""
        # Format nicely
        lines = text.split("\n")
        print(f"\n{C_GREEN}{C_BOLD}  Agent:{C_RESET}")
        for line in lines:
            print(f"  {line}")
        print()

    async def stop(self) -> None:
        self._running = False
