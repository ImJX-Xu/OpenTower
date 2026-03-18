"""CEO Agent — intent decomposition & task broadcasting.

Listens for ``user_request`` packets, uses the LLM to decompose the
natural-language intent into a JSON array of atomic tasks, then broadcasts
each as a ``task_assign`` packet to the Worker.
"""

from __future__ import annotations

import json
import logging
import re

from opentower.agents.base import BaseAgent
from opentower.schema.emp import (
    EMPPacket,
    INTENT_TASK_ASSIGN,
    INTENT_USER_REQUEST,
)

logger = logging.getLogger("opentower.agents.ceo")

_MAX_DECOMPOSE_DEPTH = 3  # anti-infinite-loop guard


class CEOAgent(BaseAgent):
    """Chief Executive Orchestrator — decomposes intent, never executes."""

    def register(self) -> None:
        """Subscribe to user_request events."""
        self.bus.subscribe(INTENT_USER_REQUEST, self.handle)

    async def handle(self, packet: EMPPacket) -> None:
        user_intent = packet.action
        logger.info("[CEO] Received user intent: %s", user_intent)

        # Record incoming packet
        await self.state.record(packet)

        # Ask LLM to decompose
        messages = [
            {
                "role": "user",
                "content": (
                    f"用户意图：{user_intent}\n\n"
                    "请将此意图拆解为可执行的原子任务列表，以 JSON 数组格式返回。"
                ),
            }
        ]

        raw = await self.call_llm(messages)
        tasks = self._parse_tasks(raw)

        if not tasks:
            logger.warning("[CEO] Failed to decompose intent, broadcasting raw intent")
            tasks = [
                {
                    "action_type": "shell_execute",
                    "description": user_intent,
                    "payload": {"command": user_intent},
                }
            ]

        # Broadcast each task
        for i, task in enumerate(tasks):
            task_packet = EMPPacket(
                source=self.node_id,
                target="worker",
                intent_type=INTENT_TASK_ASSIGN,
                action=task.get("description", task.get("action_type", "unknown")),
                payload={
                    "action_type": task.get("action_type", "shell_execute"),
                    "task_payload": task.get("payload", {}),
                    "task_index": i,
                    "total_tasks": len(tasks),
                    "original_intent": user_intent,
                },
                token_budget=self.config.token_budget - self.tokens_used,
                parent_trace_id=packet.trace_id,
            )
            await self.emit(task_packet)

        logger.info("[CEO] Broadcasted %d tasks", len(tasks))

    @staticmethod
    def _parse_tasks(raw: str) -> list[dict]:
        """Extract a JSON array from the LLM response, tolerating markdown fences."""
        # Strip <think>...</think> reasoning tags (e.g. Qwen, DeepSeek)
        # Handle both with and without closing tag
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if cleaned.startswith("<think>"):
            # No closing tag — strip everything up to last JSON-like content
            idx = cleaned.find("[")
            brace = cleaned.find("{")
            if idx == -1 or (brace != -1 and brace < idx):
                idx = brace
            cleaned = cleaned[idx:] if idx != -1 else cleaned
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            # Try to find a JSON array anywhere in the text
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        logger.warning("[CEO] Could not parse LLM output as JSON: %.200s", raw)
        return []
