"""Worker Agent — task execution via Action Registry (V2.0).

Listens for ``task_assign`` packets targeted at this node,
looks up the action in the registry, executes it, and reports
the result as ``task_result``.

V2.0: Supports targeted routing (only processes packets addressed to this node).
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
        # Only process packets targeted at this node
        if packet.target and packet.target != self.node_id:
            return

        action_type = packet.payload.get("action_type", "")
        task_payload = packet.payload.get("task_payload", {})
        original_intent = packet.payload.get("original_intent", "")

        # If action_type is "delegate", this means the task was routed
        # to a worker but it's a delegation task — use the intent as shell cmd
        if action_type == "delegate":
            intent = packet.payload.get("intent", packet.action)
            action_type = "shell_execute"
            task_payload = {"command": intent}

        logger.info("[%s] Executing action: %s", self.node_id, action_type)
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
            logger.exception("[%s] Action %s failed", self.node_id, action_type)

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
                "chain": packet.payload.get("chain", []) + [self.node_id],
            },
            token_budget=packet.token_budget,
            parent_trace_id=packet.trace_id,
        )
        await self.emit(result_packet)
