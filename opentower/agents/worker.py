"""Worker Agent — task execution via Action Registry.

Listens for ``task_assign`` packets, looks up the action in the registry,
executes it, and reports the result as ``task_result``.
"""

from __future__ import annotations

import logging
from typing import Any

from opentower.actions.registry import ActionRegistry
from opentower.agents.base import BaseAgent
from opentower.schema.emp import (
    EMPPacket,
    INTENT_TASK_ASSIGN,
    INTENT_TASK_RESULT,
)

logger = logging.getLogger("opentower.agents.worker")


class WorkerAgent(BaseAgent):
    """Execution Node — executes actions, never reasons about intent."""

    def __init__(self, *args: Any, registry: ActionRegistry, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.registry = registry

    def register(self) -> None:
        """Subscribe to task_assign events."""
        self.bus.subscribe(INTENT_TASK_ASSIGN, self.handle)

    async def handle(self, packet: EMPPacket) -> None:
        action_type = packet.payload.get("action_type", "")
        task_payload = packet.payload.get("task_payload", {})
        original_intent = packet.payload.get("original_intent", "")

        logger.info("[Worker] Executing action: %s", action_type)
        await self.state.record(packet)

        try:
            result = await self.registry.execute(action_type, task_payload)
            status = "success"
        except KeyError as exc:
            result = {"error": str(exc)}
            status = "error"
        except Exception as exc:
            result = {"error": f"Unexpected error: {exc}"}
            status = "error"
            logger.exception("[Worker] Action %s failed", action_type)

        # Report result back
        result_packet = EMPPacket(
            source=self.node_id,
            target="qa",
            intent_type=INTENT_TASK_RESULT,
            action=f"Result of: {packet.action}",
            payload={
                "action_type": action_type,
                "status": status,
                "result": result,
                "original_intent": original_intent,
                "task_index": packet.payload.get("task_index"),
                "total_tasks": packet.payload.get("total_tasks"),
            },
            token_budget=packet.token_budget,
            parent_trace_id=packet.trace_id,
        )
        await self.emit(result_packet)
