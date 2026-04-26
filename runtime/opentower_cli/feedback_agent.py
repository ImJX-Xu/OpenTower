from __future__ import annotations

from typing import Any

from .ops_types import CommandExecution, CommandPlan, Intent, SecurityAssessment


def _command_errors(results: list[CommandExecution]) -> list[str]:
    messages: list[str] = []
    for result in results:
        if result.returncode == 0 and not result.timed_out:
            continue
        if result.allow_failure:
            continue
        if "Permission denied" in result.stderr or "permission denied" in result.stderr.lower():
            messages.append(f"`{result.command}` failed due to insufficient permissions.")
        elif result.timed_out:
            messages.append(f"`{result.command}` timed out.")
        elif result.stderr.strip():
            messages.append(f"`{result.command}` failed: {result.stderr.strip()}")
    return messages


def parse_preview(plan: CommandPlan, results: list[CommandExecution]) -> dict[str, Any]:
    if plan.preview_parser_kind == "user-batch-preview":
        candidates: list[dict[str, str]] = []
        for result in results:
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split(":", 2)
                if len(parts) != 3:
                    continue
                candidates.append({"username": parts[0], "uid": parts[1], "home": parts[2]})
        return {"candidates": candidates, "candidate_count": len(candidates)}
    return {"lines": [line for result in results for line in result.stdout.splitlines() if line.strip()]}


def format_block_response(intent: Intent, assessment: SecurityAssessment) -> str:
    lines = [
        "操作已拦截。",
        f"意图: {intent.operation}",
        f"风险等级: {assessment.risk_level}",
        f"原因: {assessment.reason}",
    ]
    if assessment.impacts:
        lines.append("潜在影响:")
        lines.extend(f"- {impact}" for impact in assessment.impacts)
    return "\n".join(lines)


def format_confirmation_response(
    *,
    intent: Intent,
    assessment: SecurityAssessment,
    confirmation_id: str,
    preview: dict[str, Any],
) -> str:
    lines = [
        "高风险操作需要确认，尚未执行。",
        f"confirmation_id: {confirmation_id}",
        f"意图: {intent.operation}",
        f"风险等级: {assessment.risk_level}",
        f"原因: {assessment.reason}",
    ]
    candidates = preview.get("candidates", [])
    if isinstance(candidates, list) and candidates:
        lines.append("预览到以下候选对象:")
        for candidate in candidates:
            username = candidate.get("username", "-")
            uid = candidate.get("uid", "-")
            home = candidate.get("home", "-")
            lines.append(f"- {username} (UID: {uid}, HOME: {home})")
    preview_lines = preview.get("lines", [])
    if isinstance(preview_lines, list) and preview_lines:
        lines.append("执行前检查结果:")
        lines.extend(f"- {line}" for line in preview_lines[:10])
    if assessment.impacts:
        lines.append("潜在影响:")
        lines.extend(f"- {impact}" for impact in assessment.impacts)
    lines.append("继续执行:")
    lines.append(f"python -m opentower_cli dispatch --confirmation-id {confirmation_id} --answer yes --reason \"<why>\"")
    lines.append("取消执行:")
    lines.append(f"python -m opentower_cli dispatch --confirmation-id {confirmation_id} --answer no")
    return "\n".join(lines)


def format_unsupported_response(*, objective: str, reason: str) -> str:
    suggestions = _rewrite_suggestions(objective)
    lines = [
        "Request is outside the current implemented Linux ops scope. No commands were executed.",
        f"objective: {objective}",
        f"reason: {reason}",
        "currently_supported:",
        "- disk inspection",
        "- file and config search",
        "- process, port, and service status inspection",
        "- user management with safety checks",
        "suggestion: rewrite the request as a concrete disk, file, process, port, service-status, or user-management task.",
    ]
    if suggestions:
        lines.append("try_instead:")
        lines.extend(f"- {suggestion}" for suggestion in suggestions)
    return "\n".join(lines)


def _rewrite_suggestions(objective: str) -> list[str]:
    text = str(objective or "").strip()
    lowered = text.lower()

    def _service_name() -> str:
        for candidate in ("nginx", "sshd", "redis", "mysql", "postgres", "postgresql", "docker", "haproxy"):
            if candidate in lowered:
                return candidate
        return "nginx"

    suggestions: list[str] = []
    if any(token in lowered for token in ("restart", "start", "stop", "service", "daemon")):
        service = _service_name()
        suggestions.append(f"check {service} service status")
    if any(token in lowered for token in ("cpu", "slow", "load", "latency", "performance")):
        suggestions.extend(["show cpu usage", "show load average"])
    if any(token in lowered for token in ("log", "journal", "error")):
        service = _service_name()
        suggestions.append(f"tail the latest {service} error log" if service != "sshd" else "tail the latest syslog log")
    if any(token in lowered for token in ("disk", "filesystem", "storage", "partition")) or any(token in text for token in ("磁盘", "存储", "分区", "文件系统")):
        suggestions.append("查看磁盘使用情况")
    if any(token in lowered for token in ("user", "account", "group")) or any(token in text for token in ("用户", "账号", "组")):
        suggestions.extend(["查看所有用户", "inspect user dev01"])
    if any(token in lowered for token in ("config", "file", "directory", "search", "find")) or any(token in text for token in ("配置", "文件", "目录", "查找", "搜索")):
        suggestions.append("找到所有 nginx 配置文件")

    ordered: list[str] = []
    seen: set[str] = set()
    for suggestion in suggestions:
        clean = suggestion.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
    return ordered[:3]


