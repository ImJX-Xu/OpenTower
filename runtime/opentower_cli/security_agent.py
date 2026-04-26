from __future__ import annotations

from .ops_types import Intent, SecurityAssessment


CRITICAL_PATHS = ("/", "/etc", "/boot", "/sys", "/proc", "/bin", "/sbin", "/usr", "/lib", "/lib64")
PROTECTED_USERS = {"root"}
PRIVILEGED_GROUPS = {"sudo", "docker", "adm", "wheel", "root", "lxd", "libvirt"}


def _path_is_critical(path: str) -> bool:
    clean = (path or "").strip() or "/"
    for critical in CRITICAL_PATHS:
        if clean == critical:
            return True
        if critical != "/" and clean.startswith(f"{critical}/"):
            return True
    return False


def assess_intent(intent: Intent) -> SecurityAssessment:
    if intent.operation == "create_user":
        username = str(intent.entities.get("username", "")).strip() or "<unknown>"
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Creating user '{username}' changes local account state and should be confirmed explicitly.",
            impacts=[
                "A new login identity may gain filesystem and process ownership on this machine.",
                "Automation or services may start relying on the new account immediately.",
            ],
            requires_reason=True,
        )

    if intent.operation == "add_user_to_group":
        username = str(intent.entities.get("username", "")).strip() or "<unknown>"
        group = str(intent.entities.get("group", "")).strip() or "<unknown>"
        privileged = group.lower() in PRIVILEGED_GROUPS
        impacts = [
            f"User '{username}' will inherit permissions associated with group '{group}'.",
            "The permission change may take effect for future sessions without further review.",
        ]
        if privileged:
            impacts.append(f"Group '{group}' is treated as privileged and may grant elevated host access.")
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=(
                f"Adding user '{username}' to group '{group}' changes effective host permissions"
                + (" and may grant elevated access." if privileged else ".")
            ),
            impacts=impacts,
            requires_reason=True,
        )

    if intent.operation == "delete_path":
        target_path = str(intent.entities.get("path", "")).strip() or "/"
        if _path_is_critical(target_path):
            return SecurityAssessment(
                decision="block",
                risk_level="critical",
                reason=f"Deleting {target_path} would damage core Linux system state.",
                impacts=[
                    "System configuration or boot files may be removed.",
                    "Services may fail immediately.",
                    "Users may lose the ability to log in.",
                ],
            )
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Deleting {target_path} is destructive and should not run without confirmation.",
            impacts=[
                "Files under the target path may be permanently removed.",
                "Dependent services may stop working.",
            ],
            requires_reason=True,
        )

    if intent.operation == "chmod_recursive":
        target_path = str(intent.entities.get("path", "")).strip() or "/"
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Recursively applying mode 777 to {target_path} breaks least-privilege controls.",
            impacts=[
                "Any local user may be able to modify protected files.",
                "Malicious processes could alter service configuration or executables.",
            ],
            requires_reason=True,
        )

    if intent.operation == "batch_delete_users":
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason="Bulk user deletion is destructive and must be previewed before confirmation.",
            impacts=[
                "Multiple accounts and home directories may be removed.",
                "Running sessions or jobs owned by those users may be disrupted.",
            ],
        )

    if intent.operation == "delete_user":
        username = str(intent.entities.get("username", "")).strip().lower()
        if username in PROTECTED_USERS:
            return SecurityAssessment(
                decision="block",
                risk_level="critical",
                reason=f"Deleting protected account '{username}' is not allowed.",
                impacts=[
                    "The system would lose a core administrative identity.",
                ],
            )
        return SecurityAssessment(
            decision="confirm",
            risk_level="high",
            reason=f"Deleting user '{username}' is destructive and should not run without confirmation.",
            impacts=[
                "The user's account may be removed immediately.",
                "The user's home directory and running jobs may be affected.",
            ],
            requires_reason=True,
        )

    return SecurityAssessment(
        decision="allow",
        risk_level="low",
        reason="The request fits the allowed Linux operations scope.",
        impacts=[],
    )
