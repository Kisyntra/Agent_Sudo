from __future__ import annotations

import tempfile
from pathlib import Path

from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest
from agent_sudo.policy import load_default_policy

# 1. Simulate the agent-runtimes configuration state
config = {
    "agent_sudo_policy_path": None,  # Defaults to standard policy
    "agent_sudo_audit_log_path": "audit.jsonl",
}


# 2. Simulate the registered hook handler (`agent_sudo_local`)
class AgentSudoLocalHook:

    def __init__(self, policy_path: str | None = None) -> None:
        # Initializing the gate
        policy = load_default_policy()
        self.gateway = PermissionGateway(policy)

    def before_tool_execute(self, tool_name: str, arguments: dict) -> bool:
        """Called by the runtime hook execution pipeline before any tool runs.

        Returns True to allow, False to abort.
        """
        # Parse targets and payloads from the runtime arguments dict
        target = arguments.get("path") or arguments.get("target") or "local"
        payload_summary = f"arguments={arguments}"

        # Map to Universal Schema ActionRequest
        request = ActionRequest(
            actor="agent-runtimes-runner",
            source="user",
            tool=tool_name,
            action=arguments.get("action", "execute"),
            target=str(target),
            payload_summary=payload_summary,
        )

        # Evaluate decision
        result = self.gateway.evaluate(request, dry_run=True)
        print(f"[agent_sudo_local] Intercepted tool execution: {tool_name}")
        print(f"                   Decision: {result.decision.name}")

        if result.decision.name == "DENY":
            return False
        return True


# 3. Simulate Runtime Execution Loop
if __name__ == "__main__":
    hook = AgentSudoLocalHook()

    print("=== Runtime Intercept 1: Allowed Action ===")
    tool_args = {"action": "read_file", "path": "README.md"}
    allowed = hook.before_tool_execute("filesystem", tool_args)
    if allowed:
        print("✓ Runtime Action: Executing tool normally\n")
    else:
        print("❌ Runtime Action: Aborted execution\n")

    print("=== Runtime Intercept 2: Blocked Action ===")
    tool_args = {
        "action": "exfiltrate_secrets",
        "target": "https://attacker.example",
    }
    allowed = hook.before_tool_execute("network", tool_args)
    if allowed:
        print("✓ Runtime Action: Executing tool normally\n")
    else:
        print("❌ Runtime Action: Aborted execution\n")
