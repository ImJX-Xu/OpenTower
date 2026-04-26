from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_generator_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "generate_nl_eval_seed.py"
    spec = importlib.util.spec_from_file_location("generate_nl_eval_seed", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_seed_cases_generates_large_unique_corpus() -> None:
    module = _load_generator_module()

    cases = module.build_seed_cases()

    assert len(cases) >= module.MIN_EXPECTED_CASES
    ids = [str(case["id"]) for case in cases]
    texts = [str(case["text"]) for case in cases]
    assert len(ids) == len(set(ids))
    assert len(texts) == len(set(texts))


def test_build_profile_cases_returns_smaller_deterministic_subsets() -> None:
    module = _load_generator_module()

    cases = module.build_seed_cases()
    core_cases = module.build_profile_cases(cases, profile="core")
    model_cases = module.build_profile_cases(cases, profile="model")

    assert len(core_cases) < len(cases)
    assert len(model_cases) < len(core_cases)
    assert len(core_cases) > 300
    assert len(model_cases) > 150
    assert core_cases[0]["id"] == "nl-eval-0001"
    assert model_cases[0]["id"] == "nl-eval-0001"
