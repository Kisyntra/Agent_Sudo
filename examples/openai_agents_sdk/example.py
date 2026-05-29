from __future__ import annotations

import functools

from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest
from agent_sudo.policy import load_default_policy

# 1. Initialize policy and gateway
policy = load_default_policy()
gateway = PermissionGateway(policy)


def agent_sudo_gate(tool_name: str, action_name: str):
    """Wrapper to secure tool functions provided to OpenAI Assistants."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract inputs from assistant arguments
            target = kwargs.get("path") or kwargs.get("cmd") or "unspecified_target"
            payload = f"kwargs={kwargs}"

            # Map to Universal Schema
            request = ActionRequest(
                actor="openai-assistant-agent",
                source="user",
                tool=tool_name,
                action=action_name,
                target=str(target),
                payload_summary=payload,
            )

            # Evaluate against Gateway
            result = gateway.evaluate(request, dry_run=True)
            print(f"[Agent_Sudo] Assistant requested '{tool_name}:{action_name}'...")
            print(f"             Decision: {result.decision.name} ({result.reason})")

            if result.decision.name == "DENY":
                raise PermissionError(
                    f"Action blocked by Agent_Sudo gateway rules: {result.reason}"
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


# 2. Define tools for the OpenAI Agent
@agent_sudo_gate("filesystem", "write_file")
def write_file_tool(path: str, content: str) -> str:
    return f"Successfully wrote {len(content)} bytes to {path}"


@agent_sudo_gate("shell", "run_shell_command")
def run_command_tool(cmd: str) -> str:
    return f"Mock output of running command: {cmd}"


# 3. Simulate Assistant Runner Gating
if __name__ == "__main__":
    print("=== Scenario 1: Allowed Action (Safe file write) ===")
    try:
        # Writing a file to a non-system folder is permitted under the default policy
        res = write_file_tool(path="output.txt", content="Hello world")
        print(f"Assistant tool execution output: {res}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    print("=== Scenario 2: Blocked Action (Unsafe shell command) ===")
    try:
        # Shell commands require interactive approvals (strong approval).
        # In a dry-run/non-interactive context, they fail closed and are denied.
        run_command_tool(cmd="rm -rf /")
    except PermissionError as e:
        print(f"Caught expected permission exception: {e}\n")