def _format_disk_summary(results: list[CommandExecution], warning_threshold: int) -> str:
    df_output = next((result.stdout for result in results if result.name == "disk-usage"), "")
    partitions: list[str] = []
    for raw_line in df_output.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        filesystem, _size, used, avail, used_pct, mount = parts[:6]
        warning = ""
        try:
            pct_value = int(used_pct.rstrip("%"))
        except ValueError:
            pct_value = 0
        if pct_value >= warning_threshold:
            warning = " 警告"
        partitions.append(f"- {filesystem} ({mount}) 已用 {used_pct}，剩余 {avail}{warning}")
    if not partitions:
        return "未能解析磁盘使用结果。"
    return "当前磁盘使用情况:\n" + "\n".join(partitions)


def _format_file_summary(results: list[CommandExecution], intent: Intent) -> str:
    matches = [line.strip() for result in results for line in result.stdout.splitlines() if line.strip()]
    if intent.operation == "inspect_permissions":
        if not matches:
            return "未能读取目标路径的权限信息。"
        return "权限检查结果:\n" + "\n".join(f"- {item}" for item in matches[:10])
    pattern = str(intent.entities.get("pattern") or "")
    if not matches:
        return f"未找到与 `{pattern}` 相关的结果。"
    lines = [f"找到 {len(matches)} 条相关结果:"]
    lines.extend(f"- {item}" for item in matches[:20])
    return "\n".join(lines)


def _format_log_summary(results: list[CommandExecution], intent: Intent) -> str:
    lines = [line.strip() for result in results for line in result.stdout.splitlines() if line.strip()]
    path = str(intent.entities.get("path") or "-")
    if not lines:
        if intent.operation == "recent_error_scan":
            return f"No recent error lines were found in `{path}`."
        return f"No readable log lines were returned from `{path}`."
    heading = "Recent error lines" if intent.operation == "recent_error_scan" else "Recent log lines"
    rendered = [f"{heading} from `{path}`:"]
    rendered.extend(f"- {line}" for line in lines[:20])
    return "\n".join(rendered)


def _format_process_summary_readable(results: list[CommandExecution], intent: Intent) -> str:
    lines = [line.strip() for result in results for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        if intent.operation == "port_lookup":
            return f"No process is currently listening on port {intent.entities.get('port')}."
        if intent.operation == "service_status":
            service = str(intent.entities.get("service") or "-")
            return f"No matching service or process information was returned for `{service}`."
        return "No matching process or service information was returned."
    if intent.operation == "top_cpu":
        return "Top CPU processes:\n" + "\n".join(f"- {line}" for line in lines[:20])
    if intent.operation == "top_memory":
        return "Top memory processes:\n" + "\n".join(f"- {line}" for line in lines[:20])
    if intent.operation == "load_average":
        return "Load average summary:\n" + "\n".join(f"- {line}" for line in lines[:5])
    if intent.operation == "uptime_summary":
        return "Uptime summary:\n" + "\n".join(f"- {line}" for line in lines[:5])
    if intent.operation == "service_status":
        service = str(intent.entities.get("service") or "-")
        return f"Service or process status for `{service}`:\n" + "\n".join(f"- {line}" for line in lines[:20])
    return _format_process_summary(results, intent)


def _format_process_summary(results: list[CommandExecution], intent: Intent) -> str:
    lines = [line.strip() for result in results for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        if intent.operation == "port_lookup":
            return f"未发现占用端口 {intent.entities.get('port')} 的进程。"
        return "未发现匹配的进程或服务信息。"
    summary = "进程与端口结果:\n"
    summary += "\n".join(f"- {line}" for line in lines[:20])
    return summary


def _format_user_summary(results: list[CommandExecution], intent: Intent) -> str:
    username = str(intent.entities.get("username") or "")
    lines = [line.strip() for result in results for line in result.stdout.splitlines() if line.strip()]
    if intent.operation == "create_user":
        if lines:
            return f"已尝试创建用户 `{username}`。\n" + "\n".join(f"- {line}" for line in lines[:10])
        return f"已执行创建用户 `{username}` 的命令。"
    if intent.operation == "add_user_to_group":
        return f"已尝试将 `{username}` 加入目标组。\n" + "\n".join(f"- {line}" for line in lines[:10])
    if intent.operation in {"delete_user", "batch_delete_users"}:
        return "删除操作已执行。"
    if lines:
        return "\n".join(f"- {line}" for line in lines[:10])
    return "未返回可解析的用户信息。"


def format_execution_response(
    *,
    intent: Intent,
    assessment: SecurityAssessment,
    plan: CommandPlan,
    results: list[CommandExecution],
    warning_threshold: int = 80,
) -> str:
    errors = _command_errors(results)
    if errors:
        lines = [
            "命令执行未完全成功。",
            f"意图: {intent.operation}",
            *[f"- {error}" for error in errors],
        ]
        return "\n".join(lines)

    if plan.parser_kind == "disk":
        return _format_disk_summary(results, warning_threshold)
    if plan.parser_kind == "file-search":
        return _format_file_summary(results, intent)
    if plan.parser_kind == "log":
        return _format_log_summary(results, intent)
    if plan.parser_kind == "process":
        return _format_process_summary_readable(results, intent)
    if plan.parser_kind == "user-management":
        return _format_user_summary(results, intent)
    if plan.parser_kind == "chmod":
        return "权限修改命令已执行。"
    if plan.parser_kind == "destructive-path":
        return "删除命令已执行。"
    return f"执行完成，风险等级: {assessment.risk_level}"
