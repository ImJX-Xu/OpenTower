from __future__ import annotations

from opentower_cli.feedback_agent import format_unsupported_response


def test_format_unsupported_response_suggests_supported_rewrites_for_service_mutation() -> None:
    response = format_unsupported_response(
        objective="restart nginx service",
        reason="Could not map the request to a supported Linux operations workflow.",
    )

    assert "try_instead:" in response
    assert "check nginx service status" in response


def test_format_unsupported_response_suggests_cpu_and_load_rewrites() -> None:
    response = format_unsupported_response(
        objective="analyze why the system is slow",
        reason="Could not map the request to a supported Linux operations workflow.",
    )

    assert "show cpu usage" in response
    assert "show load average" in response
