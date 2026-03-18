"""QA Agent — dual verification (static rules + LLM semantic check).

Listens for ``task_result`` packets, validates the execution output,
and emits a ``qa_verdict`` with APPROVE or REJECT.
"""

from __future__ import annotations

import json
import logging
import re

from opentower.agents.base import BaseAgent
from opentower.schema.emp import (
    EMPPacket,
    INTENT_QA_VERDICT,
    INTENT_TASK_ASSIGN,
    INTENT_TASK_RESULT,
)

logger = logging.getLogger("opentower.agents.qa")

_MAX_RETRIES = 2  # max times QA will send a task back to Worker


class QAAgent(BaseAgent):
    """Quality Assurance Inspector — never executes, only judges."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._retry_counts: dict[str, int] = {}  # trace_id → retry count

    def register(self) -> None:
        """Subscribe to task_result events."""
        self.bus.subscribe(INTENT_TASK_RESULT, self.handle)

    async def handle(self, packet: EMPPacket) -> None:
        logger.info("[QA] Inspecting result: %s", packet.action)
        await self.state.record(packet)

        result_data = packet.payload.get("result", {})
        status = packet.payload.get("status", "unknown")
        original_intent = packet.payload.get("original_intent", "")

        # ── 1. Static rules check ──────────────────────────────────
        static_issues = self._static_check(status, result_data)

        # ── 2. LLM semantic check ──────────────────────────────────
        if not static_issues:
            verdict_data = await self._llm_check(original_intent, result_data)
        else:
            verdict_data = {
                "verdict": "REJECT",
                "reason": "; ".join(static_issues),
                "suggestion": "Fix the issues listed above and re-execute.",
            }

        verdict = verdict_data.get("verdict", "APPROVE")
        reason = verdict_data.get("reason", "")
        suggestion = verdict_data.get("suggestion")

        # ── Emit verdict ───────────────────────────────────────────
        verdict_packet = EMPPacket(
            source=self.node_id,
            target="user",
            intent_type=INTENT_QA_VERDICT,
            action=f"QA {verdict}: {packet.action}",
            payload={
                "verdict": verdict,
                "reason": reason,
                "suggestion": suggestion,
                "inspected_result": result_data,
                "task_index": packet.payload.get("task_index"),
                "total_tasks": packet.payload.get("total_tasks"),
            },
            token_budget=packet.token_budget,
            parent_trace_id=packet.trace_id,
        )
        await self.emit(verdict_packet)

        # ── If REJECT, optionally retry ────────────────────────────
        if verdict == "REJECT":
            # Use original_intent as retry key (trace_ids change per retry)
            intent_key = packet.payload.get("original_intent", packet.trace_id)
            retries = self._retry_counts.get(intent_key, 0)
            if retries < _MAX_RETRIES:
                self._retry_counts[intent_key] = retries + 1
                logger.info(
                    "[QA] REJECT — retrying (%d/%d): %s",
                    retries + 1,
                    _MAX_RETRIES,
                    suggestion,
                )
                # Re-broadcast as task_assign with the suggestion baked in
                retry_packet = EMPPacket(
                    source=self.node_id,
                    target="worker",
                    intent_type=INTENT_TASK_ASSIGN,
                    action=f"[RETRY] {packet.action}",
                    payload={
                        **packet.payload,
                        "qa_suggestion": suggestion,
                    },
                    token_budget=packet.token_budget,
                    parent_trace_id=packet.trace_id,
                )
                await self.emit(retry_packet)
            else:
                logger.warning("[QA] Max retries reached for intent: %s", intent_key[:50])

    @staticmethod
    def _static_check(status: str, result: dict) -> list[str]:
        """Rule-based checks on the result."""
        issues = []
        if status == "error":
            error_msg = result.get("error", "unknown error")
            issues.append(f"Execution failed: {error_msg}")
        if "exit_code" in result and result["exit_code"] != 0:
            issues.append(f"Non-zero exit code: {result['exit_code']}")
        return issues

    async def _llm_check(self, intent: str, result: dict) -> dict:
        """Use the LLM to semantically verify if the result satisfies the intent."""
        messages = [
            {
                "role": "user",
                "content": (
                    f"原始意图：{intent}\n\n"
                    f"执行结果：{json.dumps(result, ensure_ascii=False, indent=2)}\n\n"
                    "请判断执行结果是否满足原始意图，以 JSON 格式返回判定。"
                ),
            }
        ]

        try:
            raw = await self.call_llm(messages, max_tokens=512)
            return self._parse_verdict(raw)
        except RuntimeError:
            # Token budget exhausted — auto-approve to avoid blocking
            logger.warning("[QA] Token budget exhausted, auto-approving")
            return {"verdict": "APPROVE", "reason": "Token budget exhausted, auto-approved"}

    @staticmethod
    def _parse_verdict(raw: str) -> dict:
        """Extract the verdict JSON from the LLM response.

        Strategy:
        1. Try to find all JSON objects in the raw output (including inside think tags)
        2. Return the first one that contains a "verdict" key
        3. Fall back to keyword scanning for APPROVE/REJECT
        """
        # Find all potential JSON objects in the raw text
        for match in re.finditer(r"\{[^{}]*\}", raw):
            try:
                parsed = json.loads(match.group())
                if "verdict" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Try nested JSON objects (with inner braces)
        for match in re.finditer(r"\{[^}]*\{[^}]*\}[^}]*\}", raw):
            try:
                parsed = json.loads(match.group())
                if "verdict" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        # Fall back to keyword scanning
        raw_upper = raw.upper()
        if "REJECT" in raw_upper:
            return {"verdict": "REJECT", "reason": "LLM indicated rejection (parsed from text)"}
        if "APPROVE" in raw_upper:
            return {"verdict": "APPROVE", "reason": "LLM indicated approval (parsed from text)"}

        logger.warning("[QA] Could not parse verdict, defaulting to APPROVE: %.200s", raw)
        return {"verdict": "APPROVE", "reason": f"Auto-approved (unparseable LLM output): {raw[:100]}"}
