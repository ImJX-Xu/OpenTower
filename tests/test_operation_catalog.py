from __future__ import annotations

from opentower_cli.operation_catalog import (
    FALLBACK_RESEARCH,
    LLM_NORMALIZER,
    parser_kind_for_operation,
    render_supported_operation_rows,
    supported_operations_by_source,
)


def test_supported_operations_by_source_splits_normalizer_and_fallback_surfaces() -> None:
    normalizer = supported_operations_by_source(LLM_NORMALIZER)
    fallback = supported_operations_by_source(FALLBACK_RESEARCH)

    assert normalizer["process-port-inspection"] == {"port_lookup", "service_status", "top_memory"}
    assert fallback["process-port-inspection"] == {"load_average", "service_status", "top_cpu", "top_memory", "uptime_summary"}
    assert "tail_log" not in normalizer.get("file-search", set())
    assert fallback["file-search"] == {"recent_error_scan", "tail_log"}


def test_parser_kind_for_operation_comes_from_catalog() -> None:
    assert parser_kind_for_operation("delete_path", "file-search") == "destructive-path"
    assert parser_kind_for_operation("chmod_recursive", "file-search") == "chmod"
    assert parser_kind_for_operation("recent_error_scan", "file-search") == "log"


def test_render_supported_operation_rows_builds_prompt_friendly_catalog_lines() -> None:
    normalizer_rows = render_supported_operation_rows(LLM_NORMALIZER)
    fallback_rows = render_supported_operation_rows(FALLBACK_RESEARCH)

    assert any(row.startswith("disk-inspection:") for row in normalizer_rows)
    assert any("service_status(service)" in row for row in normalizer_rows)
    assert any("top_cpu()" in row for row in fallback_rows)
    assert any("tail_log(path, line_count optional, service optional)" in row for row in fallback_rows)
