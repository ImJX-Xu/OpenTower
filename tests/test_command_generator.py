from __future__ import annotations

from opentower_cli.command_generator import plan_commands
from opentower_cli.ops_types import Intent, SecurityAssessment


def _allow_assessment() -> SecurityAssessment:
    return SecurityAssessment(decision="allow", risk_level="low", reason="ok")


def test_plan_commands_supports_permission_inspection() -> None:
    plan = plan_commands(
        Intent(
            workflow_id="file-search",
            operation="inspect_permissions",
            objective="查看 /etc/passwd 权限",
            entities={"path": "/etc/passwd"},
        ),
        _allow_assessment(),
    )

    assert plan.parser_kind == "file-search"
    assert len(plan.execution_commands) == 1
    assert plan.execution_commands[0].command == "ls -ld -- /etc/passwd"


def test_plan_commands_supports_listing_users() -> None:
    plan = plan_commands(
        Intent(
            workflow_id="user-management",
            operation="list_users",
            objective="查看所有用户",
            entities={},
        ),
        _allow_assessment(),
    )

    assert plan.parser_kind == "user-management"
    assert len(plan.execution_commands) == 1
    assert "getent passwd" in plan.execution_commands[0].command


def test_plan_commands_uses_directory_search_when_requested() -> None:
    plan = plan_commands(
        Intent(
            workflow_id="file-search",
            operation="filename_search",
            objective="查找 cache 目录",
            entities={"path": "/var", "pattern": "*cache*", "search_kind": "directory"},
        ),
        _allow_assessment(),
    )

    assert plan.parser_kind == "file-search"
    assert len(plan.execution_commands) == 1
    assert plan.execution_commands[0].command == "find /var -type d -name '*cache*' 2>/dev/null"


def test_plan_commands_service_status_avoids_matching_the_dispatch_command_itself() -> None:
    plan = plan_commands(
        Intent(
            workflow_id="process-port-inspection",
            operation="service_status",
            objective="check sshd service status",
            entities={"service": "sshd"},
        ),
        _allow_assessment(),
    )

    assert plan.parser_kind == "process"
    assert len(plan.execution_commands) == 1
    assert plan.execution_commands[0].command == "systemctl status sshd --no-pager 2>/dev/null || ps -C sshd -o pid=,comm=,args= 2>/dev/null"
