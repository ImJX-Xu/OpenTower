from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .feedback_agent import format_unsupported_response
from .intent_parser import resolve_objective
from .ops_types import Intent
from .runtime_layout import RuntimeLayout, repo_runtime_layout


@dataclass(frozen=True)
class DispatchResult:
    run_id: str
    workflow_id: str
    objective: str
    category: str
    agents: list[str]
    handoff_chain: list[str]
    acceptance_checks: list[str]
    log_file: Path
    resolution_status: str = "supported"
    resolution_reason: str = ""
    resolution_source: str = "local_rule"
    user_message: str = ""
    intent: Intent | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_workflows(skills_cfg: dict[str, Any], category: str | None = None) -> list[dict[str, Any]]:
    rows = [
        workflow for workflow in skills_cfg.get("workflows", [])
        if isinstance(workflow, dict)
    ]
    if category:
        rows = [row for row in rows if str(row.get("category", "")).strip() == category]
    return sorted(rows, key=lambda row: str(row.get("id", "")))


def workflow_config(skills_cfg: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    workflow = next(
        (
            row for row in skills_cfg.get("workflows", [])
            if isinstance(row, dict) and str(row.get("id", "")).strip() == workflow_id
        ),
        None,
    )
    if workflow is None:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    return workflow


def dispatch(
    *,
    system_cfg: dict[str, Any],
    skills_cfg: dict[str, Any],
    objective: str,
    root: Path,
    workflow_id: str | None = None,
    runtime_layout: RuntimeLayout | None = None,
    intent_normalizer: Any | None = None,
    fallback_research_agent: Any | None = None,
) -> DispatchResult:
    now = _utc_now()
    run_id = f"run-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    layout = runtime_layout or repo_runtime_layout(root)
    layout.ensure_dirs()
    log_file = layout.log_file(run_id)
    resolution = resolve_objective(
        objective,
        workflow_hint=workflow_id,
        normalizer=intent_normalizer,
        fallback_agent=fallback_research_agent,
    )

    if resolution.status == "supported":
        intent = resolution.intent
        if intent is None:
            raise ValueError("Supported resolution is missing intent.")
        workflow = workflow_config(skills_cfg, intent.workflow_id)

        payload = {
            "run_id": run_id,
            "timestamp_utc": now.isoformat(),
            "objective": objective,
            "workflow_id": intent.workflow_id,
            "category": workflow.get("category"),
            "routed_operation": intent.operation,
            "intent_entities": intent.entities,
            "acceptance_checks": workflow.get("acceptance_checks", []),
            "default_agents": workflow.get("default_agents", []),
            "handoff_chain": workflow.get("handoff_chain", []),
            "resolution_status": resolution.status,
            "resolution_reason": resolution.reason,
            "resolution_source": resolution.source,
            "runtime_context": layout.describe(),
        }
        log_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        layout.active_file.write_text(
            "\n".join(
                [
                    "# Active Session",
                    "",
                    f"- run_id: {run_id}",
                    f"- workflow_id: {intent.workflow_id}",
                    f"- category: {workflow.get('category', '-')}",
                    f"- routed_operation: {intent.operation}",
                    f"- objective: {objective}",
                    f"- resolution_status: {resolution.status}",
                    f"- handoff_chain: {', '.join(workflow.get('handoff_chain', []))}",
                    f"- acceptance_checks: {', '.join(workflow.get('acceptance_checks', []))}",
                    f"- log_file: {log_file.as_posix()}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        return DispatchResult(
            run_id=run_id,
            workflow_id=intent.workflow_id,
            objective=objective,
            category=str(workflow.get("category", "")).strip(),
            agents=list(workflow.get("default_agents", [])),
            handoff_chain=list(workflow.get("handoff_chain", [])),
            acceptance_checks=list(workflow.get("acceptance_checks", [])),
            log_file=log_file,
            resolution_status=resolution.status,
            resolution_reason=resolution.reason,
            resolution_source=resolution.source,
            intent=intent,
        )

    user_message = format_unsupported_response(objective=objective, reason=resolution.reason)
    payload = {
        "run_id": run_id,
        "timestamp_utc": now.isoformat(),
        "objective": objective,
        "workflow_id": "unsupported",
        "category": "unsupported",
        "routed_operation": None,
        "intent_entities": {},
        "acceptance_checks": [],
        "default_agents": ["intent-parser"],
        "handoff_chain": ["intent-parser"],
        "resolution_status": resolution.status,
        "resolution_reason": resolution.reason,
        "resolution_source": resolution.source,
        "runtime_context": layout.describe(),
    }
    log_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    layout.active_file.write_text(
        "\n".join(
            [
                "# Active Session",
                "",
                f"- run_id: {run_id}",
                "- workflow_id: unsupported",
                "- category: unsupported",
                "- routed_operation: -",
                f"- objective: {objective}",
                f"- resolution_status: {resolution.status}",
                f"- resolution_reason: {resolution.reason}",
                f"- log_file: {log_file.as_posix()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return DispatchResult(
        run_id=run_id,
        workflow_id="unsupported",
        objective=objective,
        category="unsupported",
        agents=["intent-parser"],
        handoff_chain=["intent-parser"],
        acceptance_checks=[],
        log_file=log_file,
        resolution_status=resolution.status,
        resolution_reason=resolution.reason,
        resolution_source=resolution.source,
        user_message=user_message,
        intent=None,
    )
