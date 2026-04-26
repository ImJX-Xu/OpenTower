from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.append(str(RUNTIME_DIR))

from opentower_cli.intent_parser import resolve_objective  # noqa: E402
from opentower_cli.security_agent import assess_intent  # noqa: E402


DEFAULT_INPUT = REPO_ROOT / "tests" / "fixtures" / "nl_eval_cases.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "production" / "eval-reports" / "nl_eval_summary.json"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    text = str(case.get("text", "") or "")
    resolution = resolve_objective(text)
    actual: dict[str, Any] = {
        "resolution_status": resolution.status,
        "workflow_id": None,
        "operation": None,
        "security_decision": None,
        "risk_level": None,
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
        "text": text,
        "expected_status": expected_status,
        "actual": actual,
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    mismatch_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    for result in results:
        status_counter[str(result.get("expected_status", "") or "")] += 1
        mismatch_counter.update(result.get("mismatches", []))

    failures = [result for result in results if not result["passed"]]
    return {
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result["passed"]),
        "failed_cases": len(failures),
        "expected_status_counts": dict(status_counter),
        "mismatch_counts": dict(mismatch_counter),
        "sample_failures": failures[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the OpenTower NL eval corpus against the local parser.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="JSONL eval corpus path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON summary output path")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for quick runs")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cases = _load_cases(input_path)
    if args.limit > 0:
        cases = cases[: args.limit]

    results = [_evaluate_case(case) for case in cases]
    summary = _summarize(results)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"input_cases: {len(cases)}")
    print(f"passed_cases: {summary['passed_cases']}")
    print(f"failed_cases: {summary['failed_cases']}")
    print(f"output: {output_path}")
    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
