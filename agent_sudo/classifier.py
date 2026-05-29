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

PATH_WRITE_ACTIONS = {"write_file", "edit_file", "delete_file"}
FILE_WRITE_ACTIONS = {"write_file", "edit_file"}

DEMO_ALLOWED_ABSOLUTE_PREFIXES = {
    "/tmp",
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
        if request.action == "run_shell_command" and is_blocked_shell_target(request.target):
            return Classification.BLOCKED
        if request.action == "read_file" and is_blocked_read_target(request.target):
            return Classification.BLOCKED
        if request.action == "get_runtime_context":
            return Classification.SAFE
        action_classification = self.policy.classification_for_action(request.action)
        if request.action in PATH_WRITE_ACTIONS and is_blocked_write_target(request.target):
            return Classification.BLOCKED
        if request.action in FILE_WRITE_ACTIONS and is_critical_write_target(request.target):
            if action_classification == Classification.BLOCKED:
                return Classification.BLOCKED
            return Classification.CRITICAL
        if request.action in PATH_WRITE_ACTIONS and is_forbidden_path_target(request.target):
            return Classification.BLOCKED
        if request.action in {"write_file", "edit_file"} and not is_write_target_allowed(request.target):
            return Classification.BLOCKED
        if is_protected_target(request.target) and request.action in PROTECTED_WRITE_ACTIONS:
            if action_classification == Classification.BLOCKED:
                return Classification.BLOCKED
            return Classification.CRITICAL
        if request.provenance.origin_type == OriginType.EXTERNAL_CONTENT and action_classification != Classification.BLOCKED:
            return Classification.SENSITIVE
        if request.source_trust in {TrustLevel.EXTERNAL_CONTENT, TrustLevel.UNKNOWN}:
            if action_classification == Classification.SAFE:
                return Classification.SENSITIVE
            return action_classification
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


def is_forbidden_path_target(target: str) -> bool:
    normalized = _normalized_target(target)
    lowered = normalized.lower()
    home = str(Path.home()).replace("\\", "/")

    if is_blocked_write_target(target):
        return True
    if normalized.startswith(f"{home}/.config/") or normalized == f"{home}/.config":
        return True
    return False


def is_blocked_write_target(target: str) -> bool:
    normalized = _normalized_target(target)
    lowered = normalized.lower()
    home = str(Path.home()).replace("\\", "/")

    if normalized.startswith(f"{home}/.ssh/") or normalized == f"{home}/.ssh":
        return True
    if is_protected_target(target) and _looks_like_tamper_target(lowered):
        return True
    return _looks_like_credential_path(lowered)


def is_write_target_allowed(target: str) -> bool:
    normalized = _normalized_target(target)
    path = Path(target).expanduser()
    if not path.is_absolute():
        return True
    return any(
        normalized == prefix or normalized.startswith(prefix.rstrip("/") + "/")
        for prefix in DEMO_ALLOWED_ABSOLUTE_PREFIXES
    )


def is_critical_write_target(target: str) -> bool:
    normalized = _normalized_target(target)
    lowered = normalized.lower()
    name = Path(normalized).name.lower()

    if name.endswith((".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".rb", ".pl")):
        return True
    if name in {".zshrc", ".bashrc"}:
        return True
    if _looks_like_launchd_plist(lowered):
        return True
    if _looks_like_cron_path(lowered):
        return True
    if _looks_like_systemd_unit(lowered):
        return True
    if _looks_like_mcp_config(lowered, name):
        return True
    if _looks_like_runtime_config(lowered, name):
        return True
    return is_protected_target(target)


def _normalized_target(target: str) -> str:
    return str(Path(target).expanduser()).replace("\\", "/")


def _looks_like_tamper_target(lowered: str) -> bool:
    return any(marker in lowered for marker in {"audit", "policy", "default_policy.yaml", "default_policy.yml"})


def _looks_like_credential_path(lowered: str) -> bool:
    path_parts = {part for part in lowered.replace("\\", "/").split("/") if part}
    sensitive_names = {
        ".env",
        "auth.json",
        "credentials",
        "secrets",
        "secret",
        "private_key",
        "id_rsa",
        "id_ed25519",
    }
    if path_parts & sensitive_names:
        return True
    return any(marker in lowered for marker in {"/auth/", "/credential/", "/credentials/", "/secret/", "/secrets/"})


def _looks_like_launchd_plist(lowered: str) -> bool:
    return lowered.endswith(".plist") and any(
        marker in lowered
        for marker in {
            "/library/launchagents/",
            "/library/launchdaemons/",
            "/system/library/launchagents/",
            "/system/library/launchdaemons/",
        }
    )


def _looks_like_cron_path(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in {
            "/etc/crontab",
            "/etc/cron.d/",
            "/etc/cron.daily/",
            "/etc/cron.hourly/",
            "/etc/cron.monthly/",
            "/etc/cron.weekly/",
            "/var/spool/cron/",
            "/var/cron/",
        }
    ) or lowered.endswith("/crontab")


def _looks_like_systemd_unit(lowered: str) -> bool:
    return "/systemd/" in lowered and lowered.endswith(
        (".service", ".timer", ".socket", ".mount", ".path", ".target")
    )


def _looks_like_mcp_config(lowered: str, name: str) -> bool:
    config_suffixes = (".json", ".jsonc", ".toml", ".yaml", ".yml")
    if name in {".mcp.json", "mcp.json", "mcp_config.json", "mcp-config.json"}:
        return True
    if "mcp" not in lowered or not name.endswith(config_suffixes):
        return False
    return any(marker in lowered for marker in {"/mcp/", "mcp_config", "mcp-config", "mcp.settings", "mcp_settings"})


def _looks_like_runtime_config(lowered: str, name: str) -> bool:
    config_names = {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "uv.lock",
        "poetry.lock",
        "config.toml",
        "config.yaml",
        "config.yml",
        "settings.json",
    }
    if "/.agent-runtime/" in lowered or lowered.endswith("/.agent-runtime"):
        return True
    if name in config_names and any(marker in lowered for marker in {"runtime", "agent-runtime", ".codex", ".agent"}):
        return True
    return False


def is_blocked_shell_target(command: str) -> bool:
    lowered = command.lower()
    parts = lowered.split()
    if parts and parts[0] == "rm" and any("r" in flag and "f" in flag for flag in parts[1:] if flag.startswith("-")):
        return True
    if parts and parts[0] == "chmod" and any(marker in lowered for marker in {".ssh", "auth", "credential"}):
        return True
    if any(marker in lowered for marker in {"id_rsa", ".ssh/", "private_key"}):
        return True
    if "token" in lowered and any(marker in lowered for marker in {"http://", "https://", "curl", "wget"}):
        return True

    # Block commands targeting protected configuration directories or system/agent credentials
    blocked_markers = {
        ".agent-sudo",
        ".agent-runtime",
        ".ssh",
        ".config",
        ".env",
        "pyproject.toml",
        "default_policy.yaml",
        "default_policy.yml",
        "auth.json",
        "mcp-audit.jsonl",
        "audit.jsonl",
        "audit.log",
        "agent_sudo/",
    }
    for marker in blocked_markers:
        if marker in lowered:
            return True

    return False


def is_blocked_read_target(target: str) -> bool:
    normalized = str(Path(target).expanduser()).replace("\\", "/")
    lowered = normalized.lower()
    name = Path(normalized).name.lower()
    home = str(Path.home()).replace("\\", "/")

    # Paths:
    # ~/.ssh/**
    if normalized.startswith(f"{home}/.ssh/") or normalized == f"{home}/.ssh":
        return True
    # ~/.config/**
    if normalized.startswith(f"{home}/.config/") or normalized == f"{home}/.config":
        return True
    # ~/.agent-sudo/**
    if normalized.startswith(f"{home}/.agent-sudo/") or normalized == f"{home}/.agent-sudo":
        return True
    # ~/.agent-runtime/**
    if normalized.startswith(f"{home}/.agent-runtime/") or normalized == f"{home}/.agent-runtime":
        return True

    # .env and .env.*
    if name == ".env" or name.startswith(".env."):
        return True

    # Files containing: auth, token, credential, secret, private_key, config, api-key
    keywords = {"auth", "token", "credential", "secret", "private_key", "config", "api" + "_" + "key"}
    if any(kw in name or kw in lowered for kw in keywords):
        return True

    return False


def _injection_scan_text(request: ActionRequest) -> str:
    return " ".join([request.source, request.tool, request.action, request.target, request.payload_summary])
