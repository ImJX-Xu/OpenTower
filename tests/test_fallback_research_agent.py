from __future__ import annotations

import json
from pathlib import Path

from opentower_cli.auth_config import AuthProfile
from opentower_cli.config_loader import load_system_config, load_workflows_catalog
from opentower_cli.fallback_research_agent import FallbackResearchAgent
from opentower_cli.intent_parser import resolve_objective
from opentower_cli.ops_types import CommandExecution, Intent, IntentResolution
from opentower_cli.runtime_layout import repo_runtime_layout
from opentower_cli.workflow_executor import execute_workflow


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
        model="deepseek-v4-flash",
        api_base_url="https://example.invalid/v1",
        api_key="sk-test",
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_fallback_research_agent_maps_cpu_request_to_top_cpu() -> None:
    client = FakeClient(
        {
            "status": "supported",
            "workflow_id": "process-port-inspection",
            "operation": "top_cpu",
            "entities": {},
            "confidence": 0.86,
            "risk_level": "low",
            "can_execute_now": True,
            "rationale": "CPU usage requests can be served by a read-only top CPU inspection.",
        }
    )
    agent = FallbackResearchAgent(profile=_profile(), client=client, model="deepseek-v4-flash")

    resolution = agent.research(objective="show cpu usage", prior_reason="Could not map the request", prior_source="llm_normalizer")

    assert resolution.status == "supported"
    assert resolution.source == "fallback_research"
    assert resolution.intent is not None
    assert resolution.intent.operation == "top_cpu"
    assert client.calls == []


def test_fallback_research_agent_maps_load_average_with_local_heuristic() -> None:
    client = FakeClient({"status": "unsupported"})
    agent = FallbackResearchAgent(profile=_profile(), client=client, model="deepseek-v4-flash")

    resolution = agent.research(objective="show load average", prior_reason="unsupported", prior_source="llm_normalizer")

    assert resolution.status == "supported"
    assert resolution.intent is not None
    assert resolution.intent.operation == "load_average"
    assert client.calls == []


def test_fallback_research_agent_infers_workflow_when_model_omits_it() -> None:
    client = FakeClient(
        {
            "status": "supported",
            "workflow_id": None,
            "operation": "tail_log",
            "entities": {
                "path": "/var/log/nginx/error.log",
                "service": "nginx",
                "line_count": 10,
            },
            "confidence": 0.91,
            "risk_level": "low",
            "can_execute_now": True,
            "rationale": "Tailing the nginx error log is a low-risk read-only operation.",
        }
    )
    agent = FallbackResearchAgent(profile=_profile(), client=client, model="deepseek-v4-flash")

    resolution = agent.research(objective="tail the latest nginx error log", prior_reason="unsupported", prior_source="llm_normalizer")

    assert resolution.status == "supported"
    assert resolution.intent is not None
    assert resolution.intent.workflow_id == "file-search"
    assert resolution.intent.operation == "tail_log"
    assert resolution.intent.entities["path"] == "/var/log/nginx/error.log"


def test_fallback_research_agent_prefers_known_operation_when_model_invents_workflow_alias() -> None:
    client = FakeClient(
        {
            "status": "supported",
            "workflow_id": "cpu_monitoring",
            "operation": "top_cpu",
            "entities": {},
            "confidence": 0.9,
            "risk_level": "low",
            "can_execute_now": True,
            "rationale": "CPU usage maps to the low-risk read-only top_cpu operation.",
        }
    )
    agent = FallbackResearchAgent(profile=_profile(), client=client, model="deepseek-v4-flash")

    resolution = agent.research(objective="show cpu usage", prior_reason="unsupported", prior_source="llm_normalizer")

    assert resolution.status == "supported"
    assert resolution.intent is not None
    assert resolution.intent.workflow_id == "process-port-inspection"
    assert resolution.intent.operation == "top_cpu"


def test_fallback_research_agent_declines_write_request() -> None:
    client = FakeClient(
        {
            "status": "unsupported",
            "risk_level": "high",
            "can_execute_now": False,
            "rationale": "Restarting a service is a write action and is outside the fallback safety policy.",
        }
    )
    agent = FallbackResearchAgent(profile=_profile(), client=client, model="deepseek-v4-flash")

    resolution = agent.research(objective="restart nginx service", prior_reason="Could not map the request", prior_source="llm_normalizer")

    assert resolution.status == "unsupported"
    assert resolution.source == "fallback_research"
    assert "outside the fallback safety policy" in resolution.reason


def test_resolve_objective_uses_fallback_agent_after_normalizer_declines() -> None:
    class FakeNormalizer:
        def normalize(self, *, objective: str, workflow_hint: str | None = None) -> IntentResolution:
            return IntentResolution(
                status="unsupported",
                intent=None,
                reason="CPU monitoring is not supported by the deterministic planner.",
                source="llm_normalizer",
            )

    class FakeFallback:
        def research(self, *, objective: str, workflow_hint: str | None = None, prior_reason: str = "", prior_source: str = "") -> IntentResolution:
            assert prior_source == "llm_normalizer"
            assert "CPU monitoring" in prior_reason
            return IntentResolution(
                status="supported",
                source="fallback_research",
                reason="Mapped by fallback research.",
                intent=Intent(
                    workflow_id="process-port-inspection",
                    operation="top_cpu",
                    objective=objective,
                    entities={},
                    confidence=0.8,
                    rationale="Mapped by fallback research.",
                ),
            )

    resolution = resolve_objective("show cpu usage", normalizer=FakeNormalizer(), fallback_agent=FakeFallback())

    assert resolution.status == "supported"
    assert resolution.source == "fallback_research"
    assert resolution.intent is not None
    assert resolution.intent.operation == "top_cpu"


def test_execute_workflow_uses_supplied_intent_without_reparsing(monkeypatch, tmp_path) -> None:
    root = _repo_root()
    system = load_system_config(root)
    workflows = load_workflows_catalog(root)
    layout = repo_runtime_layout(tmp_path)
    layout.ensure_dirs()

    monkeypatch.setattr(
        "opentower_cli.workflow_executor.execute_commands",
        lambda commands, timeout_seconds=30: [
            CommandExecution(
                name="top-cpu",
                command="ps aux --sort=-%cpu | head -6",
                description="List top CPU consumers.",
                stdout="USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND\nroot 1 40.0 0.1 0 0 ? Ss 00:00 0:01 python\n",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
            )
        ],
    )

    result = execute_workflow(
        repo_root=tmp_path,
        system_cfg=system,
        workflow_cfg=next(row for row in workflows["workflows"] if row["id"] == "process-port-inspection"),
        objective="show cpu usage",
        run_id="run-fallback-cpu",
        runtime_layout=layout,
        intent=Intent(
            workflow_id="process-port-inspection",
            operation="top_cpu",
            objective="show cpu usage",
            entities={},
            confidence=0.82,
            rationale="Mapped by fallback research.",
        ),
    )

    assert result.status == "completed"
    assert result.transcript_file.exists()
    assert result.final_output_file.exists()
