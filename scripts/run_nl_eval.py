from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.append(str(RUNTIME_DIR))

from opentower_cli.auth_config import load_auth_profile  # noqa: E402
from opentower_cli.intent_parser import resolve_objective  # noqa: E402
from opentower_cli.runtime_service import load_fallback_research_agent, load_intent_normalizer  # noqa: E402
from opentower_cli.security_agent import assess_intent  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "tests" / "fixtures" / "nl_eval_cases.jsonl"
DEFAULT_CORE_INPUT = REPO_ROOT / "tests" / "fixtures" / "nl_eval_cases.core.jsonl"
DEFAULT_MODEL_INPUT = REPO_ROOT / "tests" / "fixtures" / "nl_eval_cases.model.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "production" / "eval-reports" / "nl_eval_summary.json"
FIXTURE_INPUTS = {
    "extended": DEFAULT_INPUT,
    "core": DEFAULT_CORE_INPUT,
    "model": DEFAULT_MODEL_INPUT,
}


@dataclass(frozen=True)
class EvalContext:
    with_model: bool
    provider: str | None = None
    configured_model: str | None = None
    normalizer: Any | None = None
    fallback_agent: Any | None = None


def _load_cases(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _fixture_input_path(*, fixture_profile: str, explicit_input: str | None = None) -> Path:
    if explicit_input:
        return Path(explicit_input).resolve()
    return FIXTURE_INPUTS[fixture_profile].resolve()


def _build_eval_context(*, root: Path, with_model: bool) -> EvalContext:
    if not with_model:
        return EvalContext(with_model=False)

    profile = load_auth_profile(root, create_if_missing=False)
    normalizer = load_intent_normalizer(root=root)
    fallback_agent = load_fallback_research_agent(root=root)
    if normalizer is None and fallback_agent is None:
        raise RuntimeError("No model-backed stages are available. Configure auth.json or use pure local replay.")
    return EvalContext(
        with_model=True,
        provider=profile.provider,
        configured_model=profile.model or "auto",
        normalizer=normalizer,
        fallback_agent=fallback_agent,
    )


def _evaluate_case(case: dict[str, Any], *, context: EvalContext) -> dict[str, Any]:
    text = str(case.get("text", "") or "")
    started = time.perf_counter()
    resolution = resolve_objective(
        text,
        normalizer=context.normalizer,
        fallback_agent=context.fallback_agent,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 3)

    actual: dict[str, Any] = {
        "resolution_status": resolution.status,
        "resolution_source": resolution.source,
        "resolution_reason": resolution.reason,
        "workflow_id": None,
        "operation": None,
        "security_decision": None,
        "risk_level": None,
        "latency_ms": latency_ms,
    }
    if resolution.status == "supported" and resolution.intent is not None:
        actual["workflow_id"] = resolution.intent.workflow_id
        actual["operation"] = resolution.intent.operation
        assessment = assess_intent(resolution.intent)
        actual["security_decision"] = assessment.decision
        actual["risk_level"] = assessment.risk_level

    expected_status = str(case.get("expected_status", "") or "").strip()
    expected_resolution_status = str(case.get("expected_resolution_status", "") or "").strip()
    expected_workflow_id = case.get("expected_workflow_id")
    expected_operation = case.get("expected_operation")
    expected_security_decision = case.get("expected_security_decision")
    expected_risk_level = case.get("expected_risk_level")

    mismatches: list[str] = []
    if expected_resolution_status and actual["resolution_status"] != expected_resolution_status:
        mismatches.append("resolution_status")
    if expected_workflow_id is not None and actual["workflow_id"] != expected_workflow_id:
        mismatches.append("workflow_id")
    if expected_operation is not None and actual["operation"] != expected_operation:
        mismatches.append("operation")
    if expected_security_decision is not None and actual["security_decision"] != expected_security_decision:
        mismatches.append("security_decision")
    if expected_risk_level is not None and actual["risk_level"] != expected_risk_level:
        mismatches.append("risk_level")

    return {
        "id": case.get("id"),
        "language": case.get("language"),
        "text": text,
        "expected_status": expected_status,
        "notes": case.get("notes"),
        "actual": actual,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def _summarize(results: list[dict[str, Any]], *, context: EvalContext, fixture_profile: str) -> dict[str, Any]:
    mismatch_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    note_counter: Counter[str] = Counter()
    language_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    passed_by_source: Counter[str] = Counter()
    failed_by_source: Counter[str] = Counter()
    latency_by_source: defaultdict[str, list[float]] = defaultdict(list)

    for result in results:
        status_counter[str(result.get("expected_status", "") or "")] += 1
        mismatch_counter.update(result.get("mismatches", []))
        note_counter[str(result.get("notes", "") or "")] += 1
        language_counter[str(result.get("language", "") or "")] += 1

        actual = result.get("actual", {})
        source = str(actual.get("resolution_source", "local_rule") or "local_rule")
        source_counter[source] += 1
        latency_by_source[source].append(float(actual.get("latency_ms", 0.0) or 0.0))
        if result["passed"]:
            passed_by_source[source] += 1
        else:
            failed_by_source[source] += 1

    failures = [result for result in results if not result["passed"]]
    sample_failures_by_source: dict[str, list[dict[str, Any]]] = {}
    for source in source_counter:
        sample_failures_by_source[source] = [row for row in failures if row["actual"]["resolution_source"] == source][:5]

    average_latency_ms_by_source = {
        source: round(sum(values) / len(values), 3) if values else 0.0
        for source, values in latency_by_source.items()
    }
    average_latency_ms = round(
        sum(sum(values) for values in latency_by_source.values()) / len(results),
        3,
    ) if results else 0.0

    return {
        "fixture_profile": fixture_profile,
        "with_model": context.with_model,
        "provider": context.provider,
        "configured_model": context.configured_model,
        "normalizer_enabled": context.normalizer is not None,
        "fallback_enabled": context.fallback_agent is not None,
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result["passed"]),
        "failed_cases": len(failures),
        "expected_status_counts": dict(status_counter),
        "note_counts": dict(note_counter),
        "language_counts": dict(language_counter),
        "resolution_source_counts": dict(source_counter),
        "passed_by_source": dict(passed_by_source),
        "failed_by_source": dict(failed_by_source),
        "average_latency_ms": average_latency_ms,
        "average_latency_ms_by_source": average_latency_ms_by_source,
        "mismatch_counts": dict(mismatch_counter),
        "sample_failures": failures[:20],
        "sample_failures_by_source": sample_failures_by_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the OpenTower NL eval corpus against the local parser.")
    parser.add_argument("--input", default="", help="Optional JSONL eval corpus path")
    parser.add_argument("--fixture-profile", choices=sorted(FIXTURE_INPUTS), default="extended", help="Named fixture profile when --input is omitted")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON summary output path")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for quick runs")
    parser.add_argument("--with-model", action="store_true", help="Use the configured normalizer/fallback model chain instead of pure local rules")
    args = parser.parse_args()

    input_path = _fixture_input_path(fixture_profile=args.fixture_profile, explicit_input=str(args.input or "").strip() or None)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    context = _build_eval_context(root=REPO_ROOT, with_model=bool(args.with_model))
    cases = _load_cases(input_path)
    if args.limit > 0:
        cases = cases[: args.limit]

    results = [_evaluate_case(case, context=context) for case in cases]
    summary = _summarize(results, context=context, fixture_profile=args.fixture_profile)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"fixture_profile: {args.fixture_profile}")
    print(f"with_model: {str(context.with_model).lower()}")
    if context.provider:
        print(f"provider: {context.provider}")
        print(f"configured_model: {context.configured_model}")
    print(f"input_cases: {len(cases)}")
    print(f"passed_cases: {summary['passed_cases']}")
    print(f"failed_cases: {summary['failed_cases']}")
    print(f"output: {output_path}")
    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
