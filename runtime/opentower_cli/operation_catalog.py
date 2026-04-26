from __future__ import annotations

from dataclasses import dataclass


LOCAL_RULE = "local_rule"
LLM_NORMALIZER = "llm_normalizer"
FALLBACK_RESEARCH = "fallback_research"


@dataclass(frozen=True)
class OperationSpec:
    workflow_id: str
    operation: str
    parser_kind: str
    signature: str
    resolution_sources: frozenset[str]


OPERATION_SPECS: tuple[OperationSpec, ...] = (
    OperationSpec(
        workflow_id="disk-inspection",
        operation="disk_usage",
        parser_kind="disk",
        signature="disk_usage()",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="disk-inspection",
        operation="disk_usage_with_logs",
        parser_kind="disk",
        signature="disk_usage_with_logs(path optional)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="filename_search",
        parser_kind="file-search",
        signature="filename_search(path, pattern, search_kind=file|directory)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="content_search",
        parser_kind="file-search",
        signature="content_search(path, pattern)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="inspect_permissions",
        parser_kind="file-search",
        signature="inspect_permissions(path)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="delete_path",
        parser_kind="destructive-path",
        signature="delete_path(path)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="chmod_recursive",
        parser_kind="chmod",
        signature="chmod_recursive(path, mode)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="tail_log",
        parser_kind="log",
        signature="tail_log(path, line_count optional, service optional)",
        resolution_sources=frozenset({FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="file-search",
        operation="recent_error_scan",
        parser_kind="log",
        signature="recent_error_scan(path, limit optional, service optional)",
        resolution_sources=frozenset({FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="port_lookup",
        parser_kind="process",
        signature="port_lookup(port)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="top_memory",
        parser_kind="process",
        signature="top_memory()",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER, FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="service_status",
        parser_kind="process",
        signature="service_status(service)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER, FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="top_cpu",
        parser_kind="process",
        signature="top_cpu()",
        resolution_sources=frozenset({FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="load_average",
        parser_kind="process",
        signature="load_average()",
        resolution_sources=frozenset({FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="process-port-inspection",
        operation="uptime_summary",
        parser_kind="process",
        signature="uptime_summary()",
        resolution_sources=frozenset({FALLBACK_RESEARCH}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="list_users",
        parser_kind="user-management",
        signature="list_users()",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="create_user",
        parser_kind="user-management",
        signature="create_user(username, group optional)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="add_user_to_group",
        parser_kind="user-management",
        signature="add_user_to_group(username, group)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="delete_user",
        parser_kind="user-management",
        signature="delete_user(username)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="batch_delete_users",
        parser_kind="user-management",
        signature="batch_delete_users(user_filter)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
    OperationSpec(
        workflow_id="user-management",
        operation="inspect_user",
        parser_kind="user-management",
        signature="inspect_user(username)",
        resolution_sources=frozenset({LOCAL_RULE, LLM_NORMALIZER}),
    ),
)


def operation_spec(operation: str, workflow_id: str | None = None) -> OperationSpec | None:
    clean_operation = str(operation or "").strip()
    clean_workflow = str(workflow_id or "").strip()
    for spec in OPERATION_SPECS:
        if spec.operation != clean_operation:
            continue
        if clean_workflow and spec.workflow_id != clean_workflow:
            continue
        return spec
    return None


def parser_kind_for_operation(operation: str, workflow_id: str | None = None, *, default: str | None = None) -> str:
    spec = operation_spec(operation, workflow_id)
    if spec is not None:
        return spec.parser_kind
    if default is not None:
        return default
    raise ValueError(f"Unknown operation metadata: {workflow_id or '*'} / {operation}")


def supported_operations_by_source(source: str) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for spec in OPERATION_SPECS:
        if source not in spec.resolution_sources:
            continue
        grouped.setdefault(spec.workflow_id, set()).add(spec.operation)
    return grouped


def render_supported_operation_rows(source: str) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for spec in OPERATION_SPECS:
        if source not in spec.resolution_sources:
            continue
        grouped.setdefault(spec.workflow_id, []).append(spec.signature)
    return [f"{workflow_id}: {', '.join(grouped[workflow_id])}" for workflow_id in sorted(grouped)]


__all__ = [
    "FALLBACK_RESEARCH",
    "LLM_NORMALIZER",
    "LOCAL_RULE",
    "OPERATION_SPECS",
    "OperationSpec",
    "operation_spec",
    "parser_kind_for_operation",
    "render_supported_operation_rows",
    "supported_operations_by_source",
]
