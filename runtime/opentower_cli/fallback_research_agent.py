from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .anthropic_client import AnthropicMessagesClient
from .auth_config import AuthProfile, load_auth_profile
from .operation_catalog import FALLBACK_RESEARCH, render_supported_operation_rows, supported_operations_by_source
from .ollama_client import OllamaMessagesClient
from .openai_compatible_client import OpenAICompatibleMessagesClient
from .ops_types import Intent, IntentResolution


FALLBACK_OPERATIONS: dict[str, set[str]] = supported_operations_by_source(FALLBACK_RESEARCH)
SERVICE_LOG_PATHS = {
    "nginx": "/var/log/nginx/error.log",
    "auth": "/var/log/auth.log",
    "sshd": "/var/log/auth.log",
    "syslog": "/var/log/syslog",
    "kernel": "/var/log/kern.log",
    "redis": "/var/log/redis/redis-server.log",
    "mysql": "/var/log/mysql/error.log",
}


def _workflow_for_operation(operation: str) -> str | None:
    clean = str(operation or "").strip()
    for workflow_id, operations in FALLBACK_OPERATIONS.items():
        if clean in operations:
            return workflow_id
    return None


@dataclass(frozen=True)
class FallbackResearchAgent:
    profile: AuthProfile
    client: Any
    model: str | None = None

    def research(
        self,
        *,
        objective: str,
        workflow_hint: str | None = None,
        prior_reason: str = "",
        prior_source: str = "",
    ) -> IntentResolution:
        heuristic = _local_research_resolution(objective=objective, workflow_hint=workflow_hint)
        if heuristic is not None:
            return heuristic
        response = self.client.create_message(
            system=_fallback_system_prompt(),
            user_text=_fallback_user_prompt(objective=objective, prior_reason=prior_reason, prior_source=prior_source),
            model=self.model or self.profile.model,
            max_tokens=800,
            temperature=0,
        )
        payload = _parse_json_payload(response.text)
        status = str(payload.get("status", "") or "").strip().lower()
        rationale = str(payload.get("rationale", "") or "").strip()
        clarification = str(payload.get("clarification_question", "") or "").strip()
        risk_level = str(payload.get("risk_level", "") or "").strip().lower() or "high"
        can_execute_now = bool(payload.get("can_execute_now"))
        if status != "supported":
            reason = rationale or clarification or "Fallback research could not map the request safely."
            return IntentResolution(
                status="unsupported",
                intent=None,
                reason=reason,
                source="fallback_research",
            )

        operation = str(payload.get("operation", "") or "").strip()
        raw_workflow_id = str(payload.get("workflow_id", "") or "").strip()
        workflow_id = raw_workflow_id if raw_workflow_id in FALLBACK_OPERATIONS else (_workflow_for_operation(operation) or raw_workflow_id)
        if workflow_id not in FALLBACK_OPERATIONS:
            raise ValueError(f"Unsupported fallback workflow: {workflow_id}")
        if operation not in FALLBACK_OPERATIONS[workflow_id]:
            raise ValueError(f"Unsupported fallback operation: {workflow_id}/{operation}")
        if workflow_hint and workflow_hint != workflow_id:
            raise ValueError(f"Objective does not match workflow '{workflow_hint}'; fallback resolved '{workflow_id}'.")
        if risk_level != "low" or not can_execute_now:
            reason = rationale or clarification or "Fallback research declined execution for this request."
            return IntentResolution(
                status="unsupported",
                intent=None,
                reason=reason,
                source="fallback_research",
            )

        entities = _normalize_entities(workflow_id=workflow_id, operation=operation, payload=payload.get("entities", {}))
        confidence = _normalize_confidence(payload.get("confidence"))
        intent = Intent(
            workflow_id=workflow_id,
            operation=operation,
            objective=objective,
            entities=entities,
            confidence=confidence,
            rationale=rationale or "Mapped by fallback research.",
        )
        return IntentResolution(
            status="supported",
            intent=intent,
            reason=intent.rationale,
            source="fallback_research",
        )


def _fallback_system_prompt() -> str:
    supported = render_supported_operation_rows(FALLBACK_RESEARCH)
    return "\n".join(
        [
            "You are the OpenTower Linux Ops fallback research agent.",
            "Map unsupported requests only into a small set of low-risk read-only operations, or decline safely.",
            "A prior stage may say the request is unsupported in the narrow deterministic planner. That prior reason is context only, not a binding restriction.",
            "If the current request fits one of the allowed fallback operations below, return supported even if the prior stage declined it.",
            "Never emit shell commands.",
            "Never propose restart, stop, start, install, delete, chmod, package management, deployment, firewall, or user mutation operations.",
            "Allowed operations:",
            *[f"- {row}" for row in supported],
            "Canonical mappings:",
            "- show cpu usage => process-port-inspection / top_cpu",
            "- show load average => process-port-inspection / load_average",
            "- show uptime => process-port-inspection / uptime_summary",
            "- tail the latest nginx error log => file-search / tail_log / path=/var/log/nginx/error.log",
            "Known default log paths:",
            "- nginx => /var/log/nginx/error.log",
            "- auth or sshd => /var/log/auth.log",
            "- syslog => /var/log/syslog",
            "- kernel => /var/log/kern.log",
            "- redis => /var/log/redis/redis-server.log",
            "- mysql => /var/log/mysql/error.log",
            'Return JSON only with this schema: {"status":"supported|unsupported","workflow_id":"...","operation":"...","entities":{},"confidence":0.0,"risk_level":"low|medium|high","can_execute_now":true|false,"clarification_question":"...","rationale":"..."}',
            "Prefer unsupported over guessing. Only mark can_execute_now true for low-risk read-only operations with concrete entities.",
        ]
    )


