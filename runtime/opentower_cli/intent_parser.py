from __future__ import annotations

import re
from typing import Any, Iterable

from .ops_types import Intent, IntentResolution


WORKFLOW_IDS = {
    "disk-inspection",
    "file-search",
    "process-port-inspection",
    "user-management",
}

SEARCH_VERBS_ZH = ("查找", "搜索", "找到", "找出", "搜寻")
FILE_SEARCH_NOUNS_ZH = ("文件", "配置文件", "配置", "日志", "目录", "ssh", "nginx", "conf", "设置", "参数")
PROCESS_HINTS_ZH = ("端口", "进程", "服务", "内存最多", "内存占用", "最占内存")
DISK_HINTS_ZH = ("磁盘", "分区", "存储", "空间", "文件系统", "挂载点")
USER_HINTS_ZH = ("用户", "账号")
DELETE_HINTS_ZH = ("删除", "移除", "清理")


def _quoted_values(text: str) -> list[str]:
    return [
        match.group(1) or match.group(2) or match.group(3) or match.group(4)
        for match in re.finditer(r'"([^"]+)"|\'([^\']+)\'|“([^”]+)”|‘([^’]+)’', text)
    ]


def _first_absolute_path(text: str) -> str | None:
    match = re.search(r"(/(?:[A-Za-z0-9._/\-]+)?)", text)
    return match.group(1) if match else None


