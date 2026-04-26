from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_eval_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "run_nl_eval.py"
    spec = importlib.util.spec_from_file_location("run_nl_eval", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summarize_tracks_sources_and_latency() -> None:
    module = _load_eval_module()
    context = module.EvalContext(with_model=True, provider="openai-compatible", configured_model="gpt-test")
    results = [
        {
            "language": "en",
            "expected_status": "allow",
            "notes": "Disk inspection",
            "passed": True,
            "mismatches": [],
            "actual": {"resolution_source": "local_rule", "latency_ms": 12.5},
        },
        {
            "language": "zh",
            "expected_status": "unsupported",
            "notes": "Out of scope request",
            "passed": False,
            "mismatches": ["resolution_status"],
            "actual": {"resolution_source": "fallback_research", "latency_ms": 40.0},
        },
    ]

    summary = module._summarize(results, context=context, fixture_profile="model")

    assert summary["with_model"] is True
    assert summary["provider"] == "openai-compatible"
    assert summary["resolution_source_counts"] == {"local_rule": 1, "fallback_research": 1}
    assert summary["passed_by_source"] == {"local_rule": 1}
    assert summary["failed_by_source"] == {"fallback_research": 1}
    assert summary["average_latency_ms"] == 26.25


def test_build_eval_context_requires_model_stage_when_enabled(monkeypatch, tmp_path) -> None:
    module = _load_eval_module()
    monkeypatch.setattr(module, "load_auth_profile", lambda root, create_if_missing=False: object())
    monkeypatch.setattr(module, "load_intent_normalizer", lambda root: None)
    monkeypatch.setattr(module, "load_fallback_research_agent", lambda root: None)

    with pytest.raises(RuntimeError, match="No model-backed stages are available"):
        module._build_eval_context(root=tmp_path, with_model=True)
