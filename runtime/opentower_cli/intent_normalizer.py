from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .anthropic_client import AnthropicMessagesClient
from .auth_config import AuthProfile, load_auth_profile
from .ollama_client import OllamaMessagesClient
from .openai_compatible_client import OpenAICompatibleMessagesClient
from .ops_types import Intent, IntentResolution


SUPPORTED_OPERATIONS: dict[str, set[str]] = {
    "disk-inspection": {"disk_usage", "disk_usage_with_logs"},
    "file-search": {"filename_search", "content_search", "inspect_permissions", "delete_path", "chmod_recursive"},
    "process-port-inspection": {"port_lookup", "top_memory", "service_status"},
    "user-management": {"list_users", "create_user", "add_user_to_group", "delete_user", "batch_delete_users", "inspect_user"},
}


@dataclass(frozen=True)
class StructuredIntentNormalizer:
    profile: AuthProfile
    client: Any
    model: str | None = None

    def normalize(self, *, objective: str, workflow_hint: str | None = None) -> IntentResolution:
        response = self.client.create_message(
            system=_normalizer_system_prompt(),
            user_text=objective,
            model=self.model or self.profile.model,
            max_tokens=600,
            temperature=0,
        )
        payload = _parse_json_payload(response.text)
        status = str(payload.get("status", "") or "").strip().lower()
        if status != "supported":
            reason = str(payload.get("rationale", "") or "").strip() or "LLM normalizer could not map the request safely."
            return IntentResolution(
                status="unsupported",
                intent=None,
                reason=reason,
                source="llm_normalizer",
            )

        workflow_id = str(payload.get("workflow_id", "") or "").strip()
        operation = str(payload.get("operation", "") or "").strip()
        if workflow_id not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported workflow from LLM normalizer: {workflow_id}")
        if operation not in SUPPORTED_OPERATIONS[workflow_id]:
            raise ValueError(f"Unsupported operation from LLM normalizer: {workflow_id}/{operation}")
        if workflow_hint and workflow_hint != workflow_id:
            raise ValueError(f"Objective does not match workflow '{workflow_hint}'; normalizer resolved '{workflow_id}'.")

        entities = _normalize_entities(workflow_id=workflow_id, operation=operation, payload=payload.get("entities", {}))
        confidence = _normalize_confidence(payload.get("confidence"))
        rationale = str(payload.get("rationale", "") or "").strip() or "Mapped by LLM normalizer."
        intent = Intent(
            workflow_id=workflow_id,
            operation=operation,
            objective=objective,
            entities=entities,
            confidence=confidence,
            rationale=rationale,
        )
        return IntentResolution(
            status="supported",
            intent=intent,
            reason=rationale,
            source="llm_normalizer",
        )


def _normalizer_system_prompt() -> str:
    supported = [
        "disk-inspection: disk_usage, disk_usage_with_logs",
        "file-search: filename_search(path, pattern, search_kind=file|directory), content_search(path, pattern), inspect_permissions(path), delete_path(path), chmod_recursive(path, mode)",
        "process-port-inspection: port_lookup(port), top_memory(), service_status(service)",
        "user-management: list_users(), create_user(username, group optional), add_user_to_group(username, group), delete_user(username), batch_delete_users(user_filter), inspect_user(username)",
    ]
    return "\n".join(
        [
            "You are the OpenTower Linux Ops intent normalizer.",
            "Your task is to map a user request into one already-implemented operation, or mark it unsupported.",
            "Prefer unsupported over guessing.",
            "Never propose restart, stop, start, install, firewall, CPU monitoring, log-tail, diagnostics, deployment, package management, or any other unimplemented capability.",
            "Do not emit shell commands.",
            "Supported operations:",
            *[f"- {row}" for row in supported],
            'Return JSON only with this schema: {"status":"supported|unsupported","workflow_id":"...","operation":"...","entities":{},"confidence":0.0,"rationale":"..."}',
        ]
    )


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
        raise ValueError("LLM normalizer did not return a JSON object.")
    return payload


