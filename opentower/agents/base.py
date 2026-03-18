"""Base Agent — abstract foundation for all agent nodes (V2.0).

Provides:
- Config injection (role prompt, permissions, token budget)
- Bus integration (subscribe + emit)
- LLM call wrapper with automatic token accounting
- Per-node memory (independent context for each agent)
- Global state wall recording (audit log)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from opentower.bus.event_bus import EMPBus
from opentower.llm.client import LLMClient
from opentower.memory.node_memory import NodeMemory
from opentower.memory.state_wall import StateWall
from opentower.schema.company import NodeConfig
from opentower.schema.emp import EMPPacket

logger = logging.getLogger("opentower.agents")


class BaseAgent(ABC):
    """Abstract base class for all OpenTower agents (V2.0)."""

    def __init__(
        self,
        node_id: str,
        config: NodeConfig,
        bus: EMPBus,
        llm: LLMClient,
        state: StateWall,
        *,
        memory: Optional[NodeMemory] = None,
        **kwargs,
    ) -> None:
        self.node_id = node_id
        self.config = config
        self.bus = bus
        self.llm = llm
        self.state = state
        self.memory = memory  # per-node scoped memory (V2.0)
        self.tokens_used = 0

    @abstractmethod
    async def handle(self, packet: EMPPacket) -> None:
        """Process an incoming EMP packet. Subclasses must implement."""
        ...

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
    ) -> str:
        """Call the LLM with token budget enforcement and memory injection.

        V2.0: Automatically injects per-node memory context before the prompt.

        Raises:
            RuntimeError: If the token budget is exceeded.
        """
        remaining = self.config.token_budget - self.tokens_used
        if remaining <= 0:
            raise RuntimeError(
                f"[{self.node_id}] Token budget exhausted "
                f"({self.tokens_used}/{self.config.token_budget})"
            )

        # Build full message chain
        full_messages = []

        # 1. System prompt from config
        full_messages.append({"role": "system", "content": self.config.prompt})

        # 2. Inject per-node memory context (V2.0)
        if self.memory:
            context = await self.memory.get_context(n=5)
            if context:
                full_messages.append({
                    "role": "system",
                    "content": f"你的近期工作记忆（仅供上下文参考）：\n{context}",
                })

        # 3. User messages
        full_messages.extend(messages)

        effective_max = min(max_tokens, remaining)
        text, usage = await self.llm.chat(full_messages, max_tokens=effective_max)
        self.tokens_used += usage.total

        logger.info(
            "[%s] LLM used %d tokens (total %d/%d)",
            self.node_id,
            usage.total,
            self.tokens_used,
            self.config.token_budget,
        )

        # Record in per-node memory
        if self.memory:
            await self.memory.record("input", messages[-1].get("content", "")[:500])
            await self.memory.record("output", text[:500])

        return text

    async def emit(self, packet: EMPPacket) -> None:
        """Publish a packet on the bus and record it in the state wall."""
        await self.state.record(packet)
        await self.bus.publish(packet)
        logger.info(
            "[%s] → [%s] %s: %s",
            packet.source,
            packet.target or "ALL",
            packet.intent_type,
            packet.action[:80],
        )
