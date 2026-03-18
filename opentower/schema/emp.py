"""Layer 3: EMP (Empire Message Protocol) — strongly-typed JSON packets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# ── Intent type constants ──────────────────────────────────────────
INTENT_USER_REQUEST = "user_request"
INTENT_TASK_ASSIGN = "task_assign"
INTENT_TASK_RESULT = "task_result"
INTENT_QA_VERDICT = "qa_verdict"


class EMPPacket(BaseModel):
    """A single message on the EMP event bus.

    Every inter-agent communication is wrapped in this envelope so that
    the routing layer can dispatch by ``intent_type`` and the state wall
    can persist the full trace.
    """

    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: str  # sender node id, e.g. "ceo"
    target: str | None = None  # None = broadcast
    intent_type: str  # routing key
    action: str  # human-readable action description
    payload: dict[str, Any] = Field(default_factory=dict)
    token_budget: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_trace_id: str | None = None  # chain tracing

    def reply(
        self,
        *,
        source: str,
        intent_type: str,
        action: str,
        payload: dict[str, Any] | None = None,
        token_budget: int | None = None,
    ) -> "EMPPacket":
        """Create a reply packet that inherits this packet's trace chain."""
        return EMPPacket(
            source=source,
            target=self.source,
            intent_type=intent_type,
            action=action,
            payload=payload or {},
            token_budget=token_budget if token_budget is not None else self.token_budget,
            parent_trace_id=self.trace_id,
        )