def _extract_username(text: str) -> str | None:
    patterns = (
        r"用户\s*([A-Za-z_][A-Za-z0-9_-]*)",
        r"名为\s*([A-Za-z_][A-Za-z0-9_-]*)",
        r"user\s+([A-Za-z_][A-Za-z0-9_-]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_group(text: str) -> str | None:
    patterns = (
        r"加入\s*([A-Za-z0-9_-]+)\s*组",
        r"add\s+.*\s+to\s+([A-Za-z0-9_-]+)\s+group",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_user_filter(text: str, quoted: list[str]) -> str | None:
    if quoted:
        return quoted[0]
    patterns = (
        r"所有\s*([A-Za-z0-9_-]+)\s*用户",
        r"\ball\s+([A-Za-z0-9_-]+)\s+users\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_port(text: str) -> int | None:
    patterns = (
        r"端口\s*([0-9]{1,5})",
        r"([0-9]{1,5})\s*端口",
        r":([0-9]{1,5})",
        r"port\s*([0-9]{1,5})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        port = int(match.group(1))
        if 0 <= port <= 65535:
            return port
    return None


def _extract_service(text: str) -> str | None:
    keywords = (
        "nginx",
        "docker",
        "sshd",
        "redis",
        "mysql",
        "postgres",
        "postgresql",
        "haproxy",
        "chronyd",
        "rsyslog",
        "consul",
        "vault",
        "rabbitmq",
    )
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            return keyword
    match = re.search(r"([A-Za-z0-9_.@-]+)\s*(?:服务|service|进程)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_search_path(text: str, defaults: Iterable[str]) -> str:
    for path in re.findall(r"(/[A-Za-z0-9._/\-]+)", text):
        return path
    return next(iter(defaults), "/")


def _default_search_roots(text: str, lowered: str) -> tuple[str, ...]:
    if "/var/log" in text or "日志" in text or "log" in lowered:
        return ("/var/log", "/etc", "/")
    if "配置" in text or "config" in lowered or "nginx" in lowered:
        return ("/etc", "/")
    return ("/etc", "/")


def _default_filename_pattern(text: str, lowered: str, quoted: list[str]) -> str:
    if quoted:
        return quoted[0]
    if "错误日志" in text or "error" in lowered:
        return "*error*"
    match = re.search(r"([^\s/]+)\s*配置文件", text)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate not in {"所有", "全部", "相关", "指定", "这个", "该"}:
            return f"*{candidate}*"
    match = re.search(r"([^\s/]+)\s*(?:文件|目录|日志)", text)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate not in {"所有", "全部", "相关", "指定", "这个", "该", "配置"}:
            return f"*{candidate}*"
    service = _extract_service(text)
    if service:
        return f"*{service}*"
    if "配置" in text or "config" in lowered:
        return "*.conf*"
    return "*"


def _default_content_pattern(text: str, quoted: list[str]) -> str:
    if quoted:
        return quoted[0]
    service = _extract_service(text)
    if service:
        return service
    return "database"


def _looks_like_file_search(text: str, lowered: str, *, quoted: list[str], path: str | None) -> bool:
    if any(token in lowered for token in ("grep", "locate")):
        return True
    if re.search(r"\bfind\b", lowered) and (
        any(token in lowered for token in ("file", "files", "directory", "directories", "config", "configs", "log", "logs"))
        or quoted
        or path is not None
    ):
        return True
    if re.search(r"\bsearch\b", lowered) and any(token in lowered for token in ("file", "files", "directory", "directories", "config", "log")):
        return True

    has_search_verb = any(token in text for token in SEARCH_VERBS_ZH)
    has_file_noun = any(token in text for token in FILE_SEARCH_NOUNS_ZH)
    has_content_phrase = "包含" in text or "内容" in text or "content" in lowered or "containing" in lowered

    if has_file_noun and (has_search_verb or quoted or path is not None):
        return True
    if has_search_verb and has_content_phrase:
        return True
    return False


def _has_permission_change_intent(text: str, lowered: str) -> bool:
    has_mode = re.search(r"\b[0-7]{3,4}\b", lowered) is not None
    if "chmod" in lowered:
        return True
    if "权限" not in text and "permission" not in lowered:
        return False
    if has_mode and any(token in text for token in ("修改", "更改", "设置", "赋予", "授予", "开放", "给")):
        return True
    if any(token in text for token in ("修改", "更改", "设置", "赋予", "授予", "开放")):
        return True
    if has_mode and any(token in lowered for token in ("change permission", "set permission", "grant permission", "make permission")):
        return True
    if re.search(r"权限\s*(?:改成|设为|设置为|开放为)", text):
        return True
    return any(token in lowered for token in ("change permission", "set permission", "grant permission"))


def _looks_like_user_management(text: str, lowered: str) -> bool:
    if any(token in text for token in USER_HINTS_ZH):
        return True
    if any(token in lowered for token in ("useradd", "userdel", "usermod")):
        return True
    if re.search(r"\b(create|delete|list|inspect)\s+users?\b", lowered):
        return True
    if any(token in lowered for token in ("system users", "linux users", "user list", "user account")):
        return True
    if re.search(r"\b(delete|remove)\b.*\busers?\b", lowered):
        return True
    if "all users" in lowered:
        return True
    if ("加入" in text and "组" in text) or re.search(r"\badd\b.*\bgroup\b", lowered):
        return True
    if "passwd" in lowered:
        return any(token in text for token in ("用户", "密码", "账号")) or any(
            token in lowered for token in ("set password", "change password")
        )
    if "group" in lowered:
        return any(token in text for token in ("用户", "加入")) or any(
            token in lowered for token in ("groupadd", "groupdel", "usermod")
        )
    return False


def _has_unhandled_action_verb(lowered: str) -> bool:
    if any(token in lowered for token in ("重启", "启动", "停止", "安装", "升级", "卸载", "重载", "部署")):
        return True
    patterns = (
        r"挂载(?!点)",
        r"\brestart\b",
        r"\bstart\b",
        r"\bstop\b",
        r"\bkill\b",
        r"\bterminate\b",
        r"\binstall\b",
        r"\bupgrade\b",
        r"\breboot\b",
        r"\bshutdown\b",
        r"\bmount\b",
        r"\bumount\b",
        r"\bresize\b",
        r"\bgrow\b",
        r"\bshrink\b",
        r"\bmonitor\b",
        r"\breload\b",
        r"\bdeploy\b",
        r"\bpull\b",
        r"\bcapture\b",
        r"\brecord\b",
        r"\brotate\b",
        r"\bopen\b.*\bfirewall\b",
        r"\bclose\b.*\bfirewall\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _is_open_ended_diagnostic_request(text: str, lowered: str) -> bool:
    if "分析" in text:
        return True
    patterns = (
        r"\bwhy\b",
        r"\bdiagnose\b",
        r"\banaly[sz]e\b",
        r"\breport\b",
        r"\bdiagnostics?\b",
        r"\bleak\b",
        r"\bzombie\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _looks_like_process_request(text: str, lowered: str) -> bool:
    if any(token in text for token in PROCESS_HINTS_ZH):
        return True
    patterns = (
        r"\bport\b",
        r"\bprocess(?:es)?\b",
        r"\bmemory\b",
        r"\bsystemctl\b",
        r"\blsof\b",
        r"\bnetstat\b",
        r"\bss\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _with_workflow_hint(intent: Intent, workflow_hint: str | None) -> Intent:
    if not workflow_hint:
        return intent
    hint = str(workflow_hint).strip()
    if hint not in WORKFLOW_IDS:
        raise ValueError(f"Unknown workflow: {hint}")
    if hint != intent.workflow_id:
        raise ValueError(f"Objective does not match workflow '{hint}'; parser resolved '{intent.workflow_id}'.")
    return Intent(
        workflow_id=hint,
        operation=intent.operation,
        objective=intent.objective,
        entities=intent.entities,
        confidence=intent.confidence,
        rationale=intent.rationale,
    )


def parse_objective(objective: str, workflow_hint: str | None = None) -> Intent:
    text = str(objective or "").strip()
    if not text:
        raise ValueError("Objective is required.")

    lowered = text.lower()
    quoted = _quoted_values(text)
    path = _first_absolute_path(text)

    if _has_permission_change_intent(text, lowered):
        target_path = path or "/"
        return _with_workflow_hint(
            Intent(
                workflow_id="file-search",
                operation="chmod_recursive",
                objective=text,
                entities={"path": target_path, "mode": "777"},
                confidence=0.98,
                rationale="Detected a recursive permission-change request.",
            ),
            workflow_hint,
        )

    if "权限" in text or "permission" in lowered:
        if path is None:
            raise ValueError("Could not determine the path to inspect permissions for.")
        return _with_workflow_hint(
            Intent(
                workflow_id="file-search",
                operation="inspect_permissions",
                objective=text,
                entities={"path": path},
                confidence=0.9,
                rationale="Matched a read-only permissions inspection request.",
            ),
            workflow_hint,
        )

    if (any(token in text for token in DELETE_HINTS_ZH) or "rm " in lowered or "remove " in lowered) and path:
        return _with_workflow_hint(
            Intent(
                workflow_id="file-search",
                operation="delete_path",
                objective=text,
                entities={"path": path},
                confidence=0.98,
                rationale="Detected a path deletion request.",
            ),
            workflow_hint,
        )

    if _has_unhandled_action_verb(lowered):
        raise ValueError("Could not map the request to a supported Linux operations workflow.")

    if "cpu" in lowered:
        raise ValueError("Could not map the request to a supported Linux operations workflow.")

    if _is_open_ended_diagnostic_request(text, lowered):
        raise ValueError("Could not map the request to a supported Linux operations workflow.")

    if any(token in text for token in DISK_HINTS_ZH) or any(token in lowered for token in ("disk", "storage", "filesystem", "partition", "free space", "df -h", "lsblk", "mounted")):
        operation = "disk_usage_with_logs" if ("日志" in text or "/var/log" in text) else "disk_usage"
        return _with_workflow_hint(
            Intent(
                workflow_id="disk-inspection",
                operation=operation,
                objective=text,
                entities={"path": "/var/log" if "/var/log" in text else None},
                confidence=0.92,
                rationale="Matched disk, partition, or storage-inspection language.",
            ),
            workflow_hint,
        )

    if _looks_like_user_management(text, lowered):
        username = _extract_username(text)
        group = _extract_group(text)
        has_delete_verb = any(token in text for token in DELETE_HINTS_ZH) or "delete" in lowered or "userdel" in lowered
        wants_all_users = (
            "所有" in text
            or "全部" in text
            or "批量" in text
            or re.search(r"\ball\s+[A-Za-z0-9_-]+\s+users\b", lowered) is not None
        )
        if has_delete_verb and wants_all_users:
            user_filter = _extract_user_filter(text, quoted) or "test"
            return _with_workflow_hint(
                Intent(
                    workflow_id="user-management",
                    operation="batch_delete_users",
                    objective=text,
                    entities={"user_filter": user_filter},
                    confidence=0.94,
                    rationale="Matched a bulk user-deletion request.",
                ),
                workflow_hint,
            )
        if (
            "列出" in text
            or "列表" in text
            or "查看所有用户" in text
            or "所有账号" in text
            or "all users" in lowered
            or any(token in lowered for token in ("system users", "linux users", "user list", "user account"))
            or wants_all_users
        ) and not has_delete_verb:
            return _with_workflow_hint(
                Intent(
                    workflow_id="user-management",
                    operation="list_users",
                    objective=text,
                    entities={},
                    confidence=0.88,
                    rationale="Matched a read-only user listing request.",
                ),
                workflow_hint,
            )
        if "创建" in text or "create" in lowered or "useradd" in lowered:
            if not username:
                raise ValueError("Could not determine the username to create.")
            operation = "create_user"
        elif ("加入" in text and "组" in text) or "usermod" in lowered:
            if not username:
                raise ValueError("Could not determine the username to update.")
            if not group:
                raise ValueError("Could not determine the target group.")
            operation = "add_user_to_group"
        elif has_delete_verb:
            if not username:
                raise ValueError("Could not determine the username to delete.")
            operation = "delete_user"
        else:
            if not username:
                raise ValueError("Could not determine which user to inspect.")
            operation = "inspect_user"
        return _with_workflow_hint(
            Intent(
                workflow_id="user-management",
                operation=operation,
                objective=text,
                entities={"username": username, "group": group},
                confidence=0.92,
                rationale="Matched user-account management language.",
            ),
            workflow_hint,
        )

    if _looks_like_file_search(text, lowered, quoted=quoted, path=path):
        search_path = _extract_search_path(text, defaults=_default_search_roots(text, lowered))
        search_kind = "directory" if ("目录" in text or "directory" in lowered or "directories" in lowered) else "file"
        if "包含" in text or "content" in lowered or "containing" in lowered or "grep" in lowered:
            pattern = _default_content_pattern(text, quoted)
            operation = "content_search"
            entities = {"path": search_path, "pattern": pattern}
        else:
            pattern = _default_filename_pattern(text, lowered, quoted)
            operation = "filename_search"
            entities = {"path": search_path, "pattern": pattern, "search_kind": search_kind}
        return _with_workflow_hint(
            Intent(
                workflow_id="file-search",
                operation=operation,
                objective=text,
                entities=entities,
                confidence=0.9,
                rationale="Matched filename or content-search language.",
            ),
            workflow_hint,
        )

    if _looks_like_process_request(text, lowered):
        port = _extract_port(text)
        service = _extract_service(text)
        if "内存最多" in text or "内存占用" in text or "最占内存" in text or "吃内存" in text or "memory" in lowered:
            operation = "top_memory"
        elif port is not None:
            operation = "port_lookup"
        elif service:
            operation = "service_status"
        else:
            operation = "process_lookup"
        return _with_workflow_hint(
            Intent(
                workflow_id="process-port-inspection",
                operation=operation,
                objective=text,
                entities={"port": port, "service": service},
                confidence=0.9,
                rationale="Matched process, service, port, or memory inspection language.",
            ),
            workflow_hint,
        )

    raise ValueError("Could not map the request to a supported Linux operations workflow.")


def resolve_objective(
    objective: str,
    workflow_hint: str | None = None,
    *,
    normalizer: Any | None = None,
    fallback_agent: Any | None = None,
) -> IntentResolution:
    try:
        intent = parse_objective(objective, workflow_hint=workflow_hint)
    except ValueError as exc:
        resolved = IntentResolution(
            status="unsupported",
            intent=None,
            reason=str(exc),
            source="local_rule",
        )
        if normalizer is not None:
            try:
                normalized = normalizer.normalize(objective=objective, workflow_hint=workflow_hint)
            except Exception:
                normalized = None
            if normalized is not None:
                if normalized.status == "supported":
                    return normalized
                resolved = normalized
        if fallback_agent is None:
            return resolved
        try:
            researched = fallback_agent.research(
                objective=objective,
                workflow_hint=workflow_hint,
                prior_reason=resolved.reason,
                prior_source=resolved.source,
            )
        except Exception:
            return resolved
        return researched
    return IntentResolution(
        status="supported",
        intent=intent,
        reason=intent.rationale,
        source="local_rule",
    )
