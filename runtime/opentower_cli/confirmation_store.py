from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from .ops_types import CommandPlan, Decision, Intent, PlannedCommand, SecurityAssessment
from .runtime_layout import RuntimeLayout


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConfirmationRecord:
    confirmation_id: str
    run_id: str
    workflow_id: str
    operation: str
    objective: str
    status: str
    risk_level: str
    reason: str
    impacts: list[str]
    requires_reason: bool
    commands: list[dict[str, Any]]
    preview: dict[str, Any]
    created_at_utc: str
    resolved_at_utc: str | None = None
    answer: str | None = None
    answer_reason: str | None = None
    assessment_decision: str = "confirm"
    plan_parser_kind: str = ""
    intent_entities: dict[str, Any] = field(default_factory=dict)
    intent_confidence: float = 0.0
    intent_rationale: str = ""

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def to_intent(self) -> Intent:
        return Intent(
            workflow_id=self.workflow_id,
            operation=self.operation,
            objective=self.objective,
            entities=dict(self.intent_entities),
            confidence=float(self.intent_confidence),
            rationale=self.intent_rationale,
        )

    def to_assessment(self) -> SecurityAssessment:
        return SecurityAssessment(
            decision=cast(Decision, self.assessment_decision),
            risk_level=self.risk_level,
            reason=self.reason,
            impacts=list(self.impacts),
            requires_reason=self.requires_reason,
        )


def create_confirmation(
    *,
    layout: RuntimeLayout,
    run_id: str,
    intent: Intent,
    assessment: SecurityAssessment,
    plan: CommandPlan,
    commands: list[PlannedCommand],
    preview: dict[str, Any],
) -> ConfirmationRecord:
    record = ConfirmationRecord(
        confirmation_id=f"confirm-{uuid4().hex[:10]}",
        run_id=run_id,
        workflow_id=intent.workflow_id,
        operation=intent.operation,
        objective=intent.objective,
        status="pending",
        risk_level=assessment.risk_level,
        reason=assessment.reason,
        impacts=list(assessment.impacts),
        requires_reason=assessment.requires_reason,
        commands=[asdict(command) for command in commands],
        preview=preview,
        created_at_utc=_utc_now(),
        assessment_decision=assessment.decision,
        plan_parser_kind=plan.parser_kind,
        intent_entities=dict(intent.entities),
        intent_confidence=float(intent.confidence),
        intent_rationale=intent.rationale,
    )
    record.write(layout.confirmation_file(record.confirmation_id))
    return record


def load_confirmation(layout: RuntimeLayout, confirmation_id: str) -> ConfirmationRecord:
    path = layout.confirmation_file(confirmation_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ConfirmationRecord(**payload)


def save_confirmation(layout: RuntimeLayout, record: ConfirmationRecord) -> None:
    record.write(layout.confirmation_file(record.confirmation_id))


def mark_confirmation(
    layout: RuntimeLayout,
    record: ConfirmationRecord,
    *,
    answer: str,
    answer_reason: str | None,
    status: str,
) -> ConfirmationRecord:
    record.status = status
    record.answer = answer
    record.answer_reason = answer_reason
    record.resolved_at_utc = _utc_now()
    save_confirmation(layout, record)
    return record
