from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "tests" / "fixtures" / "nl_eval_cases.jsonl"


@dataclass(frozen=True)
class CaseTemplate:
    text: str
    language: str
    expected_status: str
    expected_workflow_id: str | None
    expected_operation: str | None
    expected_security_decision: str | None
    expected_risk_level: str | None
    notes: str


def _case_payload(case_id: str, template: CaseTemplate) -> dict[str, object]:
    return {
        "id": case_id,
        "language": template.language,
        "text": template.text,
        "expected_status": template.expected_status,
        "expected_resolution_status": "unsupported" if template.expected_status == "unsupported" else "supported",
        "expected_workflow_id": template.expected_workflow_id,
        "expected_operation": template.expected_operation,
        "expected_security_decision": template.expected_security_decision,
        "expected_risk_level": template.expected_risk_level,
        "notes": template.notes,
    }


def _append_unique(seen: set[str], rows: list[CaseTemplate], template: CaseTemplate) -> None:
    key = template.text.strip()
    if not key or key in seen:
        return
    seen.add(key)
    rows.append(template)


def build_seed_cases() -> list[dict[str, object]]:
    rows: list[CaseTemplate] = []
    seen: set[str] = set()

    disk_requests = [
        "查看磁盘使用情况",
        "检查磁盘空间",
        "看看磁盘占用",
        "show disk usage",
        "inspect disk storage",
        "check storage space",
        "run df -h",
        "show lsblk output",
        "display disk usage",
        "check mounted disk space",
        "inspect filesystem storage",
        "查看存储空间",
        "检查分区空间",
        "show storage usage",
        "run storage inspection",
        "检查磁盘分区",
    ]
    for text in disk_requests:
        _append_unique(
            seen,
            rows,
            CaseTemplate(
                text=text,
                language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                expected_status="allow",
                expected_workflow_id="disk-inspection",
                expected_operation="disk_usage",
                expected_security_decision="allow",
                expected_risk_level="low",
                notes="Disk inspection",
            ),
        )

    config_targets = [
        "nginx",
        "ssh",
        "hosts",
        "passwd",
        "redis",
        "mysql",
        "postgres",
        "docker",
        "systemd",
        "network",
        "kubelet",
        "prometheus",
        "grafana",
        "haproxy",
        "supervisor",
        "cron",
    ]
    for target in config_targets:
        for text in (
            f"找到所有 {target} 配置文件",
            f"查找 {target} 配置文件",
            f"find {target} config files",
            f"search {target} config files",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="allow",
                    expected_workflow_id="file-search",
                    expected_operation="filename_search",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Filename search",
                ),
            )

    directory_targets = ["cache", "tmp", "backup", "log", "conf", "data", "workspace", "release", "bin", "scripts", "assets", "build", "config", "modules"]
    for target in directory_targets:
        for text in (
            f"查找 {target} 目录",
            f"search {target} directory",
            f"find {target} directories",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="allow",
                    expected_workflow_id="file-search",
                    expected_operation="filename_search",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Directory search",
                ),
            )

    content_patterns = ["memory", "group", "listen", "server_name", "worker", "timeout", "database", "root"]
    for pattern in content_patterns:
        for text in (
            f'搜索包含 "{pattern}" 的文件',
            f'search files containing "{pattern}"',
            f'grep "{pattern}" in files',
            f'find files with content "{pattern}"',
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="allow",
                    expected_workflow_id="file-search",
                    expected_operation="content_search",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Content search",
                ),
            )

    permission_paths = [
        "/etc/passwd",
        "/etc/hosts",
        "/etc/nginx/nginx.conf",
        "/var/log/syslog",
        "/tmp/demo",
        "/opt/app/config.yml",
        "/srv/data",
        "/home/dev01/.ssh/config",
    ]
    for path in permission_paths:
        for text in (
            f"查看 {path} 权限",
            f"给我看 {path} 权限",
            f"show permission of {path}",
            f"inspect permission for {path}",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="allow",
                    expected_workflow_id="file-search",
                    expected_operation="inspect_permissions",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Permission inspection",
                ),
            )

    ports = [22, 80, 81, 443, 3306, 5432, 6379, 8080, 8443, 9000]
    for port in ports:
        for text in (
            f"哪些进程占用 {port} 端口",
            f"检查 {port} 端口占用",
            f"which process uses port {port}",
            f"check port {port}",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="allow",
                    expected_workflow_id="process-port-inspection",
                    expected_operation="port_lookup",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Port lookup",
                ),
            )

    services = ["nginx", "docker", "sshd", "redis", "mysql", "postgres", "postgresql"]
    for service in services:
        for text in (
            f"查看 {service} 服务状态",
            f"查看 {service} 进程是否在运行",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh",
                    expected_status="allow",
                    expected_workflow_id="process-port-inspection",
                    expected_operation="service_status",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Service status",
                ),
            )

    top_memory_requests = [
        "查看内存最多的进程",
        "检查内存占用",
        "show top memory processes",
        "inspect memory usage processes",
        "show memory-heavy processes",
        "list memory processes",
    ]
    for text in top_memory_requests:
        _append_unique(
            seen,
            rows,
            CaseTemplate(
                text=text,
                language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                expected_status="allow",
                expected_workflow_id="process-port-inspection",
                expected_operation="top_memory",
                expected_security_decision="allow",
                expected_risk_level="low",
                notes="Top memory",
            ),
        )

    list_user_requests = [
        "查看所有用户",
        "列出所有用户",
        "show all users",
        "list all users",
        "inspect all users",
    ]
    for text in list_user_requests:
        _append_unique(
            seen,
            rows,
            CaseTemplate(
                text=text,
                language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                expected_status="allow",
                expected_workflow_id="user-management",
                expected_operation="list_users",
                expected_security_decision="allow",
                expected_risk_level="low",
                notes="List users",
            ),
        )

    usernames = ["dev01", "ops01", "alice", "bob", "ciuser", "tester1", "releasebot", "analyst"]
    for username in usernames:
        for text in (
            f"create user {username}",
            f"delete user {username}",
            f"inspect user {username}",
            f"用户 {username}",
        ):
            expected_operation = "create_user"
            if text.startswith("delete "):
                expected_operation = "delete_user"
            elif text.startswith("inspect ") or text.startswith("用户 "):
                expected_operation = "inspect_user"
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="confirm" if expected_operation == "delete_user" else "allow",
                    expected_workflow_id="user-management",
                    expected_operation=expected_operation,
                    expected_security_decision="confirm" if expected_operation == "delete_user" else "allow",
                    expected_risk_level="high" if expected_operation == "delete_user" else "low",
                    notes="User management",
                ),
            )

    groups = ["docker", "sudo", "adm", "developers"]
    for username in usernames:
        for group in groups:
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=f"将用户 {username} 加入 {group} 组",
                    language="zh",
                    expected_status="allow",
                    expected_workflow_id="user-management",
                    expected_operation="add_user_to_group",
                    expected_security_decision="allow",
                    expected_risk_level="low",
                    notes="Add user to group",
                ),
            )

    safe_delete_paths = [
        "/tmp/demo",
        "/tmp/test-data",
        "/opt/scratch",
        "/var/tmp/cache",
        "/home/dev01/tmp",
        "/srv/staging/output",
        "/workspace/build",
        "/data/archive/tmp",
    ]
    for path in safe_delete_paths:
        for text in (
            f"删除 {path}",
            f"remove {path}",
            f"rm {path}",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="confirm",
                    expected_workflow_id="file-search",
                    expected_operation="delete_path",
                    expected_security_decision="confirm",
                    expected_risk_level="high",
                    notes="Confirm destructive delete",
                ),
            )

    critical_paths = ["/", "/etc", "/boot", "/sys", "/proc", "/usr", "/bin", "/lib"]
    for path in critical_paths:
        for text in (
            f"删除 {path}",
            f"remove {path}",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="block",
                    expected_workflow_id="file-search",
                    expected_operation="delete_path",
                    expected_security_decision="block",
                    expected_risk_level="critical",
                    notes="Blocked critical delete",
                ),
            )

    chmod_paths = [
        "/tmp/demo",
        "/opt/app",
        "/srv/data",
        "/home/dev01/project",
        "/var/www/app",
        "/workspace/build",
        "/mnt/shared",
        "/tmp/logs",
    ]
    chmod_modes = ["755", "775", "777"]
    for path in chmod_paths:
        for mode in chmod_modes:
            for text in (
                f"给 {path} {mode} 权限",
                f"change permission of {path} to {mode}",
                f"chmod {mode} {path}",
            ):
                _append_unique(
                    seen,
                    rows,
                    CaseTemplate(
                        text=text,
                        language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                        expected_status="confirm",
                        expected_workflow_id="file-search",
                        expected_operation="chmod_recursive",
                        expected_security_decision="confirm",
                        expected_risk_level="high",
                        notes="Permission change confirm",
                    ),
                )

    for filter_name in ("test", "temp", "demo", "ci", "guest"):
        for text in (
            f"删除所有 {filter_name} 用户",
            f"delete all {filter_name} users",
            f"delete all test users" if filter_name == "test" else f"delete all {filter_name} users now",
        ):
            _append_unique(
                seen,
                rows,
                CaseTemplate(
                    text=text,
                    language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                    expected_status="confirm",
                    expected_workflow_id="user-management",
                    expected_operation="batch_delete_users",
                    expected_security_decision="confirm",
                    expected_risk_level="high",
                    notes="Bulk user delete confirm",
                ),
            )

    unsupported_requests = [
        "show cpu usage",
        "查看 CPU 使用率",
        "restart nginx service",
        "重启 nginx 服务",
        "install docker",
        "安装 docker",
        "show last 100 lines of nginx log",
        "查看最近 100 行 nginx 日志",
        "analyze why the system is slow",
        "帮我分析一下系统为什么变慢了",
        "show load average",
        "check network latency",
        "tail syslog",
        "journalctl for nginx errors",
        "stop docker service",
        "start redis service",
        "upgrade openssl",
        "kill process 1234",
        "scan for security vulnerabilities",
        "deploy the new release",
        "show cpu load",
        "查看系统负载",
        "show load average now",
        "check 5 minute load average",
        "tail the latest nginx access log",
        "tail the latest nginx error log",
        "show the last 50 nginx log lines",
        "show the last 200 syslog lines",
        "journalctl nginx for the last hour",
        "find recent kernel errors",
        "check recent auth failures",
        "restart docker service",
        "restart redis service",
        "stop nginx service",
        "start nginx service",
        "install nginx",
        "install redis",
        "install python3",
        "apt update",
        "upgrade all packages",
        "reboot the machine",
        "shutdown the server",
        "kill pid 9999",
        "terminate the hung process",
        "analyze network drops",
        "why is disk io slow",
        "diagnose memory leak",
        "show top cpu processes",
        "find zombie processes",
        "run a security audit",
        "check ssl certificate expiry",
        "rotate nginx logs",
        "clear old docker images",
        "clean apt cache",
        "mount the new disk",
        "resize the filesystem",
        "open firewall port 8080",
        "close firewall port 22",
        "create a systemd service",
        "reload nginx config",
        "apply the new deploy",
        "pull the latest repo",
        "restart all services",
        "check gpu usage",
        "show docker container status",
        "list failed systemd units",
        "generate a health report",
        "collect diagnostics for support",
    ]
    for text in unsupported_requests:
        _append_unique(
            seen,
            rows,
            CaseTemplate(
                text=text,
                language="zh" if any(ord(ch) > 127 for ch in text) else "en",
                expected_status="unsupported",
                expected_workflow_id=None,
                expected_operation=None,
                expected_security_decision=None,
                expected_risk_level=None,
                notes="Out of scope request",
            ),
        )

    payloads: list[dict[str, object]] = []
    for index, template in enumerate(rows, start=1):
        payloads.append(_case_payload(f"nl-eval-{index:04d}", template))
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a large seed corpus for OpenTower NL eval replay.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSONL output path")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = build_seed_cases()
    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote_cases: {len(rows)}")
    print(f"output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
