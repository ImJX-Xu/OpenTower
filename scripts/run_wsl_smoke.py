from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.append(str(RUNTIME_DIR))

from opentower_cli.runtime_service import dispatch_and_maybe_execute, load_runtime_bundle  # noqa: E402


DEFAULT_JSON_OUTPUT = REPO_ROOT / "production" / "eval-reports" / "wsl_smoke_summary.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "production" / "eval-reports" / "wsl_smoke_summary.md"


@dataclass(frozen=True)
class SmokeCase:
    name: str
    objective: str
    expected_resolution_status: str
    expected_execution_status: str | None
    execute: bool = True
    expected_resolution_source: str | None = None


def default_cases() -> list[SmokeCase]:
    return [
        SmokeCase("disk_usage", "查看磁盘使用情况", "supported", "completed"),
        SmokeCase("file_search", "找到所有 nginx 配置文件", "supported", "completed"),
        SmokeCase("service_status", "check sshd service status", "supported", "completed"),
        SmokeCase("top_cpu", "show cpu usage", "supported", "completed"),
        SmokeCase("load_average", "show load average", "supported", "completed"),
        SmokeCase("tail_syslog", "tail the latest syslog log", "supported", "completed"),
        SmokeCase("create_user_confirm", "create user smokeuser", "supported", "pending_confirmation"),
        SmokeCase("group_update_confirm", "将用户 dev01 加入 sudo 组", "supported", "pending_confirmation"),
        SmokeCase("critical_delete_block", "删除 /etc", "supported", "completed"),
        SmokeCase("unsupported_restart", "restart nginx service", "unsupported", None),
    ]


def _output_excerpt(bundle: Any) -> str:
    execution = bundle.execution_result
    if execution is not None:
        return str(execution.final_output or "").strip()[:300]
    return str(bundle.dispatch_result.user_message or "").strip()[:300]


def _run_case(case: SmokeCase, *, runtime: Any) -> dict[str, Any]:
    bundle = dispatch_and_maybe_execute(
        root=REPO_ROOT,
        objective=case.objective,
        runtime=runtime,
        execute=case.execute,
    )
    dispatch_result = bundle.dispatch_result
    execution_result = bundle.execution_result
    actual_execution_status = execution_result.status if execution_result is not None else None
    passed = dispatch_result.resolution_status == case.expected_resolution_status
    if case.expected_execution_status is not None:
        passed = passed and actual_execution_status == case.expected_execution_status
    if case.expected_resolution_source is not None:
        passed = passed and dispatch_result.resolution_source == case.expected_resolution_source
    if case.name == "critical_delete_block" and execution_result is not None:
        passed = passed and "操作已拦截" in execution_result.final_output

    return {
        "name": case.name,
        "objective": case.objective,
        "expected_resolution_status": case.expected_resolution_status,
        "expected_execution_status": case.expected_execution_status,
        "actual_resolution_status": dispatch_result.resolution_status,
        "actual_resolution_source": dispatch_result.resolution_source,
        "actual_execution_status": actual_execution_status,
        "passed": passed,
        "log_file": str(dispatch_result.log_file),
        "output_excerpt": _output_excerpt(bundle),
    }


def _render_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# WSL Smoke Summary",
        "",
        f"- total_cases: {len(results)}",
        f"- passed_cases: {sum(1 for row in results if row['passed'])}",
        f"- failed_cases: {sum(1 for row in results if not row['passed'])}",
        "",
    ]
    for row in results:
        lines.extend(
            [
                f"## {row['name']}",
                "",
                f"- objective: {row['objective']}",
                f"- passed: {str(row['passed']).lower()}",
                f"- actual_resolution_status: {row['actual_resolution_status']}",
                f"- actual_resolution_source: {row['actual_resolution_source']}",
                f"- actual_execution_status: {row['actual_execution_status'] or '-'}",
                f"- log_file: {row['log_file']}",
                "",
                "```text",
                row["output_excerpt"] or "(no output excerpt)",
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-mostly WSL smoke suite for OpenTower Linux Ops.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT), help="JSON summary output path")
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT), help="Markdown summary output path")
    args = parser.parse_args()

    json_output = Path(args.json_output).resolve()
    md_output = Path(args.md_output).resolve()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)

    runtime = load_runtime_bundle(root=REPO_ROOT)
    results = [_run_case(case, runtime=runtime) for case in default_cases()]
    summary = {
        "total_cases": len(results),
        "passed_cases": sum(1 for row in results if row["passed"]),
        "failed_cases": sum(1 for row in results if not row["passed"]),
        "results": results,
    }
    json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_output.write_text(_render_markdown(results), encoding="utf-8")

    print(f"total_cases: {summary['total_cases']}")
    print(f"passed_cases: {summary['passed_cases']}")
    print(f"failed_cases: {summary['failed_cases']}")
    print(f"json_output: {json_output}")
    print(f"md_output: {md_output}")
    return 0 if summary["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