def _fallback_user_prompt(*, objective: str, prior_reason: str, prior_source: str) -> str:
    lines = [f"objective: {objective}"]
    if prior_source:
        lines.append(f"prior_source: {prior_source}")
    if prior_reason:
        lines.append(f"prior_reason_context_only: {prior_reason}")
    return "\n".join(lines)


def _parse_json_payload(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Fallback research agent did not return a JSON object.")
    return payload


def _normalize_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)


def _normalize_count(raw: Any, *, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


def _normalize_entities(*, workflow_id: str, operation: str, payload: Any) -> dict[str, Any]:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("Fallback research entities must be an object.")

    def _text(name: str) -> str | None:
        value = payload.get(name)
        text = str(value or "").strip()
        return text or None

    entities: dict[str, Any] = {}
    if operation == "service_status":
        service = _text("service")
        if not service:
            raise ValueError("Fallback research missing required entity: service")
        entities["service"] = service
        return entities

    if operation in {"top_cpu", "top_memory", "load_average", "uptime_summary"}:
        return entities

    service = (_text("service") or "").lower()
    path = _text("path") or SERVICE_LOG_PATHS.get(service)
    if not path:
        raise ValueError(f"Fallback research missing concrete log path for {operation}")
    entities["path"] = path
    if service:
        entities["service"] = service
    if operation == "tail_log":
        entities["line_count"] = _normalize_count(payload.get("line_count"), default=100)
    elif operation == "recent_error_scan":
        entities["limit"] = _normalize_count(payload.get("limit"), default=50)
    if workflow_id != "file-search":
        raise ValueError(f"Unsupported fallback workflow/entity combination: {workflow_id}/{operation}")
    return entities


def _local_research_resolution(*, objective: str, workflow_hint: str | None = None) -> IntentResolution | None:
    text = str(objective or "").strip()
    lowered = text.lower()

    def _supported_intent(workflow_id: str, operation: str, *, entities: dict[str, Any] | None = None, rationale: str) -> IntentResolution:
        if workflow_hint and workflow_hint != workflow_id:
            return IntentResolution(
                status="unsupported",
                intent=None,
                reason=f"Objective does not match workflow '{workflow_hint}'; fallback resolved '{workflow_id}'.",
                source="fallback_research",
            )
        return IntentResolution(
            status="supported",
            intent=Intent(
                workflow_id=workflow_id,
                operation=operation,
                objective=text,
                entities=entities or {},
                confidence=0.95,
                rationale=rationale,
            ),
            reason=rationale,
            source="fallback_research",
        )

    if "cpu" in lowered and any(token in lowered for token in ("usage", "load", "top")):
        return _supported_intent(
            "process-port-inspection",
            "top_cpu",
            rationale="Direct mapping to top_cpu under process-port-inspection per allowed operations.",
        )

    if "load average" in lowered or "system load" in lowered:
        return _supported_intent(
            "process-port-inspection",
            "load_average",
            rationale="Direct mapping to load_average under process-port-inspection per allowed operations.",
        )

    if "uptime" in lowered:
        return _supported_intent(
            "process-port-inspection",
            "uptime_summary",
            rationale="Direct mapping to uptime_summary under process-port-inspection per allowed operations.",
        )

    if "tail" in lowered and "log" in lowered:
        service = next((name for name in SERVICE_LOG_PATHS if name in lowered), "")
        path = SERVICE_LOG_PATHS.get(service)
        if path:
            match = re.search(r"\b(?:last|tail)\s+(\d{1,3})\b", lowered)
            line_count = _normalize_count(match.group(1) if match else None, default=10, maximum=200)
            entities: dict[str, Any] = {"path": path, "line_count": line_count}
            if service:
                entities["service"] = service
            return _supported_intent(
                "file-search",
                "tail_log",
                entities=entities,
                rationale=f"Direct mapping to tail_log with the known default path for {service or 'the requested'} logs. This is a low-risk, read-only operation.",
            )

    return None


def build_fallback_research_agent(*, root: Path) -> FallbackResearchAgent | None:
    profile = load_auth_profile(root, create_if_missing=False)
    provider = profile.provider
    if provider == "anthropic":
        if not profile.api_key:
            return None
        client = AnthropicMessagesClient(api_key=profile.api_key, api_url=profile.api_base_url or None)
        return FallbackResearchAgent(profile=profile, client=client, model=profile.model)
    if provider == "openai-compatible":
        if not profile.api_key:
            return None
        client = OpenAICompatibleMessagesClient(api_url=profile.api_base_url or None, api_key=profile.api_key)
        return FallbackResearchAgent(profile=profile, client=client, model=profile.model)
    client = OllamaMessagesClient(api_url=profile.api_base_url or None, api_key=profile.api_key or None)
    return FallbackResearchAgent(profile=profile, client=client, model=profile.model)


__all__ = [
    "FALLBACK_OPERATIONS",
    "FallbackResearchAgent",
    "SERVICE_LOG_PATHS",
    "build_fallback_research_agent",
]
