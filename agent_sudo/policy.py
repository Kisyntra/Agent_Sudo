from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from agent_sudo.models import Classification, Decision, PolicyResult


@dataclass(frozen=True)
class Policy:
    safe_actions: set[str]
    sensitive_actions: set[str]
    critical_actions: set[str]
    blocked_actions: set[str]

    def decision_for(self, classification: Classification) -> PolicyResult:
        if classification == Classification.SAFE:
            return PolicyResult(Decision.ALLOW, "SAFE actions are allowed by policy")
        if classification == Classification.SENSITIVE:
            return PolicyResult(Decision.REQUIRE_APPROVAL, "SENSITIVE actions require CLI approval")
        if classification == Classification.CRITICAL:
            return PolicyResult(
                Decision.REQUIRE_STRONG_APPROVAL,
                "CRITICAL actions require passphrase confirmation",
            )
        return PolicyResult(Decision.DENY, "BLOCKED actions are denied by policy")

    def classification_for_action(self, action: str) -> Classification:
        normalized = action.strip()
        if normalized in self.blocked_actions:
            return Classification.BLOCKED
        if normalized in self.critical_actions:
            return Classification.CRITICAL
        if normalized in self.sensitive_actions:
            return Classification.SENSITIVE
        if normalized in self.safe_actions:
            return Classification.SAFE
        return Classification.SENSITIVE


def load_default_policy() -> Policy:
    policy_path = resources.files("agent_sudo.config").joinpath("default_policy.yaml")
    return load_policy(Path(str(policy_path)))


def load_policy(path: Path) -> Policy:
    data = _parse_simple_yaml(path.read_text(encoding="utf-8"))
    return Policy(
        safe_actions=set(data.get("safe", [])),
        sensitive_actions=set(data.get("sensitive", [])),
        critical_actions=set(data.get("critical", [])),
        blocked_actions=set(data.get("blocked", [])),
    )


def _parse_simple_yaml(text: str) -> dict[str, list[str]]:
    """Parse the small list-only YAML shape used by the MVP policy file."""
    result: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            result[current_key] = []
            continue
        if line.lstrip().startswith("- "):
            if current_key is None:
                raise ValueError("policy list item found before a section")
            result[current_key].append(line.lstrip()[2:].strip())
            continue
        raise ValueError(f"unsupported policy YAML line: {raw_line}")
    return result
