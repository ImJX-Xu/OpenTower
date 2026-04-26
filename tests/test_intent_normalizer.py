from __future__ import annotations

import json
from pathlib import Path

from opentower_cli.auth_config import AuthProfile
from opentower_cli.intent_normalizer import StructuredIntentNormalizer
from opentower_cli.intent_parser import resolve_objective
from opentower_cli.ops_types import Intent, IntentResolution


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def create_message(self, *, system: str, user_text: str, model: str | None = None, max_tokens: int = 1400, temperature: float = 0.2):
        self.calls.append(
            {
                "system": system,
                "user_text": user_text,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return type("Resp", (), {"text": json.dumps(self.payload)})()


def _profile() -> AuthProfile:
    return AuthProfile(
        path=Path("auth.json"),
        provider="openai-compatible",
        model="gpt-4o-mini",
        api_base_url="https://example.invalid/v1",
        api_key="sk-test",
    )


def test_structured_intent_normalizer_maps_supported_service_status() -> None:
    client = FakeClient(
        {
            "status": "supported",
            "workflow_id": "process-port-inspection",
            "operation": "service_status",
            "entities": {"service": "nginx"},
            "confidence": 0.91,
            "rationale": "The request is asking to inspect the nginx service state.",
        }
    )
    normalizer = StructuredIntentNormalizer(profile=_profile(), client=client, model="gpt-4o-mini")

    resolution = normalizer.normalize(objective="check nginx service status")

    assert resolution.status == "supported"
    assert resolution.source == "llm_normalizer"
    assert resolution.intent is not None
    assert resolution.intent.workflow_id == "process-port-inspection"
    assert resolution.intent.operation == "service_status"
    assert resolution.intent.entities["service"] == "nginx"
    assert client.calls[0]["user_text"] == "check nginx service status"


def test_structured_intent_normalizer_returns_unsupported_when_model_declines() -> None:
    client = FakeClient(
        {
            "status": "unsupported",
            "rationale": "CPU usage monitoring is not implemented in the current deterministic planner.",
        }
    )
    normalizer = StructuredIntentNormalizer(profile=_profile(), client=client, model="gpt-4o-mini")

    resolution = normalizer.normalize(objective="show cpu usage")

    assert resolution.status == "unsupported"
    assert resolution.intent is None
    assert resolution.source == "llm_normalizer"
    assert "not implemented" in resolution.reason


def test_structured_intent_normalizer_accepts_fenced_json() -> None:
    class FencedClient(FakeClient):
        def create_message(self, *, system: str, user_text: str, model: str | None = None, max_tokens: int = 1400, temperature: float = 0.2):
            return type(
                "Resp",
                (),
                {
                    "text": "```json\n"
                    + json.dumps(
                        {
                            "status": "supported",
                            "workflow_id": "process-port-inspection",
                            "operation": "service_status",
                            "entities": {"service": "nginx"},
                            "confidence": 0.93,
                            "rationale": "The request asks for service status.",
                        }
                    )
                    + "\n```"
                },
            )()

    normalizer = StructuredIntentNormalizer(profile=_profile(), client=FencedClient({}), model="gpt-4o-mini")
    resolution = normalizer.normalize(objective="check nginx service status")

    assert resolution.status == "supported"
    assert resolution.intent is not None
    assert resolution.intent.operation == "service_status"


def test_resolve_objective_uses_normalizer_after_local_rule_failure() -> None:
    class FakeNormalizer:
        def normalize(self, *, objective: str, workflow_hint: str | None = None) -> IntentResolution:
            return IntentResolution(
                status="supported",
                source="llm_normalizer",
                reason="Mapped by fake normalizer.",
                intent=Intent(
                    workflow_id="process-port-inspection",
                    operation="service_status",
                    objective=objective,
                    entities={"service": "nginx"},
                    confidence=0.84,
                    rationale="Mapped by fake normalizer.",
                ),
            )

    resolution = resolve_objective("check nginx service status", normalizer=FakeNormalizer())

    assert resolution.status == "supported"
    assert resolution.source == "llm_normalizer"
    assert resolution.intent is not None
    assert resolution.intent.operation == "service_status"
