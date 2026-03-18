"""Manager Agent — generic task decomposition node (V2.0).

A ManagerAgent is any node that has subordinates. It:
1. Receives a task (via task_assign or delegate intent)
2. Uses the LLM to decompose it into sub-tasks
3. Dispatches each sub-task to the appropriate subordinate

The CEO from V1.0 is now just a ManagerAgent configured via company.yaml.
Chairman, CEO, VP, TechLead — they all use this same class.
"""

from __future__ import annotations

import json
import logging
import re

from opentower.agents.base import BaseAgent
from opentower.schema.emp import (
    EMPPacket,
    INTENT_TASK_ASSIGN,
)

logger = logging.getLogger("opentower.agents.manager")


class ManagerAgent(BaseAgent):
    """Generic manager — decomposes tasks and delegates to subordinates.

    Replaces the V1.0 CEOAgent with a generalized version that works
    at any level of the org hierarchy.
    """

    def __init__(self, *args, subordinates: list[str] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.subordinates = subordinates or []

    def register(self, listen_intents: list[str] | None = None) -> None:
        """Subscribe to relevant intents.

        Args:
            listen_intents: List of intent_types to listen for.
                            Defaults to [INTENT_TASK_ASSIGN].
        """
        intents = listen_intents or [INTENT_TASK_ASSIGN]
        for intent in intents:
            self.bus.subscribe(intent, self.handle)

    async def handle(self, packet: EMPPacket) -> None:
        """Decompose incoming task and delegate to subordinates."""
        # Only process packets targeted at this node (or broadcast)
        if packet.target and packet.target != self.node_id:
            return

        intent = packet.payload.get("intent", packet.action)
        logger.info(
            "[%s] Received task: %s (from %s)",
            self.node_id,
            intent[:60],
            packet.source,
        )
        await self.state.record(packet)

        # Ask LLM to decompose
        messages = [
            {
                "role": "user",
                "content": (
                    f"上级分配的任务：{intent}\n\n"
                    f"你的下属节点：{', '.join(self.subordinates)}\n\n"
                    "请将此任务拆解为可分配给下属的原子任务列表，以 JSON 数组格式返回。"
                ),
            }
        ]

        try:
            raw = await self.call_llm(messages)
        except RuntimeError:
            logger.warning("[%s] Token budget exhausted, forwarding raw task", self.node_id)
            raw = None

        tasks = self._parse_tasks(raw) if raw else []

        if not tasks:
            logger.warning("[%s] Failed to decompose, forwarding as single task", self.node_id)
            # Default: forward to first subordinate
            target = self.subordinates[0] if self.subordinates else "worker"
            tasks = [
                {
                    "action_type": "delegate",
                    "description": intent,
                    "payload": {"intent": intent},
                    "target_subordinate": target,
                }
            ]

        # Dispatch each sub-task
        for i, task in enumerate(tasks):
            target = task.get("target_subordinate")
            if not target or target not in self.subordinates:
                target = self.subordinates[0] if self.subordinates else "worker"

            # Determine action_type: "delegate" means send to manager, else direct execute
            action_type = task.get("action_type", "delegate")

            task_packet = EMPPacket(
                source=self.node_id,
                target=target,
                intent_type=INTENT_TASK_ASSIGN,
                action=task.get("description", intent),
                payload={
                    "action_type": action_type,
                    "task_payload": task.get("payload", {}),
                    "intent": task.get("payload", {}).get("intent", intent),
                    "task_index": i,
                    "total_tasks": len(tasks),
                    "original_intent": packet.payload.get("original_intent", intent),
                    "chain": packet.payload.get("chain", []) + [self.node_id],
                },
                token_budget=max(
                    256,
                    (self.config.token_budget - self.tokens_used) // max(1, len(tasks)),
                ),
                parent_trace_id=packet.trace_id,
            )
            await self.emit(task_packet)

        logger.info("[%s] Delegated %d sub-tasks", self.node_id, len(tasks))

    @staticmethod
    def _parse_tasks(raw: str) -> list[dict]:
        """Extract a JSON array from the LLM response, robust to think tags."""
        # Strip <think>...</think> reasoning tags
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if cleaned.startswith("<think>"):
            # No closing tag — find first JSON content
            idx = cleaned.find("[")
            brace = cleaned.find("{")
            if idx == -1 or (brace != -1 and brace < idx):
                idx = brace
            cleaned = cleaned[idx:] if idx != -1 else cleaned

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            # Try to find a JSON array anywhere
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            # Try individual JSON objects
            results = []
            for m in re.finditer(r"\{[^{}]*\}", raw):
                try:
                    obj = json.loads(m.group())
                    if "action_type" in obj or "description" in obj:
                        results.append(obj)
                except json.JSONDecodeError:
                    continue
            if results:
                return results

        logger.warning("[%s] Could not parse LLM output as JSON: %.200s", "manager", raw)
        return []
