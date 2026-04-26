from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from opentower_cli import runtime_service as runtime_service_mod
from opentower_cli.engine import DispatchResult
from opentower_cli.ops_types import Intent
from opentower_cli.runtime_service import DispatchExecutionBundle, RuntimeBundle, dispatch_and_maybe_execute, load_repo_configs


def _dispatch_result(tmp_path: Path, *, run_id: str, intent: Intent | None = None) -> DispatchResult:
    return DispatchResult(
        run_id=run_id,
        workflow_id="disk-inspection",
        objective="查看磁盘使用情况",
        category="inspect",
        agents=["intent-parser"],
        handoff_chain=["intent-parser", "security-guard", "command-planner", "result-analyst"],
        acceptance_checks=["df_parsed"],
        log_file=tmp_path / f"{run_id}.json",
        intent=intent,
    )


def _unsupported_dispatch_result(tmp_path: Path, *, run_id: str) -> DispatchResult:
    return DispatchResult(
        run_id=run_id,
        workflow_id="unsupported",
        objective="show cpu usage",
        category="unsupported",
        agents=["intent-parser"],
        handoff_chain=["intent-parser"],
        acceptance_checks=[],
        log_file=tmp_path / f"{run_id}.json",
        resolution_status="unsupported",
        resolution_reason="Could not map the request to a supported Linux operations workflow.",
        user_message="unsupported",
    )


def test_load_repo_configs_reads_new_linux_ops_schema() -> None:
    root = Path(__file__).resolve().parents[1]
    system_cfg, workflows_cfg = load_repo_configs(root)

    assert system_cfg["system"]["name"] == "OpenTower Linux Ops"
    assert [workflow["id"] for workflow in workflows_cfg["workflows"]] == [
        "disk-inspection",
        "file-search",
        "process-port-inspection",
        "user-management",
    ]


def test_dispatch_and_maybe_execute_uses_preloaded_runtime_without_reloading(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}
    runtime = RuntimeBundle(
        system_cfg={"system": {"name": "Preloaded Runtime"}},
        skills_cfg={"workflows": [{"id": "disk-inspection", "category": "inspect"}]},
    )

    def fail_load_runtime_bundle(**_: object):
        raise AssertionError("load_runtime_bundle should not run when runtime is preloaded")

    def fake_dispatch(**kwargs):
        observed["dispatch_kwargs"] = kwargs
        return _dispatch_result(tmp_path, run_id="run-123")

    monkeypatch.setattr(runtime_service_mod, "load_runtime_bundle", fail_load_runtime_bundle)

    result = dispatch_and_maybe_execute(
        root=tmp_path,
        objective="查看磁盘使用情况",
        runtime=runtime,
        execute=False,
        dispatch_impl=fake_dispatch,
    )

    assert isinstance(result, DispatchExecutionBundle)
    assert result.runtime is runtime
    assert result.execution_result is None
    assert observed["dispatch_kwargs"]["objective"] == "查看磁盘使用情况"


def test_dispatch_and_maybe_execute_executes_workflow(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_load_runtime_bundle(*, root: Path) -> RuntimeBundle:
        return RuntimeBundle(
            system_cfg={"system": {"name": "Linux Ops"}},
            skills_cfg={"workflows": [{"id": "disk-inspection", "category": "inspect"}]},
        )

    def fake_dispatch(**kwargs):
        observed["dispatch_kwargs"] = kwargs
        return _dispatch_result(tmp_path, run_id="run-456")

    def fake_execute_workflow(**kwargs):
        observed["execute_kwargs"] = kwargs
        return SimpleNamespace(
            transcript_file=tmp_path / "transcript.md",
            final_output_file=tmp_path / "final.md",
            group_chat_file=tmp_path / "group.md",
            final_output="done",
            status="completed",
            confirmation_id=None,
        )

    monkeypatch.setattr(runtime_service_mod, "load_runtime_bundle", fake_load_runtime_bundle)

    result = dispatch_and_maybe_execute(
        root=tmp_path,
        objective="查看磁盘使用情况",
        execute=True,
        dispatch_impl=fake_dispatch,
        execute_workflow_impl=fake_execute_workflow,
    )

    assert result.dispatch_result.run_id == "run-456"
    assert result.execution_result is not None
    assert observed["execute_kwargs"]["workflow_cfg"]["id"] == "disk-inspection"


def test_dispatch_and_maybe_execute_passes_resolved_intent_into_execution(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_load_runtime_bundle(*, root: Path) -> RuntimeBundle:
        return RuntimeBundle(
            system_cfg={"system": {"name": "Linux Ops"}},
            skills_cfg={"workflows": [{"id": "process-port-inspection", "category": "inspect"}]},
        )

    resolved_intent = Intent(
        workflow_id="process-port-inspection",
        operation="top_cpu",
        objective="show cpu usage",
        entities={},
        confidence=0.81,
        rationale="Mapped by fallback research.",
    )

    def fake_dispatch(**kwargs):
        observed["dispatch_kwargs"] = kwargs
        return DispatchResult(
            run_id="run-fallback",
            workflow_id="process-port-inspection",
            objective="show cpu usage",
            category="inspect",
            agents=["intent-parser"],
            handoff_chain=["intent-parser", "security-guard", "command-planner", "result-analyst"],
            acceptance_checks=["natural_language_feedback"],
            log_file=tmp_path / "run-fallback.json",
            resolution_status="supported",
            resolution_source="fallback_research",
            resolution_reason="Mapped by fallback research.",
            intent=resolved_intent,
        )

    def fake_execute_workflow(**kwargs):
        observed["execute_kwargs"] = kwargs
        return SimpleNamespace(
            transcript_file=tmp_path / "transcript.md",
            final_output_file=tmp_path / "final.md",
            group_chat_file=tmp_path / "group.md",
            final_output="done",
            status="completed",
            confirmation_id=None,
        )

    monkeypatch.setattr(runtime_service_mod, "load_runtime_bundle", fake_load_runtime_bundle)

    result = dispatch_and_maybe_execute(
        root=tmp_path,
        objective="show cpu usage",
        execute=True,
        dispatch_impl=fake_dispatch,
        execute_workflow_impl=fake_execute_workflow,
    )

    assert result.execution_result is not None
    assert observed["execute_kwargs"]["intent"] == resolved_intent


def test_dispatch_and_maybe_execute_skips_execution_for_unsupported_result(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_load_runtime_bundle(*, root: Path) -> RuntimeBundle:
        return RuntimeBundle(
            system_cfg={"system": {"name": "Linux Ops"}},
            skills_cfg={"workflows": [{"id": "disk-inspection", "category": "inspect"}]},
        )

    def fake_dispatch(**kwargs):
        observed["dispatch_kwargs"] = kwargs
        return _unsupported_dispatch_result(tmp_path, run_id="run-unsupported")

    def fail_execute_workflow(**kwargs):
        raise AssertionError("execute_workflow should not run for unsupported requests")

    monkeypatch.setattr(runtime_service_mod, "load_runtime_bundle", fake_load_runtime_bundle)

    result = dispatch_and_maybe_execute(
        root=tmp_path,
        objective="show cpu usage",
        execute=True,
        dispatch_impl=fake_dispatch,
        execute_workflow_impl=fail_execute_workflow,
    )

    assert result.dispatch_result.run_id == "run-unsupported"
    assert result.dispatch_result.resolution_status == "unsupported"
    assert result.execution_result is None