def _normalize_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return min(max(value, 0.0), 1.0)


def _normalize_entities(*, workflow_id: str, operation: str, payload: Any) -> dict[str, Any]:
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("LLM normalizer entities must be an object.")

    def _text(name: str) -> str | None:
        value = payload.get(name)
        text = str(value or "").strip()
        return text or None

    entities: dict[str, Any] = {}

    if operation in {"inspect_permissions", "delete_path", "chmod_recursive"}:
        path = _text("path")
        if not path:
            raise ValueError(f"LLM normalizer missing required entity: path for {operation}")
        entities["path"] = path

    if operation == "chmod_recursive":
        mode = _text("mode") or "777"
        entities["mode"] = mode

    if operation == "filename_search":
        path = _text("path") or "/etc"
        pattern = _text("pattern")
        if not pattern:
            raise ValueError("LLM normalizer missing required entity: pattern for filename_search")
        search_kind = (_text("search_kind") or "file").lower()
        if search_kind not in {"file", "directory"}:
            raise ValueError(f"Unsupported search_kind from LLM normalizer: {search_kind}")
        entities.update({"path": path, "pattern": pattern, "search_kind": search_kind})

    if operation == "content_search":
        path = _text("path") or "/etc"
        pattern = _text("pattern")
        if not pattern:
            raise ValueError("LLM normalizer missing required entity: pattern for content_search")
        entities.update({"path": path, "pattern": pattern})

    if operation == "port_lookup":
        port_raw = payload.get("port")
        if port_raw is None:
            port_raw = payload.get("entities", {}).get("port") if isinstance(payload.get("entities"), dict) else None
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            raise ValueError("LLM normalizer missing required entity: port for port_lookup")
        if not 0 <= port <= 65535:
            raise ValueError(f"Invalid port from LLM normalizer: {port}")
        entities["port"] = port

    if operation == "service_status":
        service = _text("service")
        if not service:
            raise ValueError("LLM normalizer missing required entity: service for service_status")
        entities["service"] = service

    if operation in {"create_user", "delete_user", "inspect_user"}:
        username = _text("username")
        if not username:
            raise ValueError(f"LLM normalizer missing required entity: username for {operation}")
        entities["username"] = username
        group = _text("group")
        if group:
            entities["group"] = group

    if operation == "add_user_to_group":
        username = _text("username")
        group = _text("group")
        if not username or not group:
            raise ValueError("LLM normalizer missing required entity: username/group for add_user_to_group")
        entities["username"] = username
        entities["group"] = group

    if operation == "batch_delete_users":
        user_filter = _text("user_filter")
        if not user_filter:
            raise ValueError("LLM normalizer missing required entity: user_filter for batch_delete_users")
        entities["user_filter"] = user_filter

    if workflow_id == "disk-inspection" and operation == "disk_usage_with_logs":
        path = _text("path")
        if path:
            entities["path"] = path

    return entities


def build_intent_normalizer(*, root: Path) -> StructuredIntentNormalizer | None:
    profile = load_auth_profile(root, create_if_missing=False)
    provider = profile.provider
    if provider == "anthropic":
        if not profile.api_key:
            return None
        client = AnthropicMessagesClient(api_key=profile.api_key, api_url=profile.api_base_url or None)
        return StructuredIntentNormalizer(profile=profile, client=client, model=profile.model)
    if provider == "openai-compatible":
        if not profile.api_key:
            return None
        client = OpenAICompatibleMessagesClient(api_url=profile.api_base_url or None, api_key=profile.api_key)
        return StructuredIntentNormalizer(profile=profile, client=client, model=profile.model)
    client = OllamaMessagesClient(api_url=profile.api_base_url or None, api_key=profile.api_key or None)
    return StructuredIntentNormalizer(profile=profile, client=client, model=profile.model)


__all__ = [
    "SUPPORTED_OPERATIONS",
    "StructuredIntentNormalizer",
    "build_intent_normalizer",
]
