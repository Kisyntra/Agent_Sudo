from __future__ import annotations

from pathlib import Path

from agent_sudo.injection import detect_prompt_injection
from agent_sudo.models import ActionRequest, Classification, OriginType, TrustLevel
from agent_sudo.policy import Policy


BLOCKING_HINTS = {
    "bypass_policy",
    "disable_audit",
    "exfiltration",
    "secret_exfiltration",
    "token_exfiltration",
}

PROTECTED_WRITE_ACTIONS = {
    "write_file",
    "edit_file",
    "delete_file",
    "run_shell_command",
    "modify_auth",
    "create_cron",
}

CRITICAL_HINTS = {
    "credentials",
    "secrets",
    "auth",
    "money",
    "employment",
    "legal",
    "external_post",
    "email_send",
    "destructive",
}

SENSITIVE_HINTS = {
    "writes_local_file",
    "external_side_effect",
    "shell",
    "browser_action",
    "scheduled_task",
}


class ActionClassifier:
    def __init__(self, policy: Policy):
        self.policy = policy

    def classify(self, request: ActionRequest) -> Classification:
        hints = {hint.strip().lower() for hint in request.risk_hints}
        if request.action == "prompt_injection_attempt" or detect_prompt_injection(_injection_scan_text(request)):
            return Classification.BLOCKED
        if hints & BLOCKING_HINTS:
            return Classification.BLOCKED
        action_classification = self.policy.classification_for_action(request.action)
        if request.provenance.origin_type == OriginType.EXTERNAL_CONTENT and action_classification != Classification.BLOCKED:
            return Classification.SENSITIVE
        if request.source_trust in {TrustLevel.EXTERNAL_CONTENT, TrustLevel.UNKNOWN}:
            if action_classification == Classification.SAFE:
                return Classification.SENSITIVE
            return action_classification
        if is_protected_target(request.target) and request.action in PROTECTED_WRITE_ACTIONS:
            if action_classification == Classification.BLOCKED:
                return Classification.BLOCKED
            return Classification.CRITICAL
        if hints & CRITICAL_HINTS:
            if action_classification == Classification.BLOCKED:
                return Classification.BLOCKED
            return Classification.CRITICAL
        if hints & SENSITIVE_HINTS:
            if action_classification in {Classification.BLOCKED, Classification.CRITICAL}:
                return action_classification
            return Classification.SENSITIVE
        return action_classification


def is_protected_target(target: str) -> bool:
    expanded = str(Path(target).expanduser())
    normalized = expanded.replace("\\", "/")
    home = str(Path.home()).replace("\\", "/")

    if normalized == "pyproject.toml" or normalized.endswith("/pyproject.toml"):
        return True
    if normalized.endswith(".yaml") or normalized.endswith(".yml"):
        return True
    if normalized.endswith(".jsonl") and "audit" in normalized.lower():
        return True
    if "audit" in normalized.lower() and normalized.endswith(".log"):
        return True
    if normalized.startswith("agent_sudo/config/") or "/agent_sudo/config/" in normalized:
        return True
    if normalized.startswith("agent_sudo/") and normalized.endswith(".py"):
        return True
    if "/agent_sudo/" in normalized and normalized.endswith(".py"):
        return True
    if normalized.startswith(f"{home}/.agent-sudo/"):
        return True
    if normalized == f"{home}/.agent-runtime/auth.json":
        return True
    if normalized.startswith(f"{home}/.agent-runtime/"):
        return True
    return False


def _injection_scan_text(request: ActionRequest) -> str:
    return " ".join([request.source, request.tool, request.action, request.target, request.payload_summary])
